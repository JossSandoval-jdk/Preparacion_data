"""
config.py
=========
Configuracion central de la fase de PREPARACION DE DATOS (CRISP-DM) para la
deteccion de anomalias de rendimiento OLTP de SteelNort.

Define rutas base, nombres de archivo, el diccionario canonico de variables
y la lista de corridas de carga normal de referencia.

Solo preparacion de datos: NO se etiquetan anomalias aqui. Solo conocemos la
carga de trabajo; la deteccion de anomalias corresponde a la fase de Modelado.
"""

import os

# ----------------------------------------------------------------------
# Rutas base
# ----------------------------------------------------------------------
BASE_PROYECTO = os.path.dirname(os.path.abspath(__file__))

# Directorio donde viven las corridas crudas (output/) - datos originales
OUTPUT_BASE_DIR = os.getenv(
    "STEELNORT_OUTPUT_DIR",
    os.path.normpath(os.path.join(BASE_PROYECTO, "..", "output")),
)

# Directorios de salida de esta fase
DIR_DATASETS = os.path.join(BASE_PROYECTO, "datasets")
DIR_INVENTARIO = os.path.join(DIR_DATASETS, "inventario")
DIR_LIMPIO = os.path.join(DIR_DATASETS, "limpio")
DIR_INTEGRADO = os.path.join(DIR_DATASETS, "integrado")

# ----------------------------------------------------------------------
# Nombres de archivo
# ----------------------------------------------------------------------
ARCHIVO_INVENTARIO = "inventario_corridas.csv"
ARCHIVO_VARIABLES = "variables_seleccionadas.csv"
ARCHIVO_DATASET_INTEGRADO = "dataset_steelnort_preparado.csv"
ARCHIVO_DATASET_MODELO = "dataset_steelnort_preparado_modelo.csv"
ARCHIVO_METADATA = "metadata_transformaciones.json"
ARCHIVO_REPORTE_CALIDAD = "reporte_calidad_datos.csv"
ARCHIVO_VARIABLES_CLAVE = "variables_clave.csv"
ARCHIVO_DATASET_CLAVE = "dataset_carga_normal_clave.csv"
ARCHIVO_VARIABLES_PRINCIPALES = "variables_principales.csv"
ARCHIVO_DATASET_PRINCIPALES = "dataset_carga_normal_principales.csv"
ARCHIVO_DATASET_EVENTOS = "dataset_eventos.csv"
ARCHIVO_DATASET_LOGS = "dataset_logs.csv"

# Formato de los datasets intermedios por corrida
# (csv para poder inspeccionar los datos en texto plano)
FORMATO_INTERMEDIO = "csv"

# Nombres de los datasets intermedios por corrida (dentro de datasets/limpio)
NOMBRE_METRICAS_LIMPIO = "metricas_limpio.csv"
NOMBRE_EVENTS_LIMPIO = "eventos_limpio.csv"
NOMBRE_EVENTS_XE_LIMPIO = "eventos_xe_limpio.csv"
NOMBRE_SQLSERVER_LOGS_LIMPIO = "sqlserver_logs_limpio.csv"
NOMBRE_EVENTOS_PREPARADOS = "eventos_preparados.csv"
NOMBRE_LOGS_PREPARADOS = "logs_preparados.csv"
NOMBRE_TRANSFORMADO = "datos_transformados.csv"

# Nombres de los archivos de fuente dentro de cada corrida
NOMBRE_METRICAS = "metrics.log"
NOMBRE_EVENTS = "events.log"
NOMBRE_EVENTS_XE = "events_xe.log"
NOMBRE_SQLSERVER_LOGS = "sqlserver_logs.log"
NOMBRE_WORKLOAD_STATS = "workload_stats.log"

