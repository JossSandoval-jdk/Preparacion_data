"""
03_transformacion.py: Paso 3 del Pipeline (Transformación de Datos).
Este módulo consolida múltiples fuentes de datos en una sola estructura tabular.
Realiza pivoteo de métricas, cálculo de tasas (derivadas) y agregación de eventos
basada en ventanas temporales.
"""

import json
import os

import numpy as np
import pandas as pd

import config


def log(msg):
    print(f"[TRANSFORMACION] {msg}", flush=True)


# Contadores DMV que en el collector llegan como valor crudo (sin delta), por
# lo que quedan en 0 en capturas: no se convierten a tasa, se dejan tal cual.
CONTADORES_SIN_DELTA = [
    "page_reads_per_sec", "page_writes_per_sec", "rollbacks_per_sec",
    "batch_requests_per_sec", "sql_compilations_per_sec",
]

# Contadores acumulativos que el collector entrega como tasa real por segundo
# (tras la correccion del collector, el propio collector calcula delta/dt para
# los contadores /sec). Por eso aqui NO se vuelve a diferenciar transactions_per_sec.
# total_reads / total_writes siguen viniendo como conteos acumulados (del
# dm_io_virtual_file_stats) y SI se convierten a tasa real (delta/dt) aqui.
CONTADORES_A_TASA = ["total_reads", "total_writes"]

# Eventos DMV a agregar por timestamp (seconds)
EVENTOS_DMV = ["login", "logout", "sql_batch_completed", "lock_acquired",
               "lock_released", "wait_info"]


def pivot_metricas(corrida, dir_salida):
    """
    Transforma el formato largo (log de métricas) a formato ancho (tabla de variables).
    Cada variable única se convierte en una columna para permitir análisis temporal.
    """
    df_m = pd.read_csv(os.path.join(dir_salida, config.NOMBRE_METRICAS_LIMPIO),
                       encoding="utf-8-sig")
    df_m["timestamp"] = pd.to_datetime(df_m["timestamp"])
    wide = df_m.pivot_table(index="timestamp", columns="metrica", values="valor",
                            aggfunc="first")
    wide = wide.reset_index()
    return wide


def aplicar_tasas(wide):
    """Calcula las tasas de cambio para variables acumulativas (delta/dt)."""
    wide = wide.sort_values("timestamp").reset_index(drop=True)
    dt = wide["timestamp"].diff().dt.total_seconds()
    for col in CONTADORES_A_TASA:
        if col in wide.columns:
            wide[col] = wide[col].diff() / dt
    return wide


def _asignar_a_muestras(df, timestamps):
    """
    Utiliza un join 'asof' para alinear eventos discretos (log)
    a la muestra temporal (métricas) más cercana cronológicamente.
    """
    muestras = pd.DataFrame({"muestra_timestamp": pd.to_datetime(timestamps)})
    muestras = muestras.drop_duplicates().sort_values("muestra_timestamp")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    if df.empty or muestras.empty:
        return df.iloc[0:0].copy()
    asignado = pd.merge_asof(
        df,
        muestras,
        left_on="timestamp",
        right_on="muestra_timestamp",
        direction="forward",
    )
    return asignado.dropna(subset=["muestra_timestamp"])


