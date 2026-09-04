# Preparación de datos para la detección y diagnóstico de anomalías de rendimiento

## Fuente de datos

Para el desarrollo del proyecto se utilizaron tres fuentes principales de
información relacionadas con el comportamiento y funcionamiento de SQL Server:
las métricas de rendimiento, los eventos generados por el motor de base de
datos y los registros del sistema o logs. Estas fuentes proporcionan
información complementaria para la detección de anomalías de rendimiento, el
diagnóstico de sus posibles causas y el apoyo a la toma de decisiones.

| Fuente | Cantidad de registros válidos |
|---|---:|
| Métricas de rendimiento | 5.262 |
| Eventos de SQL Server | 1.448 |
| Logs de SQL Server | 305 |
| **Total** | **7.015** |

Las métricas describen el consumo de recursos del host, la actividad de SQL
Server y la respuesta de la API. Los eventos permiten identificar consultas,
sesiones, esperas y bloqueos ocurridos durante la ejecución de las cargas de
trabajo. Los logs aportan información textual sobre el estado, inicio,
configuración, advertencias y errores reportados por el motor.

Se utilizaron las corridas `carga1` y `carga2`. La corrida `carga1` se mantuvo
como referencia normal para el filtrado de señal y el dataset destinado al
modelado, mientras que `carga2` se conservó para ampliar el conjunto integrado
y comparar comportamientos.

## Selección de datos y variables

A partir de las fuentes recopiladas se construyó un catálogo de **72 variables
numéricas canónicas**. La selección cubre las principales dimensiones del
rendimiento del sistema:

- CPU, memoria y carga global del host.
- Lecturas, escrituras y actividad de I/O.
- Tráfico de red y respuesta de la API.
- Sesiones, solicitudes y transacciones.
- Consultas largas, bloqueos y esperas.
- Vida de páginas y estado del buffer de SQL Server.
- Conteos y agregados derivados de eventos.
- Conteos derivados de mensajes del error log.

La selección se realizó progresivamente. Primero se conservaron las variables
disponibles en el catálogo canónico. Después se revisó su señal sobre `carga1`,
considerando la cobertura de datos y la variabilidad. El resultado fue de 41
variables con señal suficiente. Finalmente, se definieron 22 variables
principales según su utilidad para detectar y diagnosticar cambios de
rendimiento.

Las decisiones aplicadas a cada variable quedaron registradas en
`variables_clave.csv` mediante `decision_modelo` y `motivo_decision`:

| Situación de la variable | Decisión |
|---|---|
| Todos los valores disponibles son `0` | Eliminar del conjunto dinámico del modelo |
| Tiene un único valor constante distinto de `0` | Eliminar del conjunto dinámico del modelo |
| Supera el límite de valores `NaN` | Eliminar del conjunto dinámico del modelo |
| Presenta poca variabilidad | Evaluar según su utilidad y contexto |
| Presenta variabilidad suficiente | Mantener |
| Tiene `NaN` únicamente en la primera muestra por `delta/dt` | Mantener y tratar según el modelo |
| Es una variable de configuración con pocos valores | No usar como variable dinámica |
| Aporta información diagnóstica y tiene señal | Mantener para diagnóstico |

Las variables constantes, con demasiados valores faltantes o con mediciones no
confiables se excluyeron del conjunto analítico correspondiente, pero no se
eliminaron necesariamente de los archivos originales. Un valor igual a cero
no se descartó automáticamente, porque puede representar ausencia real de
actividad, como cero bloqueos, cero errores o cero escrituras en una ventana.

## Limpieza de datos

La limpieza se realizó por separado para cada fuente antes de integrarlas.

En las métricas se validó el formato de las líneas, se normalizaron las marcas
temporales y se convirtieron los valores a formato numérico. Se descartaron
únicamente líneas con formato inválido o valores no numéricos. Las métricas
acumulativas `total_reads` y `total_writes` se conservaron en la fuente y
posteriormente se transformaron a tasas mediante `delta/dt`. La primera
muestra de cada corrida puede quedar sin tasa porque no existe una muestra
anterior de referencia.

En los eventos se verificó que cada línea fuera un JSON válido, se controlaron
los duplicados y se normalizó el campo `timestamp`. Los eventos se clasificaron
según el origen que puede inferirse de la información disponible:

- `SQL_SERVER_INTERNAL`: tareas propias del motor, como `TASK MANAGER`,
  `CHECKPOINT`, `BRKR TASK` o `SYSTEM_HEALTH_MONITOR`.
- `UNKNOWN`: eventos cuyo origen no puede determinarse con suficiente evidencia.

En los logs se validó el formato de fecha, proceso y mensaje. El contenido se
normalizó en los campos `timestamp`, `proceso`, `error_level`,
`error_message` y `log_category`. Los mensajes se clasificaron como `INFO`,
`STARTUP`, `CONFIGURATION`, `WARNING`, `ERROR`, `FATAL` o `PERFORMANCE`.

Los mensajes de inicio o información del servidor, como `SQL Server is
starting`, `SQL Server detected...` y `SQL Server is starting at normal
priority`, no se consideraron errores ni anomalías de rendimiento. Asimismo,
un mensaje clasificado como `ERROR` se conserva como evidencia, pero no implica
por sí solo que exista una anomalía: su relevancia debe verificarse con la
proximidad temporal de las métricas y eventos.