# ----------------------------------------------------------------------
# Corridas de carga normal de referencia
# ----------------------------------------------------------------------
# carga1 : captura nueva del collector corregido (sin events_xe), con carga de
#          aplicacion real (workload_stats presente). Es la carga normal de
#          referencia para entrenar el modelo de la fase de Modelado.
# En preparacion se conserva TODA la carga; esta lista solo define la
# referencia normal de entrenamiento de la fase de Modelado.
CORRIDAS_CARGA_NORMAL = ["carga1"]

# ----------------------------------------------------------------------
# Umbrales de seleccion de variables por senal
# ----------------------------------------------------------------------
# Una variable tiene senal (sirve para el modelo) si en la carga normal de
# referencia presenta suficiente variacion y cobertura de datos.
UMBRAL_NAV = 50.0   # % maximo de NaN permitido sobre la carga normal
MIN_UNICOS = 2      # minimo de valores unicos (si no, es constante -> sin senal)

# ----------------------------------------------------------------------
# VARIABLES PRINCIPALES (seleccion experta por dominio de rendimiento)
# ----------------------------------------------------------------------
# Las variables que pasan el filtro de senal (05) se reducen a las MAS
# IMPORTANTES y ESENCIALES para:
#   * deteccion de anomalias de rendimiento (aislar desviaciones),
#   * diagnostico de apoyo (que variables explican "por que" es anomalo),
#   * analisis de correlacion y reglas de motor (alertas).
#
# Se descartan las redundantes (aportan poca informacion adicional y
# corrompen la correlacion) y las de baja senal desde el dominio OLTP.
# Cada entrada: columna + justificacion de utilidad para deteccion/diagnostico.
VARIABLES_PRINCIPALES = [
    # --- Variables principales para deteccion ---
    {"columna": "cpu_usr", "rol": "cpu",
     "justificacion": "CPU modo usuario: senal directa de saturacion/computo OLTP"},
    {"columna": "cpu_sys", "rol": "cpu",
     "justificacion": "CPU modo sistema: I/O y llamadas al kernel (esperas)"},
    {"columna": "cpu_wai", "rol": "cpu",
     "justificacion": "CPU en espera de I/O: evidencia de espera del sistema"},
    {"columna": "cpu_idl", "rol": "cpu",
     "justificacion": "CPU idle: contexto para interpretar saturacion del host"},
    {"columna": "memory_used_mb", "rol": "memoria",
     "justificacion": "Memoria host usada (MB): presion de memoria del servidor"},
    {"columna": "memory_available_mb", "rol": "memoria",
     "justificacion": "Memoria host disponible (MB): margen frente a presion"},
    {"columna": "page_life_expectancy", "rol": "buffer",
     "justificacion": "Vida de paginas en buffer: presion de memoria del SQL Server"},
    {"columna": "disk_read_per_sec", "rol": "io",
     "justificacion": "Lectura de disco: satiracion de I/O (anomalias de storage)"},
    {"columna": "disk_write_per_sec", "rol": "io",
     "justificacion": "Escritura de disco: saturacion de I/O y log"},
    {"columna": "total_reads", "rol": "io_motor_sql",
     "justificacion": "Lecturas del motor SQL: cuello de botella de I/O"},
    {"columna": "total_writes", "rol": "io_motor_sql",
     "justificacion": "Escrituras del motor SQL: actividad de datos y log"},
    {"columna": "active_sessions", "rol": "sesiones",
     "justificacion": "Sesiones activas: usuarios concurrentes (contention)"},
    {"columna": "active_requests", "rol": "sesiones",
     "justificacion": "Requests en ejecucion: satiracion de trabajo concurrente"},
    {"columna": "transactions_per_sec", "rol": "transacciones",
     "justificacion": "Transacciones/seg: volumen OLTP real"},
    {"columna": "long_queries", "rol": "sesiones",
     "justificacion": "Consultas de usuario largas recalculadas desde eventos"},
    {"columna": "long_transactions", "rol": "sesiones",
     "justificacion": "Transacciones de usuario largas recalculadas desde eventos"},
    {"columna": "duration_avg_ms", "rol": "rendimiento",
     "justificacion": "Duracion promedio de consultas de usuario por ventana"},
    {"columna": "duration_max_ms", "rol": "rendimiento",
     "justificacion": "Duracion maxima de consultas de usuario por ventana"},
    {"columna": "cpu_time_sum_ms", "rol": "rendimiento",
     "justificacion": "CPU acumulada de consultas de usuario por ventana"},
    {"columna": "api_latency_ms", "rol": "api",
     "justificacion": "Latencia de la API: diagnostico de extremo a extremo"},
    {"columna": "api_status", "rol": "api",
     "justificacion": "Estado de la API: confirma si el impacto llego al usuario final"},
    {"columna": "load1", "rol": "carga",
     "justificacion": "Load 1 min: indicador reactivo de presion global del host"},
]