def agregar_eventos_dmv(corrida, dir_salida, timestamps):
    """Agrega events.log dentro de la ventana de cada muestra de metricas."""
    ruta = os.path.join(dir_salida, config.NOMBRE_EVENTS_LIMPIO)
    if not os.path.exists(ruta):
        return None
    df_e = pd.read_csv(ruta, encoding="utf-8-sig")
    if df_e.empty or "timestamp" not in df_e.columns:
        return None
    df_e = df_e.copy()
    df_e["timestamp"] = pd.to_datetime(df_e["timestamp"], errors="coerce")
    if "event_name" not in df_e.columns:
        return None
    df_e = _asignar_a_muestras(df_e, timestamps)
    out = pd.DataFrame({"timestamp": pd.to_datetime(timestamps).drop_duplicates().sort_values()})
    user_events = df_e[df_e["process_type"] == "USER"] \
        if "process_type" in df_e.columns else df_e.iloc[0:0]

    renombrar = {
        "login": "events_login_count",
        "logout": "events_logout_count",
        "wait_info": "events_wait_count",
    }
    for origen, nombre in renombrar.items():
        counts = user_events.loc[user_events["event_name"] == origen].groupby(
            "muestra_timestamp").size()
        out[nombre] = out["timestamp"].map(counts).fillna(0).astype(int)

    lock_counts = df_e[df_e["event_name"].isin(["lock_acquired", "lock_released"])] \
        .groupby("muestra_timestamp").size()
    out["events_lock_count"] = out["timestamp"].map(lock_counts).fillna(0).astype(int)

    batch = user_events[user_events["event_name"] == "sql_batch_completed"].copy()
    out["events_batch_count"] = out["timestamp"].map(
        batch.groupby("muestra_timestamp").size()
    ).fillna(0).astype(int)

    for column in ("duration", "cpu_time", "logical_reads", "writes"):
        if column in batch.columns:
            batch[column] = pd.to_numeric(batch[column], errors="coerce").fillna(0)
        else:
            batch[column] = 0
    grouped = batch.groupby("muestra_timestamp")
    long_queries = batch[batch["duration"] > 15000].groupby("muestra_timestamp").size()
    long_transactions = batch[batch["duration"] > 30000].groupby("muestra_timestamp").size()
    out["long_queries"] = out["timestamp"].map(long_queries).fillna(0).astype(int)
    out["long_transactions"] = out["timestamp"].map(long_transactions).fillna(0).astype(int)
    for source, target, method in [
        ("duration", "query_duration_max_ms", "max"),
        ("duration", "query_duration_avg_ms", "mean"),
        ("cpu_time", "cpu_time_sum_ms", "sum"),
        ("logical_reads", "logical_reads_sum", "sum"),
        ("writes", "writes_sum", "sum"),
    ]:
        values = getattr(grouped[source], method)()
        out[target] = out["timestamp"].map(values).fillna(0)

    wait_type = df_e.get("wait_type", pd.Series(index=df_e.index, dtype="object")) \
        .fillna("").astype(str).str.upper()
    out["wait_lck_count"] = out["timestamp"].map(
        df_e.loc[wait_type.str.startswith("LCK_")].groupby("muestra_timestamp").size()
    ).fillna(0).astype(int)
    out["wait_io_count"] = out["timestamp"].map(
        df_e.loc[wait_type.str.startswith(("PAGEIOLATCH_", "PAGELATCH_"))]
        .groupby("muestra_timestamp").size()
    ).fillna(0).astype(int)
    out["wait_log_count"] = out["timestamp"].map(
        df_e.loc[wait_type == "WRITELOG"].groupby("muestra_timestamp").size()
    ).fillna(0).astype(int)

    sessions = pd.to_numeric(df_e.get("session_id"), errors="coerce")
    out["distinct_sessions_count"] = out["timestamp"].map(
        user_events.assign(_session_id=pd.to_numeric(user_events.get("session_id"), errors="coerce"))
        .dropna(subset=["_session_id"])
        .groupby("muestra_timestamp")["_session_id"].nunique()
    ).fillna(0).astype(int)

    out["query_count"] = out["events_batch_count"]
    out["wait_count"] = out["timestamp"].map(
        user_events[user_events["event_name"] == "wait_info"]
        .groupby("muestra_timestamp").size()
    ).fillna(0).astype(int)
    out["lock_event_count"] = out["timestamp"].map(
        df_e[df_e["event_name"].isin(["lock_acquired", "lock_released"])]
        .groupby("muestra_timestamp").size()
    ).fillna(0).astype(int)
    out["error_count"] = out["timestamp"].map(
        df_e[df_e["event_name"].isin(["error_reported", "xml_deadlock_report"])]
        .groupby("muestra_timestamp").size()
    ).fillna(0).astype(int)

    # Alias historicos conservados para no romper consumidores existentes.
    out["duration_max_ms"] = out["query_duration_max_ms"]
    out["duration_avg_ms"] = out["query_duration_avg_ms"]
    return out


def agregar_logs_sqlserver(dir_salida, timestamps):
    """Agrega errores y advertencias del error log en cada ventana de muestra."""
    ruta = os.path.join(dir_salida, config.NOMBRE_SQLSERVER_LOGS_LIMPIO)
    if not os.path.exists(ruta):
        return None
    df_l = pd.read_csv(ruta, encoding="utf-8-sig")
    if df_l.empty or "timestamp" not in df_l.columns:
        return None
    df_l["timestamp"] = pd.to_datetime(df_l["timestamp"], errors="coerce")
    df_l = _asignar_a_muestras(df_l, timestamps)
    out = pd.DataFrame({"timestamp": pd.to_datetime(timestamps).drop_duplicates().sort_values()})
    mensaje = df_l.get("mensaje", pd.Series(index=df_l.index, dtype="object")) \
        .fillna("").astype(str).str.lower()
    severidad = mensaje.str.extract(r"severity\s*(?:level)?\s*[:=]?\s*(\d+)", expand=False)
    severidad = pd.to_numeric(severidad, errors="coerce")
    grupos = {
        "log_error_count": mensaje.str.contains("error", regex=False),
        "log_warning_count": mensaje.str.contains("warning|advertencia", regex=True),
        "log_fatal_count": mensaje.str.contains("fatal", regex=False) | severidad.between(20, 25),
    }
    for nombre, mask in grupos.items():
        out[nombre] = out["timestamp"].map(
            df_l.loc[mask].groupby("muestra_timestamp").size()
        ).fillna(0).astype(int)
    return out