## Construcción de datos

Después de la limpieza, las métricas registradas en formato longitudinal se
transformaron a una estructura amplia. Cada fila representa una observación
temporal y cada columna representa una métrica o variable derivada.

A partir de `events.log` se generaron agregados por ventana temporal, utilizando
como referencia las muestras de `metrics.log`. Entre las variables derivadas se
incluyen:

- `cpu_total`: suma de `cpu_usr` y `cpu_sys`.
- `query_count`: cantidad de consultas de usuario.
- `events_batch_count`: cantidad de lotes completados.
- `query_duration_avg_ms` y `query_duration_max_ms`.
- `cpu_time_sum_ms`, `logical_reads_sum` y `writes_sum`.
- `wait_count`, `wait_lck_count`, `wait_io_count` y `wait_log_count`.
- `lock_event_count` y `error_count`.
- `distinct_sessions_count`.
- `requests_per_session`.
- `log_error_count`, `log_warning_count` y `log_fatal_count`.

Las consultas y transacciones largas se recalcularon utilizando eventos
clasificados como `USER`. De esta forma, las actividades internas de SQL
Server no contaminan los indicadores de carga de usuario. En las capturas
actuales no existen eventos explícitos de inicio y confirmación de transacción;
por ello, el indicador de transacciones largas se interpreta como un proxy
basado en la duración de la actividad de usuario y debe validarse en futuras
capturas con mayor contexto transaccional.

## Integración de datos

Las fuentes transformadas se relacionaron mediante `timestamp`. Como las
frecuencias de captura son diferentes, los eventos y mensajes se asignaron a la
siguiente muestra de `metrics.log`, formando una ventana temporal consistente.

La integración permite analizar una secuencia como la siguiente:

```text
Métrica con comportamiento inusual
        -> evento relacionado
        -> consulta, espera o bloqueo
        -> mensaje de SQL Server, si existe
        -> evidencia para el diagnóstico
```

La relación no se establece únicamente por similitud de valores. También se
consideran la proximidad temporal y, cuando están disponibles, `session_id`,
`database_name`, `command`, `sql_text`, `proceso`, `resource_type` y `mode`.

La integración numérica produjo un dataset de **117 observaciones y 76
columnas**, compuesto por el timestamp, 72 variables canónicas y tres campos
de contexto: `run_name`, `experiment_id` y `es_carga_normal`.

## Formateo

Finalmente, los datos se organizaron en CSV para facilitar su inspección,
trazabilidad y uso posterior en el modelado. Se mantuvieron separados los
datos numéricos de los registros textuales de diagnóstico:

- `dataset_steelnort_preparado.csv`: métricas originales y variables numéricas
  derivadas.
- `dataset_steelnort_preparado_modelo.csv`: versión filtrada con las 41
  variables que tienen decisión `MANTENER`; excluye constantes, variables con
  demasiados `NaN` y mediciones no confiables.
- `dataset_eventos.csv`: 1.448 eventos con contexto de sesión, consulta,
  duración, CPU, lecturas, escrituras, esperas, bloqueos y `process_type`.
- `dataset_logs.csv`: 305 mensajes del motor con `timestamp`, `proceso`,
  `error_level`, `error_message`, `log_category` y `run_name`.
- `dataset_carga_normal_principales.csv`: 62 observaciones de `carga1` con las
  22 variables principales y el contexto de entrenamiento.

Separar eventos y logs evita mezclar texto libre con las variables numéricas
utilizadas por el modelo, sin perder la evidencia necesaria para el
 diagnóstico.

## Justificación de las transformaciones

Las transformaciones se realizaron para convertir información heterogénea en
un conjunto consistente y analizable. La reorganización de las métricas
permite representar la evolución temporal del sistema. El cálculo de tasas
para variables acumulativas evita interpretar como actividad reciente un valor
que representa el total desde el inicio de la medición.

La agregación de eventos incorpora el contexto operativo de cada intervalo,
mientras que la clasificación de eventos permite diferenciar la carga de
usuario de las tareas internas del motor. La normalización de los logs permite
conservar los mensajes completos y, al mismo tiempo, obtener categorías
numéricas que pueden relacionarse con las métricas.

La selección progresiva reduce redundancias y variables sin señal suficiente,
pero mantiene los archivos originales para conservar trazabilidad. Los valores
extremos tampoco se eliminan automáticamente, ya que pueden representar
anomalías reales o comportamientos legítimos de la carga.

## Alcance de la detección

Esta fase corresponde a **Data Preparation**. No se asignan etiquetas
`is_anomaly` ni se establecen reglas arbitrarias como `CPU > 80%`. La columna
`es_carga_normal` únicamente identifica la referencia utilizada para el
entrenamiento.

Los criterios definitivos de detección deben establecerse posteriormente con
la línea base normal, el comportamiento histórico, el análisis estadístico y
la evaluación del método de modelado. El resultado de esta preparación deja
los datos listos para el flujo:

**Detección -> Diagnóstico -> Apoyo a la decisión**.
