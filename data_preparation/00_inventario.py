"""
00_inventario.py
================
Paso 0 de la preparacion de datos (CRISP-DM): inventario de corridas y fuentes.

Recorre OUTPUT_BASE_DIR, identifica cada corrida (subcarpeta) y, para cada
fuente (metrics.log, events.log, events_xe.log, sqlserver_logs.log,
workload_stats.log), registra si existe y cuantas lineas tiene.

Salida: datasets/inventario/inventario_corridas.csv
"""

import os

import pandas as pd

import config


def log(msg):
    print(f"[INVENTARIO] {msg}", flush=True)


def contar_lineas(ruta):
    try:
        with open(ruta, encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def main():
    if not os.path.isdir(config.OUTPUT_BASE_DIR):
        log(f"Directorios de datos no encontrado: {config.OUTPUT_BASE_DIR}")
        return

    corridas = sorted([
        d for d in os.listdir(config.OUTPUT_BASE_DIR)
        if os.path.isdir(os.path.join(config.OUTPUT_BASE_DIR, d))
    ])
    log(f"Corridas encontradas ({len(corridas)}): {corridas}")

    fuentes = [
        config.NOMBRE_METRICAS,
        config.NOMBRE_EVENTS,
        config.NOMBRE_EVENTS_XE,
        config.NOMBRE_SQLSERVER_LOGS,
        config.NOMBRE_WORKLOAD_STATS,
    ]

    registros = []
    for corrida in corridas:
        dir_corrida = os.path.join(config.OUTPUT_BASE_DIR, corrida)
        for fuente in fuentes:
            ruta = os.path.join(dir_corrida, fuente)
            existe = os.path.exists(ruta)
            registros.append({
                "corrida": corrida,
                "fuente": fuente,
                "existe": existe,
                "lineas": contar_lineas(ruta) if existe else 0,
            })

    df = pd.DataFrame(registros)
    os.makedirs(config.DIR_INVENTARIO, exist_ok=True)
    ruta_salida = os.path.join(config.DIR_INVENTARIO, config.ARCHIVO_INVENTARIO)
    df.to_csv(ruta_salida, index=False, encoding="utf-8-sig")
    log(f"Inventario guardado en: {ruta_salida}")

    print("\n=== RESUMEN INVENTARIO ===")
    piv = df.pivot(index="corrida", columns="fuente", values="existe")
    print(piv.to_string())
    print(f"\nTotal registros (corridas x fuentes): {len(df)}")


if __name__ == "__main__":
    main()