# Variables que PASAN el filtro de senal pero se DESCARTAN por redundancia o
# baja utilidad para deteccion/diagnostico (documentado).
VARIABLES_PRINCIPALES_DESCARTADAS = [
    {"columna": "cpu_idl", "motivo": "redundante",
     "detalle": "aprox 100 - cpu_usr - cpu_sys - cpu_wai - cpu_stl"},
    {"columna": "cpu_wai", "motivo": "baja_senal",
     "detalle": "iowait ~0 en el host, sin señal util"},
    {"columna": "memory_percent", "motivo": "redundante",
     "detalle": "correlacion ~1 con memory_used_mb"},
    {"columna": "memory_available_mb", "motivo": "redundante",
     "detalle": "= total - memory_used_mb"},
    {"columna": "load5", "motivo": "redundante",
     "detalle": "promedio lento; load1 mas reactivo"},
    {"columna": "load15", "motivo": "redundante",
     "detalle": "promedio muy lento; poca senal por muestra"},
    {"columna": "idle_sessions", "motivo": "menor_utilidad",
     "detalle": "no indica problema de rendimiento; senal debil"},
    {"columna": "buffer_cache_hit_ratio", "motivo": "medicion_incorrecta",
     "detalle": "el collector guarda cntr_value del contador 'Buffer cache hit ratio' "
               "(numerador) sin su contador base; el valor resultante (miles) no es un "
               "porcentaje real y es irrecuperable a posteriori en preparacion. Se excluye "
               "para no ensenar falsa normalidad al modelo; se requiere re-captura con "
               "correccion del collector para recuperar el ratio real (~99%)."},
]

# ----------------------------------------------------------------------
# Variables de medicion incorrecta / no confiable (excluir de seleccion)
# ----------------------------------------------------------------------
# Variables que, aunque pasen el filtro de senal (05), NO deben entrar al modelo
EXCLUIR_MEDICION_CORRUPTA = ["buffer_cache_hit_ratio"]

# ----------------------------------------------------------------------
# Diccionario canonico de variables
# ----------------------------------------------------------------------
# Cada variable: columna (nombre canonico), fuente, dominio, tipo, senal.

# A. Sistema host
FEATURES_SISTEMA = [
    {"columna": "cpu_usr", "fuente": "metrics", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "uso CPU modo usuario (%)"},
    {"columna": "cpu_sys", "fuente": "metrics", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "uso CPU modo sistema (%)"},
    {"columna": "cpu_idl", "fuente": "metrics", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "uso CPU modo idle (%)"},
    {"columna": "cpu_wai", "fuente": "metrics", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "uso CPU modo iowait (%)"},
    {"columna": "cpu_stl", "fuente": "metrics", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "uso CPU modo steal (%)"},
    {"columna": "memory_percent", "fuente": "metrics", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "memoria host usada (%)"},
    {"columna": "memory_used_mb", "fuente": "metrics", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "memoria host usada (MB)"},
    {"columna": "memory_available_mb", "fuente": "metrics", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "memoria host disponible (MB)"},
    {"columna": "disk_read_per_sec", "fuente": "metrics", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "tasa lectura de disco"},
    {"columna": "disk_write_per_sec", "fuente": "metrics", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "tasa escritura de disco"},
    {"columna": "net_send_per_sec", "fuente": "metrics", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "tasa envio de red"},
    {"columna": "net_recv_per_sec", "fuente": "metrics", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "tasa recepcion de red"},
    {"columna": "load1", "fuente": "metrics", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "carga promedio 1 min"},
    {"columna": "load5", "fuente": "metrics", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "carga promedio 5 min"},
    {"columna": "load15", "fuente": "metrics", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "carga promedio 15 min"},
]

