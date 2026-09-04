"""
04_integracion.py
=================
Paso 4 de la preparacion de datos (CRISP-DM): integracion consolidada.

Une los datos transformados de todas las corridas en un dataset integrado de
la CARGA DE TRABAJO tal cual se capturo. NO se etiqueta ninguna anomalia: en
preparacion solo se conoce la carga; la deteccion es del modelo (Modelado).

Columnas: timestamp + features canonicas + contexto (run_name, experiment_id,
es_carga_normal). Sin columna is_anomaly.

Salidas:
  datasets/integrado/dataset_steelnort_preparado.csv
  datasets/integrado/metadata_transformaciones.json
  datasets/integrado/reporte_calidad_datos.csv
"""

import json
import os

import numpy as np
import pandas as pd

import config


def log(msg):
    print(f"[INTEGRACION] {msg}", flush=True)


def cargar_transformadas():
    corridas = sorted([
        d for d in os.listdir(config.DIR_LIMPIO)
        if os.path.isdir(os.path.join(config.DIR_LIMPIO, d))
        and os.path.exists(os.path.join(config.DIR_LIMPIO, d,
                                        config.NOMBRE_TRANSFORMADO))
    ])
    out = []
    for c in corridas:
        df = pd.read_csv(os.path.join(config.DIR_LIMPIO, c, config.NOMBRE_TRANSFORMADO),
                         encoding="utf-8-sig")
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        out.append((c, df))
    return out


def construir_integrado(corridas):
    frames = []
    feats = config.columnas_features()
    for idx, (corrida, df) in enumerate(corridas):
        d = df.copy()
        for col in feats:
            if col not in d.columns:
                d[col] = np.nan
        d["run_name"] = corrida
        d["experiment_id"] = f"exp_{idx+1:02d}"
        d["es_carga_normal"] = 1 if corrida in config.CORRIDAS_CARGA_NORMAL else 0
        orden = ["timestamp"] + feats + config.columnas_contexto()
        frames.append(d[orden])
    df = pd.concat(frames, ignore_index=True, sort=False)
    df = df.sort_values(["experiment_id", "timestamp"]).reset_index(drop=True)
    return df


def reporte_calidad(df):
    feats = config.columnas_features()
    n = len(df)
    filas = []
    for col in feats:
        s = df[col].dropna()
        nulos = int(df[col].isna().sum())
        unicos = int(df[col].nunique(dropna=True))
        filas.append({
            "columna": col,
            "total": n,
            "nulos": nulos,
            "pct_nulos": round(nulos / n * 100, 2),
            "unicos": unicos,
            "media": round(float(s.mean()), 4) if len(s) else np.nan,
            "desv_std": round(float(s.std()), 4) if len(s) else np.nan,
            "min": round(float(s.min()), 4) if len(s) else np.nan,
            "max": round(float(s.max()), 4) if len(s) else np.nan,
        })
    return pd.DataFrame(filas)


def exportar_fuentes_detalle(corridas):
    """Consolida eventos y logs sin mezclarlos con el dataset numerico."""
    eventos = []
    logs = []
    for corrida, _ in corridas:
        dir_salida = os.path.join(config.DIR_LIMPIO, corrida)
        ruta_eventos = os.path.join(dir_salida, config.NOMBRE_EVENTOS_PREPARADOS)
        ruta_logs = os.path.join(dir_salida, config.NOMBRE_LOGS_PREPARADOS)
        if os.path.exists(ruta_eventos):
            df_eventos = pd.read_csv(ruta_eventos, encoding="utf-8-sig")
            df_eventos["run_name"] = corrida
            eventos.append(df_eventos)
        if os.path.exists(ruta_logs):
            df_logs = pd.read_csv(ruta_logs, encoding="utf-8-sig")
            df_logs["run_name"] = corrida
            logs.append(df_logs)

    if eventos:
        pd.concat(eventos, ignore_index=True, sort=False).to_csv(
            os.path.join(config.DIR_INTEGRADO, config.ARCHIVO_DATASET_EVENTOS),
            index=False, encoding="utf-8-sig")
    if logs:
        pd.concat(logs, ignore_index=True, sort=False).to_csv(
            os.path.join(config.DIR_INTEGRADO, config.ARCHIVO_DATASET_LOGS),
            index=False, encoding="utf-8-sig")


def main():
    corridas = cargar_transformadas()
    if not corridas:
        log("No hay datos transformados. Ejecuta 03_transformacion.py.")
        return
    log(f"Corridas a integrar ({len(corridas)}): {[c[0] for c in corridas]}")

    df = construir_integrado(corridas)
    os.makedirs(config.DIR_INTEGRADO, exist_ok=True)

    ruta_csv = os.path.join(config.DIR_INTEGRADO, config.ARCHIVO_DATASET_INTEGRADO)
    df.to_csv(ruta_csv, index=False, encoding="utf-8-sig")
    log(f"Dataset integrado en: {ruta_csv} ({df.shape[0]} filas x {df.shape[1]} cols)")
    exportar_fuentes_detalle(corridas)

    reporte = reporte_calidad(df)
    ruta_rep = os.path.join(config.DIR_INTEGRADO, config.ARCHIVO_REPORTE_CALIDAD)
    reporte.to_csv(ruta_rep, index=False, encoding="utf-8-sig")
    log(f"Reporte de calidad en: {ruta_rep}")

    metadata = {
        "descripcion": "Dataset integrado de carga de trabajo SteelNort "
                       "(fase preparacion CRISP-DM).",
        "fase_crispdm": "Data Preparation",
        "n_features": len(config.columnas_features()),
        "features": config.columnas_features(),
        "contexto": config.columnas_contexto(),
        "carga_normal_referencia": config.CORRIDAS_CARGA_NORMAL,
        "corridas": [
            {"run_name": r, "filas": int(len(d)),
             "rango": [str(d["timestamp"].min()), str(d["timestamp"].max())]}
            for (r, d) in corridas
        ],
        "total_filas": int(len(df)),
        "nota_etiquetado": (
            "CRISP-DM: en preparacion NO se asigna is_anomaly. Solo se conoce la "
            "carga de trabajo; la deteccion de anomalias la decide el modelo no "
            "supervisado (Isolation Forest) en la fase de Modelado. "
            "es_carga_normal solo marca la referencia normal de entrenamiento."
        ),
        "nota_tasas": (
            "transactions_per_sec/total_reads/total_writes convertidas a tasa "
            "por segundo (delta/dt); primera muestra por corrida = NaN. "
            "page_reads/writes, rollbacks, batch_requests, sql_compilations son "
            "contadores sin delta en el collector (quedan en 0) -> se resuelven "
            "en seleccion por senal."
        ),
    }
    ruta_meta = os.path.join(config.DIR_INTEGRADO, config.ARCHIVO_METADATA)
    with open(ruta_meta, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    log(f"Metadata en: {ruta_meta}")

    print("\n=== RESUMEN INTEGRACION (PREPARACION) ===")
    print(f"Filas totales: {len(df)} | Columnas: {df.shape[1]}")
    print(df.groupby(["run_name", "es_carga_normal"]).size().to_string())


if __name__ == "__main__":
    main()