def agregar_eventos_xe(corrida, dir_salida):
    """Agrega events_xe.log por segundo -> conteos XE + duracion (max/avg ms)."""
    ruta = os.path.join(dir_salida, config.NOMBRE_EVENTS_XE_LIMPIO)
    if not os.path.exists(ruta):
        return None
    df_x = pd.read_csv(ruta, encoding="utf-8-sig")
    df_x["timestamp"] = pd.to_datetime(df_x["timestamp"])
    if df_x.empty or "timestamp" not in df_x.columns:
        return None
    df_x = df_x.copy()
    df_x["ts"] = df_x["timestamp"].dt.floor("s")

    out = pd.DataFrame(index=df_x["ts"].unique()).sort_index()
    out.index.name = "ts"

    if "event_name" in df_x.columns:
        out["xe_batch_count"] = (df_x["event_name"] == "xe.sql_batch_completed") \
            .groupby(df_x["ts"]).sum().astype(int)
        out["xe_rpc_count"] = (df_x["event_name"] == "xe.rpc_completed") \
            .groupby(df_x["ts"]).sum().astype(int)
        out["xe_errors_count"] = (df_x["event_name"] == "xe.error_reported") \
            .groupby(df_x["ts"]).sum().astype(int)

    # duracion de sql_batch_completed (microsegundos -> ms)
    batch = df_x[df_x["event_name"] == "xe.sql_batch_completed"]
    if not batch.empty and "duration" in batch.columns:
        dur_ms = batch["duration"].astype(float) / 1000.0
        g = pd.DataFrame({"ts": batch["ts"], "dur": dur_ms}).groupby("ts")["dur"]
        out["duration_max_ms"] = g.max()
        out["duration_avg_ms"] = g.mean()

    out = out.reset_index().rename(columns={"ts": "timestamp"})
    return out


def transformar_corrida(corrida):
    dir_salida = os.path.join(config.DIR_LIMPIO, corrida)

    wide = pivot_metricas(corrida, dir_salida)
    wide = aplicar_tasas(wide)
    wide["cpu_total"] = wide.get("cpu_usr", 0) + wide.get("cpu_sys", 0)

    n_muestras = len(wide)
    log(f"   Muestras={n_muestras}")

    # unir eventos DMV
    ev_dmv = agregar_eventos_dmv(corrida, dir_salida, wide["timestamp"])
    if ev_dmv is not None and len(ev_dmv) > 0:
        wide = wide.merge(ev_dmv, on="timestamp", how="left")
        for column in ("long_queries", "long_transactions"):
            recalculada = f"{column}_y"
            capturada = f"{column}_x"
            if recalculada in wide.columns:
                wide[column] = wide[recalculada]
                wide = wide.drop(columns=[recalculada])
            if capturada in wide.columns:
                wide = wide.drop(columns=[capturada])

    # unir error log de SQL Server
    ev_logs = agregar_logs_sqlserver(dir_salida, wide["timestamp"])
    if ev_logs is not None and len(ev_logs) > 0:
        wide = wide.merge(ev_logs, on="timestamp", how="left")

    active_sessions = pd.to_numeric(wide.get("active_sessions"), errors="coerce")
    active_requests = pd.to_numeric(wide.get("active_requests"), errors="coerce")
    wide["requests_per_session"] = (
        active_requests.div(active_sessions.replace(0, np.nan)).fillna(0)
    )

    # unir eventos XE
    ev_xe = agregar_eventos_xe(corrida, dir_salida)
    if ev_xe is not None and len(ev_xe) > 0:
        wide = wide.merge(ev_xe, on="timestamp", how="left")

    cols_eventos = [
        c for c in wide.columns
        if c.startswith(("events_", "xe_", "duration_", "query_duration_",
                 "cpu_time_", "logical_reads_", "writes_", "wait_",
                 "distinct_sessions_", "log_"))
    ]
    log(f"   Columnas=eventos:{len(cols_eventos)}")

    wide.to_csv(os.path.join(dir_salida, config.NOMBRE_TRANSFORMADO),
                index=False, encoding="utf-8-sig")

    resumen = {
        "corrida": corrida,
        "muestras": int(n_muestras),
        "columnas": int(wide.shape[1]),
        "columnas_eventos": len(cols_eventos),
    }
    with open(os.path.join(dir_salida, "resumen_transformacion.json"),
              "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)
    return resumen


def main():
    corridas = sorted([
        d for d in os.listdir(config.DIR_LIMPIO)
        if os.path.isdir(os.path.join(config.DIR_LIMPIO, d))
        and os.path.exists(os.path.join(config.DIR_LIMPIO, d,
                                        config.NOMBRE_METRICAS_LIMPIO))
    ])
    log(f"Corridas a transformar ({len(corridas)}): {corridas}")

    resumenes = []
    for corrida in corridas:
        log(f"-- Transformando: {corrida}")
        resumenes.append(transformar_corrida(corrida))

    print("\n=== RESUMEN TRANSFORMACION ===")
    for r in resumenes:
        print(f"  {r['corrida']:<10} muestras={r['muestras']:<3} "
              f"cols={r['columnas']:<3} cols_eventos={r['columnas_eventos']}")


if __name__ == "__main__":
    main()