# B. SQL Server - sesiones
FEATURES_SESIONES = [
    {"columna": "active_sessions", "fuente": "metrics", "dominio": "sesiones", "tipo": "entero",
     "senal": "sesiones activas"},
    {"columna": "active_requests", "fuente": "metrics", "dominio": "sesiones", "tipo": "entero",
     "senal": "requests en ejecucion"},
    {"columna": "long_queries", "fuente": "metrics", "dominio": "sesiones", "tipo": "entero",
     "senal": "queries > 15s"},
    {"columna": "long_transactions", "fuente": "metrics", "dominio": "sesiones", "tipo": "entero",
     "senal": "transacciones > 30s"},
    {"columna": "idle_sessions", "fuente": "metrics", "dominio": "sesiones", "tipo": "entero",
     "senal": "sesiones inactivas"},
]

# C. SQL Server - locks (generales + por tabla de negocio)
FEATURES_LOCKS = [
    {"columna": "lock_waits", "fuente": "metrics", "dominio": "locks", "tipo": "entero",
     "senal": "esperas de bloqueo"},
    {"columna": "total_locks", "fuente": "metrics", "dominio": "locks", "tipo": "entero",
     "senal": "total de locks"},
    {"columna": "deadlocks_per_sec", "fuente": "metrics", "dominio": "locks", "tipo": "entero",
     "senal": "deadlocks"},
    {"columna": "venta_locks", "fuente": "metrics", "dominio": "locks_negocio", "tipo": "entero",
     "senal": "locks tabla venta"},
    {"columna": "detalle_venta_locks", "fuente": "metrics", "dominio": "locks_negocio", "tipo": "entero",
     "senal": "locks tabla detalle_venta"},
    {"columna": "inventario_locks", "fuente": "metrics", "dominio": "locks_negocio", "tipo": "entero",
     "senal": "locks tabla inventario"},
    {"columna": "kardex_locks", "fuente": "metrics", "dominio": "locks_negocio", "tipo": "entero",
     "senal": "locks tabla kardex"},
    {"columna": "caja_locks", "fuente": "metrics", "dominio": "locks_negocio", "tipo": "entero",
     "senal": "locks tabla caja"},
    {"columna": "movimiento_caja_locks", "fuente": "metrics", "dominio": "locks_negocio", "tipo": "entero",
     "senal": "locks tabla movimiento_caja"},
    {"columna": "auditoria_locks", "fuente": "metrics", "dominio": "locks_negocio", "tipo": "entero",
     "senal": "locks tabla auditoria"},
]

