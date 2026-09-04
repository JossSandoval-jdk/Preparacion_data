"""
02_limpieza.py: Paso 2 del Pipeline (Limpieza de Datos).
Estandariza los logs crudos convirtiéndolos a formatos tabulares (CSV).
Aplica técnicas de limpieza: manejo de nulos, eliminación de duplicados,
coerción de tipos y categorización de eventos SQL Server.
"""

import json # Importado para leer archivos JSON
import os   # Para manejo de rutas de archivos
import re   # Para expresiones regulares (buscar patrones en texto)
import pandas as pd # Para manipular los datos como tablas
import config # Tu archivo de configuración central

# Función para imprimir logs de progreso
def log(msg):
    print(f"[LIMPIEZA] {msg}", flush=True)

# ----------------------------------------------------------------------
# Parsers: Lógica de transformación específica por cada tipo de log
# ----------------------------------------------------------------------

# Patrón Regex para buscar: (fecha hora) (espacios) (nombre_metrica) (espacios) (valor)
_RE_METRICS = re.compile(r"^(\S+\s+\S+)\s{2,}(\S+)\s+(\S+)$")

def limpiar_metrics(ruta):
    """Parsea el log de métricas y fuerza tipos numéricos."""
    registros = []
    descartadas = 0
    no_numericas = 0
    
    # Abrimos el archivo log para leerlo línea a línea
    with open(ruta, encoding="utf-8", errors="replace") as f:
        for i, linea in enumerate(f):
            if i == 0: continue # Saltamos la cabecera del archivo
            linea = linea.strip() # Quitamos espacios en blanco extra
            if not linea: continue
            
            # Intentamos aplicar el patrón Regex
            m = _RE_METRICS.match(linea)
            if not m:
                descartadas += 1 # Si no sigue el patrón, descartamos la línea
                continue

            ts, metrica, valor = m.group(1), m.group(2), m.group(3)
            try:
                valor = float(valor) # Convertimos el valor de texto a número decimal
            except ValueError:
                no_numericas += 1 # Si no es un número, descartamos
                continue
            # Guardamos timestamp, nombre métrica y valor limpio
            registros.append((pd.Timestamp(ts), metrica, valor))

    # Creamos un DataFrame con los datos limpios
    df = pd.DataFrame(registros, columns=["timestamp", "metrica", "valor"])
    return df, {"descartadas": descartadas, "no_numericas": no_numericas}

def limpiar_events(ruta):
    """Procesa logs JSON: extrae datos, quita duplicados y normaliza fechas."""
    registros = []
    malformados = 0
    duplicados = set() # Usamos un set para rastrear qué hemos visto ya
    vistos = set()
    
    with open(ruta, encoding="utf-8", errors="replace") as f:
        for linea in f:
            linea = linea.strip()
            if not linea: continue
            try:
                obj = json.loads(linea) # Convertimos la línea JSON en diccionario de Python
            except json.JSONDecodeError:
                malformados += 1 # Si el JSON está roto, lo contamos como error
                continue

            # Verificación de duplicados basada en la línea original
            clave = linea
            if clave in vistos: duplicados.add(clave)
            vistos.add(clave)
            obj["_linea"] = clave
            registros.append(obj)

    df = pd.DataFrame(registros)
    # Convertimos la columna de tiempo a formato fecha de Pandas
    if not df.empty and "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    
    # Clasificamos qué tipo de evento es usando la función externa
    if not df.empty:
        df["process_type"] = df.apply(clasificar_evento, axis=1)
    return df, {"malformados": malformados, "duplicados": len(duplicados)}

def limpiar_events_xe(ruta):
    """Reutiliza la lógica de eventos para eventos XE."""
    return limpiar_events(ruta)

# Lista de comandos que identificamos como tareas internas de SQL Server
EVENTOS_SQL_SERVER_INTERNOS = {
    "TASK MANAGER", "TRACE QUEUE TASK", "SYSTEM_HEALTH_MONITOR",
    "ONDEMAND_TASK_QUEUE", "BRKR TASK", "CHECKPOINT",
    "HADR_AR_MGR_NOTIFICATION_WORKER",
}

