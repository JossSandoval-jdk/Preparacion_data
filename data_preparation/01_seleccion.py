"""
01_seleccion.py: Paso 1 del Pipeline (Selección de Variables).
Crea un catálogo centralizado de las variables que serán extraídas,
basándose en el diccionario de características definido en la configuración.
"""

import os
import pandas as pd
import config # Importa el diccionario de configuración con las variables permitidas

def log(msg):
    print(f"[SELECCION] {msg}", flush=True)

def main():
    # Estructura la lista de variables a partir de la configuración
    filas = []
    for f in config.FEATURES_SELECCIONADAS:
        filas.append({
            "columna": f["columna"],
            "fuente": f["fuente"],
            "dominio": f["dominio"],
            "tipo": f["tipo"],
            "senal": f["senal"],
        })

    # Crea el DataFrame con el catálogo de variables
    df = pd.DataFrame(filas)
    
    # Asegura la existencia del directorio y guarda el catálogo como CSV
    os.makedirs(config.DIR_INVENTARIO, exist_ok=True)
    ruta_salida = os.path.join(config.DIR_INVENTARIO, config.ARCHIVO_VARIABLES)
    df.to_csv(ruta_salida, index=False, encoding="utf-8-sig")
    
    # Registro de éxito en consola
    log(f"Variables seleccionadas: {len(df)}")
    log(f"Guardado en: {ruta_salida}")

    # Resumen estadístico para validación rápida
    print("\n=== RESUMEN SELECCION POR GRUPO ===")
    print(df.groupby("dominio").size().to_string())


if __name__ == "__main__":
    main()