# D. SQL Server - buffer / transacciones / IO
FEATURES_BUFFER = [
    {"columna": "transactions_per_sec", "fuente": "metrics", "dominio": "transacciones", "tipo": "numerico",
     "senal": "transacciones por segundo (contador -> tasa)"},
    {"columna": "total_reads", "fuente": "metrics", "dominio": "io", "tipo": "numerico",
     "senal": "lecturas de archivo acumuladas (-> tasa)"},
    {"columna": "total_writes", "fuente": "metrics", "dominio": "io", "tipo": "numerico",
     "senal": "escrituras de archivo acumuladas (-> tasa)"},
    {"columna": "page_life_expectancy", "fuente": "metrics", "dominio": "buffer", "tipo": "numerico",
     "senal": "vida esperada de paginas en buffer"},
    {"columna": "buffer_cache_hit_ratio", "fuente": "metrics", "dominio": "buffer", "tipo": "numerico",
     "senal": "ratio de acierto de cache"},
    # Contadores DMV que requieren delta pero llegan sin diff
    {"columna": "page_reads_per_sec", "fuente": "metrics", "dominio": "io", "tipo": "numerico",
     "senal": "lecturas de paginas/seg (contador - requiere delta)"},
    {"columna": "page_writes_per_sec", "fuente": "metrics", "dominio": "io", "tipo": "numerico",
     "senal": "escrituras de paginas/seg (contador - requiere delta)"},
    {"columna": "rollbacks_per_sec", "fuente": "metrics", "dominio": "transacciones", "tipo": "numerico",
     "senal": "rollbacks/seg (contador - requiere delta)"},
    {"columna": "batch_requests_per_sec", "fuente": "metrics", "dominio": "transacciones", "tipo": "numerico",
     "senal": "batch requests/seg (contador - requiere delta)"},
    {"columna": "sql_compilations_per_sec", "fuente": "metrics", "dominio": "transacciones", "tipo": "numerico",
     "senal": "compilaciones/seg (contador - requiere delta)"},
]

# E. API
FEATURES_API = [
    {"columna": "api_status", "fuente": "metrics", "dominio": "api", "tipo": "entero",
     "senal": "estado HTTP del health probe"},
    {"columna": "api_latency_ms", "fuente": "metrics", "dominio": "api", "tipo": "numerico",
     "senal": "latencia del health probe (ms)"},
    {"columna": "products_count", "fuente": "metrics", "dominio": "api", "tipo": "entero",
     "senal": "productos devueltos"},
    {"columna": "sales_count", "fuente": "metrics", "dominio": "api", "tipo": "entero",
     "senal": "ventas devueltas"},
]

# F. Eventos agregados por segundo (derivados de events.log y events_xe.log)
FEATURES_EVENTOS = [
    {"columna": "events_login_count", "fuente": "derivada", "dominio": "eventos_dmv", "tipo": "entero",
     "senal": "logins por muestra"},
    {"columna": "events_logout_count", "fuente": "derivada", "dominio": "eventos_dmv", "tipo": "entero",
     "senal": "logouts por muestra"},
    {"columna": "events_batch_count", "fuente": "derivada", "dominio": "eventos_dmv", "tipo": "entero",
     "senal": "sql_batch_completed (DMV) por muestra"},
    {"columna": "events_lock_count", "fuente": "derivada", "dominio": "eventos_dmv", "tipo": "entero",
     "senal": "lock_acquired/released por muestra"},
    {"columna": "events_wait_count", "fuente": "derivada", "dominio": "eventos_dmv", "tipo": "entero",
     "senal": "wait_info por muestra"},
    {"columna": "duration_max_ms", "fuente": "derivada", "dominio": "rendimiento", "tipo": "numerico",
     "senal": "duracion maxima de consulta en el segundo"},
    {"columna": "duration_avg_ms", "fuente": "derivada", "dominio": "rendimiento", "tipo": "numerico",
     "senal": "duracion promedio de consulta en el segundo"},
    {"columna": "query_duration_max_ms", "fuente": "derivada", "dominio": "eventos", "tipo": "numerico",
     "senal": "maximo de duration de sql_batch_completed por ventana"},
    {"columna": "query_duration_avg_ms", "fuente": "derivada", "dominio": "eventos", "tipo": "numerico",
     "senal": "promedio de duration de sql_batch_completed por ventana"},
    {"columna": "cpu_time_sum_ms", "fuente": "derivada", "dominio": "eventos", "tipo": "numerico",
     "senal": "suma de cpu_time por ventana"},
    {"columna": "logical_reads_sum", "fuente": "derivada", "dominio": "eventos", "tipo": "numerico",
     "senal": "suma de logical_reads por ventana"},
    {"columna": "writes_sum", "fuente": "derivada", "dominio": "eventos", "tipo": "numerico",
     "senal": "suma de writes por ventana"},
    {"columna": "wait_lck_count", "fuente": "derivada", "dominio": "eventos", "tipo": "entero",
     "senal": "esperas LCK_* por ventana"},
    {"columna": "wait_io_count", "fuente": "derivada", "dominio": "eventos", "tipo": "entero",
     "senal": "esperas PAGEIOLATCH_*/PAGELATCH_* por ventana"},
    {"columna": "wait_log_count", "fuente": "derivada", "dominio": "eventos", "tipo": "entero",
     "senal": "esperas WRITELOG por ventana"},
    {"columna": "distinct_sessions_count", "fuente": "derivada", "dominio": "eventos", "tipo": "entero",
     "senal": "sesiones distintas por ventana"},
    {"columna": "cpu_total", "fuente": "derivada", "dominio": "sistema_host", "tipo": "numerico",
     "senal": "cpu_usr + cpu_sys"},
    {"columna": "query_count", "fuente": "derivada", "dominio": "eventos", "tipo": "entero",
     "senal": "consultas de usuario por ventana"},
    {"columna": "wait_count", "fuente": "derivada", "dominio": "eventos", "tipo": "entero",
     "senal": "esperas de usuario por ventana"},
    {"columna": "lock_event_count", "fuente": "derivada", "dominio": "eventos", "tipo": "entero",
     "senal": "eventos de bloqueo por ventana"},
    {"columna": "error_count", "fuente": "derivada", "dominio": "eventos", "tipo": "entero",
     "senal": "errores reportados por eventos por ventana"},
    {"columna": "requests_per_session", "fuente": "derivada", "dominio": "sesiones", "tipo": "numerico",
     "senal": "active_requests / active_sessions"},
]