def clasificar_evento(evento):
    """Lógica de negocio: decide si un evento es del usuario o del sistema."""
    command = str(evento.get("command") or "").strip().upper()
    event_name = str(evento.get("event_name") or "").strip().lower()
    
    # Si es interno de SQL, lo marcamos como SQL_SERVER_INTERNAL
    if command in EVENTOS_SQL_SERVER_INTERNOS:
        return "SQL_SERVER_INTERNAL"
    
    # Si son eventos de login/lock, los marcamos como desconocidos
    if event_name in {"login", "logout", "lock_acquired", "lock_released",
                      "wait_info", "xml_deadlock_report", "error_reported"}:
        return "UNKNOWN"
    
    # Si el comando es SQL de usuario y la base de datos es la nuestra (steelnort)
    if command.startswith(("SELECT", "EXECUTE", "INSERT", "UPDATE", "DELETE",
                           "MERGE", "CALL")):
        database = str(evento.get("database_name") or "").strip().lower()
        if database in {"steelnort", ""}:
            return "USER" # Marcado como evento de usuario
    return "UNKNOWN"

def limpiar_sqlserver_logs(ruta):
    """Procesa el log de errores de SQL Server, extrayendo niveles de severidad."""
    registros = []
    descartadas = 0
    with open(ruta, encoding="utf-8", errors="replace") as f:
        for linea in f:
            linea = linea.rstrip("\n")
            if not linea.strip(): continue
            
            # Regex para extraer fecha, proceso y mensaje del log
            m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s+(\S+)\s+(.*)$", linea)
            if not m:
                descartadas += 1
                continue
            
            mensaje = m.group(3)
            registros.append({
                "timestamp": pd.Timestamp(m.group(1)),
                "proceso": m.group(2),
                "error_level": "", # Campo vacío inicial para rellenar después
                "error_message": mensaje,
                "mensaje": mensaje,
            })
            
    df = pd.DataFrame(registros)
    if not df.empty:
        # Extraemos el nivel de severidad del mensaje usando regex
        texto = df["error_message"].str.lower()
        severidad = texto.str.extract(r"severity\s*(?:level)?\s*[:=]?\s*(\d+)", expand=False)
        severidad = pd.to_numeric(severidad, errors="coerce")
        df["error_level"] = severidad
        
        # Clasificación por categorías basándonos en palabras clave en el mensaje
        df["log_category"] = "INFO"
        df.loc[texto.str.contains("start|startup|starting|recovery|ready for client", regex=True), "log_category"] = "STARTUP"
        df.loc[texto.str.contains("configuration|configured|setting|parameter", regex=True), "log_category"] = "CONFIGURATION"
        df.loc[texto.str.contains("warning|advertencia", regex=True), "log_category"] = "WARNING"
        df.loc[texto.str.contains("performance|slow|timeout|latency", regex=True), "log_category"] = "PERFORMANCE"
        df.loc[texto.str.contains("fatal", regex=False) | severidad.between(20, 25), "log_category"] = "FATAL"
        df.loc[texto.str.contains("error", regex=False), "log_category"] = "ERROR"
    return df, {"descartadas": descartadas}

