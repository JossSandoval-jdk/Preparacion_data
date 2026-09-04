"""
05_seleccion_variables_clave.py
===============================
Paso 5 de la preparacion de datos (CRISP-DM): seleccion de las variables MAS
CLAVE por senal en la carga normal de referencia.

El dataset integrado mantiene TODAS las variables candidatas. Con datos
limitados es necesario quedarse con las variables que realmente aportan senal
para que el modelo (fase de Modelado) sea viable y no memorice (sobreajuste).

Criterio de senal sobre la carga normal (config.CORRIDAS_CARGA_NORMAL):
  1. la variable debe estar presente en los datos (existir en el dataset);
  2. pct de NaN <= UMBRAL_NAV (50%);
  3. numero de valores unicos >= MIN_UNICOS (2) -> no constante.

Salidas:
  datasets/integrado/variables_clave.csv               (seleccion trazable)
  datasets/integrado/dataset_carga_normal_clave.csv    (test_run, solo clave)
"""

import os

import numpy as np
import pandas as pd

import config


def log(msg):
    print(f"[CLAVE] {msg}", flush=True)


def main():
    ruta_integrado = os.path.join(config.DIR_INTEGRADO,
                                  config.ARCHIVO_DATASET_INTEGRADO)
    if not os.path.exists(ruta_integrado):
        log(f"Falta el dataset integrado: {ruta_integrado}. Ejecuta 04.")
        return

    df = pd.read_csv(ruta_integrado, encoding="utf-8-sig")

    # Subconjunto de carga normal de referencia
    normal = df[df["run_name"].isin(config.CORRIDAS_CARGA_NORMAL)].copy()
    log(f"Carga normal ({config.CORRIDAS_CARGA_NORMAL}): {len(normal)} muestras")

    feats = config.columnas_features()
    n = len(normal)

    filas = []
    for col in feats:
        if col not in df.columns:
            filas.append({"columna": col, "presente": False, "senal": "NO_PRESENTE",
                          "nulos_pct": np.nan, "unicos": 0, "media": np.nan,
                          "decision_modelo": "ELIMINAR",
                          "motivo_decision": "variable no presente"})
            continue
        s = normal[col]
        nulos_pct = round(float(s.isna().mean() * 100), 2)
        unicos = int(s.nunique(dropna=True))
        no_nulos = s.dropna()
        media = round(float(no_nulos.mean()), 4) if len(no_nulos) else np.nan

        if col in config.EXCLUIR_MEDICION_CORRUPTA:
            # medicion incorrecta en el collector, irrecuperable: se excluye
            # aunque tenga senal (no ensena falsa normalidad al modelo)
            senal = "DESCARTADA_MEDICION"
            decision = "ELIMINAR"
            motivo = "medicion no confiable"
        elif nulos_pct > config.UMBRAL_NAV:
            senal = "MUCHO_NAN"
            decision = "ELIMINAR"
            motivo = "supera el limite de valores NaN"
        elif unicos < config.MIN_UNICOS:
            senal = "CONSTANTE"
            decision = "ELIMINAR"
            if unicos and float(no_nulos.iloc[0]) == 0:
                motivo = "todos los valores disponibles son 0"
            else:
                motivo = "un unico valor constante distinto de 0"
        else:
            senal = "CLAVE"
            decision = "MANTENER"
            if nulos_pct > 0:
                motivo = "senal suficiente; NaN inicial esperado por delta/dt"
            else:
                motivo = "variabilidad suficiente o utilidad diagnostica"

        filas.append({"columna": col, "presente": True, "senal": senal,
                      "nulos_pct": nulos_pct, "unicos": unicos, "media": media,
                      "decision_modelo": decision, "motivo_decision": motivo})

    df_selec = pd.DataFrame(filas)
    os.makedirs(config.DIR_INTEGRADO, exist_ok=True)
    ruta_var = os.path.join(config.DIR_INTEGRADO, config.ARCHIVO_VARIABLES_CLAVE)
    df_selec.to_csv(ruta_var, index=False, encoding="utf-8-sig")
    log(f"Seleccion en: {ruta_var}")

    clave = df_selec[df_selec["senal"] == "CLAVE"]["columna"].tolist()
    log(f"Variables clave: {len(clave)} de {len(feats)}")

    # Dataset para modelado: solo variables con decision explicita de mantener.
    mantener = df_selec[df_selec["decision_modelo"] == "MANTENER"]["columna"].tolist()
    cols_modelo = ["timestamp"] + mantener + config.columnas_contexto()
    df_modelo = df[cols_modelo].copy()
    ruta_modelo = os.path.join(config.DIR_INTEGRADO,
                               config.ARCHIVO_DATASET_MODELO)
    df_modelo.to_csv(ruta_modelo, index=False, encoding="utf-8-sig")
    log(f"Dataset para modelado en: {ruta_modelo} "
        f"({df_modelo.shape[0]} filas x {df_modelo.shape[1]} cols)")

    # Dataset reducido: carga normal, solo variables clave + contexto + timestamp
    cols_salida = ["timestamp"] + clave + config.columnas_contexto()
    df_clave = normal[cols_salida].copy()
    ruta_ds = os.path.join(config.DIR_INTEGRADO, config.ARCHIVO_DATASET_CLAVE)
    df_clave.to_csv(ruta_ds, index=False, encoding="utf-8-sig")
    log(f"Dataset carga normal clave en: {ruta_ds} "
        f"({df_clave.shape[0]} filas x {df_clave.shape[1]} cols)")

    print("\n=== VARIABLES CLAVE (con senal) ===")
    print(df_selec[df_selec["senal"] == "CLAVE"]
          [["columna", "nulos_pct", "unicos", "media"]].to_string(index=False))

    print(f"\n=== VARIABLES DESCARTADAS ({len(df_selec)-len(clave)}) ===")
    print(df_selec.groupby("senal").size().to_string())


if __name__ == "__main__":
    main()