# H. SQL Server error log agregado por ventana de metrics.log
FEATURES_LOGS = [
    {"columna": "log_error_count", "fuente": "derivada", "dominio": "logs", "tipo": "entero",
     "senal": "errores reportados por el motor"},
    {"columna": "log_warning_count", "fuente": "derivada", "dominio": "logs", "tipo": "entero",
     "senal": "advertencias reportadas por el motor"},
    {"columna": "log_fatal_count", "fuente": "derivada", "dominio": "logs", "tipo": "entero",
     "senal": "errores fatales o criticos del motor"},
]

# G. Settings que solo se emiten cada 60s
FEATURES_SETTINGS = [
    {"columna": "max_server_memory", "fuente": "metrics", "dominio": "settings", "tipo": "numerico",
     "senal": "memoria maxima SQL Server"},
    {"columna": "user_connections_setting", "fuente": "metrics", "dominio": "settings", "tipo": "entero",
     "senal": "conexiones maximas configuradas"},
    {"columna": "cost_threshold", "fuente": "metrics", "dominio": "settings", "tipo": "entero",
     "senal": "umbral de costo de paralelismo"},
]

# Columna de texto libre (solo diagnostico, no entra al modelo)
COLUMNA_TEXTO = {"columna": "sql_text", "fuente": "derivada", "dominio": "texto", "tipo": "texto",
                 "senal": "SQL de la consulta mas lenta (diagnostico)"}

# Orden canonico de todas las variables de rendimiento (numericas)
_FEATURES = (
    FEATURES_SISTEMA + FEATURES_SESIONES + FEATURES_LOCKS
    + FEATURES_BUFFER + FEATURES_API + FEATURES_EVENTOS + FEATURES_SETTINGS
    + FEATURES_LOGS
)
FEATURES_SELECCIONADAS = [f for f in _FEATURES]


def columnas_features():
    """Lista de nombres de columnas de features (orden canonico)."""
    return [f["columna"] for f in FEATURES_SELECCIONADAS]


def columnas_principales():
    """Lista de nombres de las variables principales (seleccion experta)."""
    return [f["columna"] for f in VARIABLES_PRINCIPALES]


def columnas_contexto():
    """Columnas de contexto del dataset de preparacion (sin etiqueta de anomalia)."""
    return ["run_name", "experiment_id", "es_carga_normal"]
