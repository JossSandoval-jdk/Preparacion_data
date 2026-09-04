"""
06_seleccion_variables_principales.py
=====================================
Paso 6 de la preparacion de datos (CRISP-DM): seleccion final de las
variables PRINCIPALES (expert-driven por dominio de rendimiento).

Parte de las variables que pasaron el filtro de senal (variables_clave.csv) y
las reduce a las MAS IMPORTANTES y ESENCIALES para:
  * deteccion de anomalias de rendimiento (aislar desviaciones),
  * diagnostico de apoyo (que variables explican "por que" es anomalo),
  * analisis de correlacion y reglas de motor (alertas).

Se descartan redundancias (cpu_idl, memory_available_mb, load5/15, ...) que
corrompen la correlacion y aportan poca informacion.

Salidas:
  datasets/integrado/variables_principales.csv    (justificacion trazable)
  datasets/integrado/dataset_carga_normal_principales.csv
      (carga normal de referencia, solo variables principales + contexto)
"""

import os

import pandas as pd

import config


def log(msg):
    print(f"[PRINCIPALES] {msg}", flush=True)


def main():
    # Base: dataset de carga normal con las variables clave (tras 05)
    ruta = os.path.join(config.DIR_INTEGRADO, config.ARCHIVO_DATASET_CLAVE)
    if not os.path.exists(ruta):
        log(f"Falta {ruta}. Ejecuta 05_seleccion_variables_clave.py.")
        return
    df = pd.read_csv(ruta, encoding="utf-8-sig")
    ruta_integrado = os.path.join(config.DIR_INTEGRADO,
                                  config.ARCHIVO_DATASET_INTEGRADO)
    df_integrado = pd.read_csv(ruta_integrado, encoding="utf-8-sig")
    normal_integrado = df_integrado[
        df_integrado["run_name"].isin(config.CORRIDAS_CARGA_NORMAL)
    ]

    # Seleccion traducible de variables principales
    filas = []
    for f in config.VARIABLES_PRINCIPALES:
        filas.append({
            "columna": f["columna"],
            "rol": f["rol"],
            "justificacion": f["justificacion"],
        })
    df_vars = pd.DataFrame(filas)
    ruta_vars = os.path.join(config.DIR_INTEGRADO,
                             config.ARCHIVO_VARIABLES_PRINCIPALES)
    df_vars.to_csv(ruta_vars, index=False, encoding="utf-8-sig")
    log(f"Seleccion en: {ruta_vars}")

    # Reporte de descartes (las que estaban en clave pero no son principales)
    clave = pd.read_csv(os.path.join(config.DIR_INTEGRADO,
                                     config.ARCHIVO_VARIABLES_CLAVE),
                        encoding="utf-8-sig")
    clave_cols = set(clave[clave["senal"] == "CLAVE"]["columna"])
    principales = set(config.columnas_principales())
    # Descartadas por redundancia/baja utilidad: las que pasaron el filtro de
    # senal (CLAVE) pero no son principales.
    descartadas = [
        {
            "columna": c,
            "motivo": next((d["motivo"] for d in config.VARIABLES_PRINCIPALES_DESCARTADAS
                            if d["columna"] == c), "no_principal"),
            "detalle": next((d["detalle"] for d in config.VARIABLES_PRINCIPALES_DESCARTADAS
                             if d["columna"] == c), ""),
        }
        for c in sorted(clave_cols - principales)
    ]
    # Ademas, las excluidas por medicion incorrecta (irrecuperables) aunque no
    # pasaran el filtro de senal: se dejan trazadas con su motivo.
    excluidas_medicion = [
        {
            "columna": c,
            "motivo": next((d["motivo"] for d in config.VARIABLES_PRINCIPALES_DESCARTADAS
                            if d["columna"] == c), "medicion_incorrecta"),
            "detalle": next((d["detalle"] for d in config.VARIABLES_PRINCIPALES_DESCARTADAS
                             if d["columna"] == c), ""),
        }
        for c in config.EXCLUIR_MEDICION_CORRUPTA
        if c not in principales
    ]
    descartadas = descartadas + excluidas_medicion
    df_desc = pd.DataFrame(descartadas)
    ruta_desc = os.path.join(config.DIR_INTEGRADO, "variables_principales_descartadas.csv")
    df_desc.to_csv(ruta_desc, index=False, encoding="utf-8-sig")
    log(f"Descartes en: {ruta_desc}")

    # Dataset final: solo variables principales + contexto sobre la carga normal
    cols = ["timestamp"] + config.columnas_principales() + config.columnas_contexto()
    df_final = df.copy()
    for col in config.columnas_principales():
        if col not in df_final.columns:
            df_final[col] = normal_integrado.set_index("timestamp")[col].reindex(
                pd.to_datetime(df_final["timestamp"])
            ).to_numpy()
    df_final = df_final[cols].copy()
    ruta_ds = os.path.join(config.DIR_INTEGRADO, config.ARCHIVO_DATASET_PRINCIPALES)
    df_final.to_csv(ruta_ds, index=False, encoding="utf-8-sig")
    log(f"Dataset de variables principales en: {ruta_ds} "
        f"({df_final.shape[0]} filas x {df_final.shape[1]} cols)")

    print("\n=== VARIABLES PRINCIPALES FINALES ===")
    print(df_vars[["columna", "rol"]].to_string(index=False))
    print(f"\nTotal principales: {len(df_vars)}")
    print(f"\n=== DESCARTADAS (por redundancia/baja utilidad) ===")
    print(df_desc.to_string(index=False))


if __name__ == "__main__":
    main()