# ----------------------------------------------------------------------
# Limpieza por corrida
# ----------------------------------------------------------------------
def limpiar_corrida(corrida):
    """Función maestra que ejecuta la limpieza de todos los archivos de una corrida."""
    dir_corrida = os.path.join(config.OUTPUT_BASE_DIR, corrida)
    dir_salida = os.path.join(config.DIR_LIMPIO, corrida)
    os.makedirs(dir_salida, exist_ok=True) # Creamos carpeta de salida para la corrida

    resumen = {"corrida": corrida}

    # Procesar métricas
    ruta_m = os.path.join(dir_corrida, config.NOMBRE_METRICAS)
    if os.path.exists(ruta_m):
        df_m, info = limpiar_metrics(ruta_m)
        df_m.to_csv(os.path.join(dir_salida, config.NOMBRE_METRICAS_LIMPIO), index=False, encoding="utf-8-sig")
        resumen.update({"metrics_validas": len(df_m), "metrics_descartadas": info["descartadas"], "metrics_no_numericas": info["no_numericas"]})
        log(f"   metrics: validas={len(df_m)} descartadas={info['descartadas']} no_numericas={info['no_numericas']}")

    # Procesar eventos generales
    ruta_e = os.path.join(dir_corrida, config.NOMBRE_EVENTS)
    if os.path.exists(ruta_e):
        df_e, info = limpiar_events(ruta_e)
        df_e.to_csv(os.path.join(dir_salida, config.NOMBRE_EVENTS_LIMPIO), index=False, encoding="utf-8-sig")
        df_e.to_csv(os.path.join(dir_salida, config.NOMBRE_EVENTOS_PREPARADOS), index=False, encoding="utf-8-sig")
        resumen.update({"events_validos": len(df_e), "events_malformados": info["malformados"], "events_duplicados": info["duplicados"]})
        log(f"   events.log: validos={len(df_e)} malformados={info['malformados']} duplicados={info['duplicados']}")

    # Procesar eventos XE (Extended Events)
    ruta_x = os.path.join(dir_corrida, config.NOMBRE_EVENTS_XE)
    if os.path.exists(ruta_x):
        df_x, info = limpiar_events_xe(ruta_x)
        if len(df_x) > 0:
            df_x.to_csv(os.path.join(dir_salida, config.NOMBRE_EVENTS_XE_LIMPIO), index=False, encoding="utf-8-sig")
        resumen.update({"xe_validos": len(df_x), "xe_malformados": info["malformados"], "xe_duplicados": info["duplicados"]})
        log(f"   events_xe.log: validos={len(df_x)} malformados={info['malformados']} duplicados={info['duplicados']}")

    # Procesar Logs SQL Server
    ruta_s = os.path.join(dir_corrida, config.NOMBRE_SQLSERVER_LOGS)
    if os.path.exists(ruta_s):
        df_s, info = limpiar_sqlserver_logs(ruta_s)
        df_s.to_csv(os.path.join(dir_salida, config.NOMBRE_SQLSERVER_LOGS_LIMPIO), index=False, encoding="utf-8-sig")
        df_s.to_csv(os.path.join(dir_salida, config.NOMBRE_LOGS_PREPARADOS), index=False, encoding="utf-8-sig")
        resumen.update({"sqlserver_validas": len(df_s), "sqlserver_descartadas": info["descartadas"]})
        log(f"   sqlserver_logs.log: validas={len(df_s)} descartadas={info['descartadas']}")

    return resumen

def main():
    if not os.path.isdir(config.OUTPUT_BASE_DIR):
        log(f"Directorios de datos no encontrado: {config.OUTPUT_BASE_DIR}")
        return

    # Obtenemos lista de corridas
    corridas = sorted([
        d for d in os.listdir(config.OUTPUT_BASE_DIR)
        if os.path.isdir(os.path.join(config.OUTPUT_BASE_DIR, d))
    ])
    log(f"Corridas a limpiar ({len(corridas)}): {corridas}")

    # Ejecutamos limpieza por cada una
    resumenes = []
    for corrida in corridas:
        log(f"-- Limpiando corrida: {corrida}")
        resumenes.append(limpiar_corrida(corrida))

    # Generamos un archivo de resumen global final
    df_resumen = pd.DataFrame(resumenes)
    os.makedirs(config.DIR_LIMPIO, exist_ok=True)
    ruta = os.path.join(config.DIR_LIMPIO, "resumen_limpieza_global.csv")
    df_resumen.to_csv(ruta, index=False, encoding="utf-8-sig")
    log(f"Resumen global en: {ruta}")

    print("\n=== RESUMEN LIMPIEZA GLOBAL ===")
    cols = ["corrida", "metrics_validas", "events_validos", "events_duplicados",
            "xe_validos", "xe_duplicados", "sqlserver_validas"]
    print(df_resumen[cols].to_string(index=False))


if __name__ == "__main__":
    main()
