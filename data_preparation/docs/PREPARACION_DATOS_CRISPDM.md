# Preparación de Datos — CRISP-DM (SteelNort) — Documento detallado

Este documento explica, **línea por línea y con resultados reales**, la fase de
**Data Preparation** del proyecto de detección de anomalías de rendimiento OLTP
de SteelNort. Se organiza según las 5 sub-etapas de CRISP-DM: **Selección de
datos, Limpieza de datos, Construcción de datos, Integración de datos y
Formateo**.

Todo el código vive en `data_preparation/` y se ejecuta en orden:

```
python 00_inventario.py
python 01_seleccion.py
python 02_limpieza.py
python 03_transformacion.py
python 04_integracion.py
python 05_seleccion_variables_clave.py
python 06_seleccion_variables_principales.py
```

> **Principio CRISP-DM aplicado aquí:** en preparación **NO se etiquetan
> anomalías**. Solo se conoce la carga de trabajo capturada; la detección de
> anomalías la decide el modelo no supervisado (Isolation Forest) en la fase de
> **Modelado**. Por eso el dataset integrado tiene `es_carga_normal` (marca la
> referencia de entrenamiento) pero **no** `is_anomaly`.

**Corrida de referencia:** `carga1` (captura del collector corregido, sin
`events_xe.log`, con carga de aplicación real de ~10 min y 30 workers).

## Metodologia para el informe

Esta seccion describe que se hace con los datos antes de la deteccion y el
diagnostico. El objetivo es conservar la evidencia original, estructurarla por
fuente y relacionarla temporalmente sin confundir ausencia de actividad con un
error.

### 1. Integracion de las fuentes

Se trabajan tres fuentes principales por corrida:

1. `metrics.log`: mediciones del host, SQL Server y API.
2. `events.log`: actividad de sesiones, consultas, esperas y bloqueos.
3. `sqlserver_logs.log`: mensajes del motor SQL Server.

Cada fuente se limpia y conserva primero con su propia estructura. El
`timestamp` se normaliza y se utiliza como referencia común. Después,
`03_transformacion.py` relaciona eventos y mensajes con la siguiente muestra
de `metrics.log`, formando ventanas temporales consistentes aunque las
fuentes no hayan sido capturadas exactamente en el mismo segundo.

`events_xe.log` no forma parte del esquema actual porque el collector no lo
genera. No se crean columnas XE vacías ni se imputan datos que no existen.

### 2. Limpieza y validacion

Para cada fuente se realizan las siguientes comprobaciones:

- fechas convertidas a un formato temporal común;
- valores numéricos convertidos a `float` o `int` según corresponda;
- líneas malformadas o valores no numéricos identificados y descartados;
- eventos JSON inválidos y duplicados controlados;
- mensajes del error log separados en `timestamp`, `proceso` y `mensaje`;
- revisión de nulos, valores constantes, unidades y rangos plausibles.

Los valores `0` no se eliminan automáticamente. En una métrica pueden
significar ausencia real de actividad, por ejemplo cero bloqueos, cero errores
o cero escrituras en una ventana.

### 3. Variables de métricas

Las métricas se dividen en variables de deteccion, diagnostico y contexto.
Entre las principales se incluyen CPU, memoria, I/O, red, carga del host,
sesiones, bloqueos, transacciones, buffer y API. Las variables acumulativas
`transactions_per_sec`, `total_reads` y `total_writes` se convierten a tasas
mediante `delta/dt` cuando existe una muestra anterior; la primera muestra de
cada corrida puede quedar como `NaN` porque no tiene referencia previa.

También se generan variables derivadas a partir de los eventos:

- `events_batch_count`: cantidad de `sql_batch_completed`;
- `query_duration_max_ms` y `query_duration_avg_ms`: duración máxima y media;
- `cpu_time_sum_ms`, `logical_reads_sum` y `writes_sum`;
- `wait_lck_count`, `wait_io_count` y `wait_log_count`;
- `distinct_sessions_count`;
- `log_error_count`, `log_warning_count` y `log_fatal_count`.

Estas variables se calculan por ventana y se integran con el timestamp de la
muestra. Un contador de logs igual a cero significa que no se encontró un
mensaje de esa categoría en la ventana; no significa que el parser haya
fallado.

### 4. Preparacion de eventos

Los eventos conservan sus campos de contexto y rendimiento cuando están
disponibles: `event_name`, `session_id`, `database_name`, `command`,
`duration`, `cpu_time`, `logical_reads`, `writes`, `wait_type`, `status`,
`resource_type`, `mode` y `sql_text`.

Se priorizan `sql_batch_completed`, `wait_info`, `lock_acquired`,
`lock_released`, `error_reported`, `xml_deadlock_report`, `login` y `logout`.
Los eventos se usan principalmente para explicar una señal detectada en las
métricas, no para reemplazarla.

Las consultas y actividades internas de SQL Server, como `TASK MANAGER`,
`TRACE QUEUE TASK`, `SYSTEM_HEALTH_MONITOR`, `CHECKPOINT`, `BRKR TASK`,
`ONDEMAND_TASK_QUEUE` y `HADR_AR_MGR_NOTIFICATION_WORKER`, deben distinguirse
de la actividad del workload. Cuando la evidencia no permite identificar el
origen, la clasificación correcta es `UNKNOWN`; no se asigna arbitrariamente
como actividad de usuario.

### 5. Recalculo de consultas largas y transacciones largas

Los campos `long_queries` y `long_transactions` capturados directamente por el
collector se conservan como evidencia, pero no deben interpretarse sin
contexto. Para el análisis se recalculan a partir de eventos de usuario,
excluyendo actividades clasificadas como internas de SQL Server.

El umbral de duración se mantiene como una decisión del estudio y no se fija
como una regla universal en esta fase. Así se evita que una actividad interna
con duración elevada sea contabilizada como una consulta lenta del usuario.

### 6. Preparacion de logs y mensajes de error

`sqlserver_logs.log` se conserva como fuente textual con:

- `timestamp`;
- `proceso`;
- `error_message`, correspondiente al mensaje limpio original;
- `log_category`, clasificación derivada del contenido.

Las categorías previstas son `INFO`, `STARTUP`, `CONFIGURATION`, `WARNING`,
`ERROR`, `FATAL` y `PERFORMANCE`. Mensajes como `SQL Server is starting`,
`SQL Server detected...` o `SQL Server is starting at normal priority` se
clasifican como `STARTUP` o `INFO`, no como errores.

La presencia de un mensaje `ERROR` tampoco determina por sí sola una anomalía
de rendimiento. Debe comprobarse su proximidad temporal con las métricas y
eventos, además de la base de datos, sesión, proceso o consulta relacionados.
Los mensajes detallados se mantienen separados para diagnóstico, mientras que
los conteos `log_error_count`, `log_warning_count` y `log_fatal_count` sirven
como variables numéricas de apoyo.

### 7. Relacion temporal para el diagnostico

La relación analítica esperada es:

```text
Metrica con comportamiento inusual
        -> evento relacionado
        -> consulta, espera o bloqueo
        -> mensaje de SQL Server, si existe
        -> evidencia para el diagnostico
```

No se consideran relacionados dos registros solo por tener valores parecidos.
La relación se basa principalmente en la ventana temporal y, cuando existe,
en `session_id`, `database_name`, `command`, `sql_text`, proceso y tipo de
recurso.

### 8. Normalizacion y deteccion posterior

Después de limpiar, seleccionar y derivar variables se revisan escalas,
distribuciones y valores extremos. Los extremos no se eliminan
automáticamente: pueden representar una anomalía real, un comportamiento
normal de carga o un error de medición.

En Data Preparation no se establecen reglas arbitrarias como `CPU > 80%`.
Los umbrales y la decisión de anomalía corresponden a la fase de Modelado y
deben definirse usando la línea base normal, el comportamiento histórico y la
evaluación del método seleccionado.

### 9. Conjuntos de salida

El resultado esperado de esta fase son tres productos relacionados:

- **Dataset de métricas:** variables numéricas de rendimiento y derivados por
  ventana, listo para detección.
- **Dataset de eventos:** registros relevantes con duración, CPU, lecturas,
  escrituras, esperas, bloqueos y contexto, listo para diagnóstico.
- **Dataset de logs:** mensajes de SQL Server con `timestamp`, `error_message`
  y `log_category`, listo para aportar evidencia y contexto.

La salida integrada actual materializa el primer producto y sus agregados
numéricos. Los registros detallados de eventos y mensajes deben conservarse en
CSV separados para no mezclar texto libre con las variables del modelo. El
flujo final es **Deteccion -> Diagnostico -> Apoyo a la decision**.

**Estado de implementacion:** la limpieza, la integracion temporal, los
agregados numericos y la exportacion de los CSV detallados de eventos y logs ya
se ejecutan en el pipeline actual. Las columnas `process_type`,
`error_message` y `log_category` quedan disponibles para el diagnostico.

---

## 0. Fuentes crudas de entrada

Cada corrida vive en `output/<corrida>/`. En `carga1` el inventario registró:

| Fuente | ¿Existe? | Líneas |
|---|---|---|
| `metrics.log` | Sí | 2788 |
| `events.log` | Sí | 602 |
| `events_xe.log` | **No** (eliminado del collector) | 0 |
| `sqlserver_logs.log` | Sí | 152 |
| `workload_stats.log` | Sí | 12 |

---

# 1. Selección de datos

**Scripts: `00_inventario.py`, `01_seleccion.py`, `config.py`**

CRISP-DM: *"Seleccionar datos — decidir qué datos se van a usar y por qué."*

### 1.1 `00_inventario.py` — Inventariar qué datos existen

Recorre `OUTPUT_BASE_DIR`, lista cada corrida y, para cada fuente registra si
existe y cuántas líneas tiene. Es la decisión de **qué datos están disponibles**.

- **Línea 24–29 (`contar_lineas`)**: abre cada archivo con
  `encoding="utf-8", errors="replace"` y cuenta líneas con
  `sum(1 for _ in f)`. Si falla (archivo bloqueado, codificación rara,
  no existe) devuelve `0`. Devolver 0 en vez de reventar permite que el
  inventario **nunca falle** aunque un archivo esté dañado.
- **Línea 37–41**: obtiene la lista de corridas con
  `os.listdir(OUTPUT_BASE_DIR)` filtrando solo directorios
  (`os.path.isdir`), ordenada alfabéticamente. Permite detectar corridas
  nuevas sin tocar el código.
- **Línea 43–49 (`fuentes`)**: la lista fija de fuentes que se va a
  catalogar: `metrics.log, events.log, events_xe.log, sqlserver_logs.log,
  workload_stats.log`.
- **Línea 51–62**: bucle anidado corrida×fuente; para cada par apunta
  `existe = os.path.exists(ruta)` y `lineas = contar_lineas(ruta)`.
- **Línea 64–67**: materializa todo en `DataFrame` y lo guarda en
  `datasets/inventario/inventario_corridas.csv`.

**Resultado real (carga1):** 1 corrida × 5 fuentes = 5 registros. `metadata`
igual a la tabla de la sección 0. La corrida `carga1` tiene las 4 fuentes que
debe y **no** `events_xe.log` (confirmando la eliminación del XE).

### 1.2 `01_seleccion.py` — Seleccionar las variables candidatas

Materializa el **diccionario canónico de variables** definido en `config.py`
(`FEATURES_SELECCIONADAS`) en un CSV trazable: `variables_seleccionadas.csv`.

- **Línea 26–34**: recorre `config.FEATURES_SELECCIONADAS` y por cada
  variable apunta: `columna`, `fuente`, `dominio`, `tipo`, `senal`.
- **Línea 36–41**: convierte a `DataFrame` y guarda en
  `datasets/inventario/variables_seleccionadas.csv` (con BOM `utf-8-sig`
  para Excel).
- **Línea 43–44**: imprime el conteo por *dominio*.

**Resultado real:** 72 variables numéricas de rendimiento catalogadas, en 8
grupos (ver `config.py`, `FEATURES_SELECCIONADAS`):

| Dominio | # variables | Ejemplos |
|---|---|---|
| `sistema_host` | 15 | cpu_usr, cpu_sys, memory_used_mb, disk_*, net_*, load1/5/15 |
| `sesiones` | 5 | active_sessions, active_requests, long_queries, long_transactions, idle_sessions |
| `locks` | 3 | lock_waits, total_locks, deadlocks_per_sec |
| `locks_negocio` | 7 | venta_locks, inventario_locks, kardex_locks, … |
| `transacciones/io/buffer` | 10 | transactions_per_sec, buffer_cache_hit_ratio, page_reads_per_sec, … |
| `api` | 4 | api_status, api_latency_ms, products_count, sales_count |
| `eventos_dmv/rendimiento` | 9 | events_*_count, duration_*_ms y agregados de events.log |
| `settings` | 3 | max_server_memory, user_connections_setting, cost_threshold |

**Justificación de la selección (`config.py`):** el catálogo cubre las 4 capas
del sistema supervisado: **host** (CPU/memoria/IO/red/load), **SQL Server**
(sesiones, locks, buffer, transacciones, contadores DMV), **API** (latencia de
extremo a extremo) y **eventos** (logins, batches, locks, waits derivados por
segundo). Con esto el modelo podrá detectar anomalías en cualquier capa.

> Elegimos conservar **todas** las 66 candidatas en esta sub-etapa; la
> reducción real a variables útiles se hace **sobre los datos** en `05` y `06`
> (sección Formateo), porque es ahí donde se puede medir la señal que aporta
> cada una.

---

# 2. Limpieza de datos

**Script: `02_limpieza.py`**

CRISP-DM: *"Limpieza de datos — corregir o descartar datos erróneos, incompletos,
con formato incorrecto o duplicados."*

Para cada corrida, `limpiar_corrida(corrida)` (línea 131) procesa cada fuente y
guarda CSV limpio en `datasets/limpio/<corrida>/`.

### 2.1 `metrics.log` → `limpiar_metrics(ruta)` (línea 43)

- **Línea 40** — `_RE_METRICS = re.compile(r"^(\S+\s+\S+)\s{2,}(\S+)\s+(\S+)$")`:
  la regex que reconoce el formato *"timestamp métrica valor"* separado por 2 o
  más espacios. Captura 3 grupos: timestamp (con fecha y hora), nombre de
  métrica y valor.
- **Línea 50–51** — salta la **cabecera** (`if i == 0: continue`).
- **Línea 53–54** — descarta líneas en blanco.
- **Línea 55–58** — si la línea **no** coincide con la regex → `descartadas += 1`
  y `continue` (no la consideraríamos válida).
- **Línea 60–64** — transforma el valor (string) a `float`. Si no es numérico
  (`ValueError`) → `no_numericas += 1` y la descarta. Así se **coerciona a
  numérico** y se elimina basura textual.
- **Línea 65** — guarda `(pd.Timestamp(ts), metrica, valor)` normalizando el
  timestamp a `pandas.Timestamp`.
- **Línea 67–68** — construye DataFrame `[timestamp, metrica, valor]` y
  devuelve además un dict de control (`descartadas`, `no_numericas`).

### 2.2 `events.log` → `limpiar_events(ruta)` (línea 71)

- **Línea 82–86** — cada línea debe ser JSON válido; si `json.loads` lanza
  `json.JSONDecodeError` → `malformados += 1` y se descarta.
- **Línea 87–90** — detección de **duplicados**: guarda cada línea completa en
  un `set`; si ya estaba vista, la cuenta como duplicada. (El collector podía
  escribir el mismo evento dos veces.)
- **Línea 91–92** — fija la línea cruda en `obj["_linea"]` para trazabilidad y
  apila el objeto.
- **Línea 94–97** — construye un `DataFrame` de eventos y normaliza su
  `timestamp` con `pd.to_datetime(..., errors="coerce")` (valores no parseables
  → `NaT`).

### 2.3 `events_xe.log` → `limpiar_events_xe(ruta)` (línea 100)

Mismo parser que events. En esta instalación el archivo **no existe** (XE
eliminado), por lo que `os.path.exists` en la línea 174 no entra y el resumen
queda en `xe_validos=0`.

### 2.4 `sqlserver_logs.log` → `limpiar_sqlserver_logs(ruta)` (línea 105)

- **Línea 114** — regex
  `r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s+(\S+)\s+(.*)$"` que reconoce
  el formato del errorlog de SQL Server: *fecha-hora, proceso(spid/server),
  mensaje*. Si no coincide → `descartadas += 1`.
- **Línea 119–123** — extrae `timestamp` (como `pd.Timestamp`), `proceso` y
  `mensaje`.

### 2.5 Orquestación y resumen global (`main`, línea 207)

- **Línea 212–216** — la lista de corridas a limpiar se descubre dinámicamente
  desde `OUTPUT_BASE_DIR`.
- **Línea 218–221** — ejecuta `limpiar_corrida` por corrida y acumula resúmenes.
- **Línea 223–227** — consolida todos los resúmenes en
  `datasets/limpio/resumen_limpieza_global.csv`.

**Resultado real (carga1):**

| Métrica | Valor |
|---|---|
| metrics válidas | 2787 |
| metrics descartadas | 0 |
| metrics no-numéricas | 0 |
| events válidos | 602 |
| events malformados | 0 |
| events duplicados | 0 |
| xe válidos | 0 (fuente eliminada) |
| sqlserver válidas | 152 |
| sqlserver descartadas | 0 |

**Interpretación:** la captura en `carga1` salió **limpia de fábrica**: 0 líneas
malformadas, 0 duplicadas, 0 no-numéricas. La limpieza validó el formato de
todas las fuentes sin perder datos.

**Salidas de esta sub-etapa:** `metricas_limpio.csv` (2787 filas, 48 métricas
distintas), `eventos_limpio.csv` (602 eventos), `sqlserver_logs_limpio.csv`
(152 mensajes) y el resumen global. Distribución de eventos:

| Tipo de evento | Cantidad |
|---|---|
| sql_batch_completed | 211 |
| wait_info | 169 |
| lock_acquired | 79 |
| lock_released | 66 |
| login | 51 |
| logout | 26 |

---

# 3. Construcción de datos

**Script: `03_transformacion.py`**

CRISP-DM: *"Construcción de datos — derivar, calcular y transformar atributos
para el modelado."*

Convierte los datos limpios (largos) de cada corrida en una **tabla por
muestra** (ancho, una fila por `timestamp`).

### 3.1 Pivot largo → ancho (`pivot_metricas`, línea 48)

- **Línea 50–52** — lee `metricas_limpio.csv` y convierte `timestamp` a
  `pd.datetime`.
- **Línea 53–54** — `df_m.pivot_table(index="timestamp", columns="metrica",
  values="valor", aggfunc="first")`: trans forma de formato largo
  (3 columnas, una fila por métrica) a **ancho** (una columna por métrica, una
  fila por timestamp). `aggfunc="first"` resuelve el caso teórico de dos
  lecturas de una misma métrica en el mismo segundo.
- **Línea 55** — `reset_index()` deja `timestamp` como columna.

**Efecto:** de `2787` filas largas de métricas a **62 filas** (muestras) × tantas
columnas como métricas.

### 3.2 Conversión acumulativos → tasa real (`aplicar_tasas`, línea 59)

- **Línea 61** — ordena por `timestamp` (`sort_values`) y resetea el índice.
- **Línea 62** — `dt = wide["timestamp"].diff().dt.total_seconds()`: calcula la
  **diferencia de tiempo** entre muestras consecutivas (delta en segundos). El
  muestreo es irregular, por eso se usa el delta real por muestra.
- **Línea 63–67** — para cada contador de `CONTADORES_A_TASA`:
  `tasa = serie.diff() / dt` (diferencia de la métrica entre muestras ÷ delta de
  tiempo = **tasa por segundo**). La primera muestra queda `NaN` (no hay valor
  anterior).
- `CONTADORES_A_TASA = ["total_reads", "total_writes"]` (línea 41): los dos
  contadores **acumulativos** de `dm_io_virtual_file_stats`.

> **Nota clave (corrección del doble delta):** `transactions_per_sec` **NO**
> está en `CONTADORES_A_TASA`. En una versión anterior se diferenció dos veces
> (una en el collector y otra aquí) dando valores negativos. Tras corregir el
> collector (que ya calcula `delta/dt` para los contadores `/sec`), este script
> ya no lo vuelve a diferenciar. Ver `config.py` y `docs/TAREAS_RECAPTURA_BASELINE.md`.

### 3.3 Agregación de eventos DMV por ventana (`agregar_eventos_dmv`)

- **Línea 76–77** — lee `eventos_limpio.csv` y normaliza `timestamp`.
- **Línea 81** — `df_e["ts"] = df_e["timestamp"].dt.floor("s")`: redondea cada
  evento al segundo (cada muestra de métricas es ~10 s, así varios eventos
  caen en el mismo bucket).
- **Línea 84** — `groupby(["ts","event_name"]).size().unstack(fill_value=0)`:
  cuenta cuántos eventos de cada tipo ocurrieron en cada segundo y rellena con
  0 (segundos sin eventos de un tipo). Así **derivamos**: `events_login_count`,
  `events_logout_count`, `events_batch_count`, `events_wait_count`,
  `events_lock_count` (lock_acquired + lock_released, líneas 100–104).

### 3.4 Columnas derivadas XE (`agregar_eventos_xe`, línea 108)

Igual que la anterior pero partiendo de `events_xe.log`. **En esta instalación
el archivo no existe**, por lo que la línea 111 (`os.path.exists`) devuelve
`None` y las columnas `xe_*`/`duration_*` quedan con todo `NaN`. Se descartan en
`05`.

### 3.5 Orquestación (`transformar_corrida`, línea 143)

- **Línea 146–147** — pivota y aplica tasas.
- **Línea 149** — `n_muestras = len(wide)` → en carga1 es **62**.
- **Línea 153–160** — hace `merge(..., how="left")` sobre `timestamp` para unir
  los eventos DMV (y XE si existiera) a la tabla ancha de métricas.
- **Línea 168–169** — guarda `datasets/limpio/carga1/datos_transformados.csv`.

**Resultado real (carga1):** `muestras=62`, `columnas=54`, `columnas_eventos=5`
(`events_login`, `events_logout`, `events_batch`, `events_lock`,
`events_wait`).

| Entregable de construcción | Valor carga1 |
|---|---|
| Muestras (filas) | 62 |
| Columnas tras pivot + derivación | 54 |
| Columnas de eventos derivados | 5 |
| `transactions_per_sec` (tasa) | media 151 txn/s (79–230) |
| `buffer_cache_hit_ratio` | 100.0 |

---

# 4. Integración de datos

**Script: `04_integracion.py`**

CRISP-DM: *"Integración de datos — combinar datos de las distintas fuentes y
corridas en un conjunto único."*

### 4.1 `cargar_transformadas()` (línea 32)

- **Línea 33–39** — descubre todas las corridas con `datos_transformados.csv`
  dentro de `DIR_LIMPIO`.
- **Línea 41–44** — lee cada una y normaliza su `timestamp`. Devuelve lista de
  `(corrida, df)`.

### 4.2 `construir_integrado(corridas)` (línea 48)

- **Línea 50** — `feats = config.columnas_features()` (las 72 variables
  canónicas).
- **Línea 53–55** — para cada feature que no esté en la corrida, la rellena con
  `NaN`: **alinea el esquema** para que todas las corridas tengan exactamente
  las mismas columnas (importante si una corrida tiene una métrica y otra no).
- **Línea 56–58** — añade el **contexto**:
  - `run_name` = nombre de la corrida;
  - `experiment_id` = `exp_01`, `exp_02`, … (orden de corridas);
  - `es_carga_normal` = `1` si la corrida está en
    `config.CORRIDAS_CARGA_NORMAL` (solo `carga1`), si no `0`.
    **Aquí NO se pone etiqueta de anomalía** — solo se marca la referencia
    normal de entrenamiento.
- **Línea 59** — orden de columnas: `["timestamp"] + features + contexto`.
- **Línea 61–62** — `pd.concat(frames, ignore_index=True)` une todas las
  corridas; luego `sort_values(["experiment_id","timestamp"])` intercala las
  corridas (no las apila bloque a bloque) y resetea el índice.

### 4.3 `reporte_calidad(df)` (línea 66)

- **Línea 70–84** — para cada feature calcula: `total`, `nulos`, `pct_nulos`,
  `unicos`, `media`, `desv_std`, `min`, `max`. Es el **control de calidad**
  que después usa `05` para decidir qué variables tienen señal.

### 4.4 `main()` (línea 88)

- **Línea 98–100** — guarda `dataset_steelnort_preparado.csv` (dataset
  integral de preparación).
- **Línea 102–105** — guarda `reporte_calidad_datos.csv`.
- **Línea 107–138** — guarda `metadata_transformaciones.json` con: fase
  CRISP-DM ("Data Preparation"), nº de features (72), contexto,
  `carga_normal_referencia = ["carga1"]` y una nota explicando que **no se
  asigna `is_anomaly`** (lo decide el modelo en Modelado).

**Resultado real:** `dataset_steelnort_preparado.csv` = **117 filas × 76
columnas** (timestamp + 72 features + 3 de contexto). Incluye `carga1` y
`carga2`; `carga1` queda marcada como referencia normal.

Desglose filas por corrida:

| run_name | es_carga_normal | filas |
|---|---|---|
| carga1 | 1 | 62 |
| carga2 | 0 | 55 |

---

# 5. Formateo

CRISP-DM: *"Formateo — reordenar, reducir y acotar los datos para el modelado
(selección final de atributos)."*

Los scripts `05` y `06` **reducen** el catálogo de 72 variables a las que
realmente sirven para detectar/diagnosticar anomalías, y generan el dataset de
entrenamiento final.

### 5.1 `05_seleccion_variables_clave.py` — filtro de señal sobre datos

Criterio (documentado en el propio script, líneas 11–14) aplicado **solo sobre
la carga normal** (`carga1`):

1. la variable debe **existir** en el dataset;
2. `% NaN` ≤ `UMBRAL_NAV` (50 %);
3. valores únicos ≥ `MIN_UNICOS` (2) → no constante.

Detalle de código:

- **Línea 40** — lee el dataset integrado.
- **Línea 43–44** — subconjunto de carga normal:
  `normal = df[df["run_name"].isin(config.CORRIDAS_CARGA_NORMAL)]` → 62 muestras.
- **Línea 50–54** — si la columna no existe → `senal=NO_PRESENTE` y pasa a la
  siguiente.
- **Línea 56–59** — calcula `nulos_pct = s.isna().mean()*100`, `unicos =
  s.nunique(dropna=True)`, `media`.
- **Línea 61–64** — si la columna está en `config.EXCLUIR_MEDICION_CORRUPTA`
  (p.ej. `buffer_cache_hit_ratio`) → `DESCARTADA_MEDICION` aunque tenga señal,
  porque su medición en el collector era incorrecta y podría enseñar **falsa
  normalidad** al modelo.
- **Línea 65–66** — si `nulos_pct > UMBRAL_NAV` → `MUCHO_NAN`.
- **Línea 67–68** — si `unicos < MIN_UNICOS` → `CONSTANTE`.
- **Línea 69–70** — en cualquier otro caso → `CLAVE` (tiene señal).
- **Línea 77–79** — guarda `variables_clave.csv` (trazable).
- **Línea 81–82** — lista las `CLAVE`.
- **Línea 85–90** — construye `dataset_carga_normal_clave.csv` (carga normal ×
  solo variables CLAVE + contexto).

**Resultado real (`variables_clave.csv` sobre 72 features):**

| Senal | # variables |
|---|---|
| CLAVE | 41 |
| CONSTANTE | 27 |
| MUCHO_NAN | 3 |
| DESCARTADA_MEDICION | 1 (`buffer_cache_hit_ratio`) |

→ **41 de 72** variables aportan señal útil en la carga normal.

### 5.2 `06_seleccion_variables_principales.py` — selección experta final

Parte de las variables CLAVE y aplica **criterio de dominio de rendimiento** (perfil
OLTP) para quedarse con las **22 variables definidas en el informe** para detección,
diagnóstico,
correlación y reglas de motor.

- **Línea 35–39** — lee `dataset_carga_normal_clave.csv`.
- **Línea 42–52** — materializa `VARIABLES_PRINCIPALES` (de `config.py`) en
  `variables_principales.csv` con su rol y justificación.
- **Línea 56–72** — calcula las **descartadas por redundancia**: variables que
  pasaron el filtro de señal (CLAVE) pero no son principales; les busca el
  `motivo`/`detalle` en `VARIABLES_PRINCIPALES_DESCARTADAS`.
- **Línea 75–86** — añade las `EXCLUIR_MEDICION_CORRUPTA` que no son
  principales (p.ej. `buffer_cache_hit_ratio`, motivo `medicion_incorrecta`).
- **Línea 88–89** — guarda `variables_principales_descartadas.csv` con el
  **motivo trazable** de cada descarte.
- **Línea 93–98** — dataset final:
  `cols = ["timestamp"] + principales + contexto`, guardado en
  `dataset_carga_normal_principales.csv`.

**Resultado real:** `dataset_carga_normal_principales.csv` = **62 filas × 26
columnas** (timestamp + 22 variables principales + 3 de contexto:
`run_name`, `experiment_id`, `es_carga_normal`).

**Las 22 variables principales** (de `config.py`):

| Variable | Rol |
|---|---|
| cpu_usr, cpu_sys, cpu_wai, cpu_idl | cpu |
| memory_used_mb, memory_available_mb | memoria |
| page_life_expectancy | buffer |
| disk_read_per_sec, disk_write_per_sec | io |
| total_reads, total_writes | io_motor_sql |
| active_sessions, active_requests | sesiones |
| transactions_per_sec | transacciones |
| long_queries, long_transactions | sesiones |
| duration_avg_ms, duration_max_ms, cpu_time_sum_ms | rendimiento |
| api_latency_ms, api_status | api |
| load1 | carga |
| venta_locks, kardex_locks, movimiento_caja_locks | locks_negocio |
| long_transactions | sesiones |
| api_status | api |
| total_reads, total_writes | io_motor_sql |

**Descartes por redundancia (7):** cpu_idl (~100−usr−sys−…), cpu_wai (≈0),
memory_percent y memory_available_mb (correlación ~1 con memory_used_mb),
load5/load15 (promedios lentos), idle_sessions (sin señal de problema).

**Por medición (1 + política):** `buffer_cache_hit_ratio` (el collector no
guardó el contador base; se excluye para no enseñar falsa normalidad, aunque en
la captura nueva ya venga correcto al 100 %).

### 5.3 Resumen del pipeline completo (de 72 → 22)

```
72 variables canónicas (config)
  └─ 05 filtro de señal sobre carga1 (NaN≤50%, únicos≥2, excluir corruptos)
      └─ 41 CLAVE
            └─ 06 selección experta por dominio OLTP
                 └─ 22 PRINCIPALES  →  dataset_carga_normal_principales.csv (62×26)
```

---

## Anexo — Resultados numéricos representativos del dataset final (62 muestras)

| Variable | media | min | max |
|---|---|---|---|
| cpu_usr | 44.44 | 0.00 | 47.50 |
| cpu_sys | 16.83 | 0.00 | 18.20 |
| memory_used_mb | 2130.19 | 1896.00 | 2203.00 |
| disk_write_per_sec | 4 574 032 | 0 | 10 162 894 |
| net_recv_per_sec | 38 424 | 18 698 | 530 004 |
| load1 | 8.80 | 2.48 | 10.25 |
| transactions_per_sec | 151.00 | 78.80 | 230.42 |
| page_life_expectancy | 1109.39 | 654.00 | 1572.00 |
| api_latency_ms | 4874.97 | 28.00 | 5009.00 |

**Nota interpretativa:** la captura `carga1` se hizo con 30 workers (carga
media-alta): `api_latency_ms` media ~4.9 s y `cpu_usr` ~44 %. El modelo de la
fase de Modelado, entrenado solo con esta "normalidad", aprenderá este régimen
de carga. Para generalizar a reposo conviene ampliar la carga normal (ver
`TAREAS_RECAPTURA_BASELINE.md`).

---

## Relación CRISP-DM → scripts → salidas (tabla resumen)

| Sub-etapa CRISP-DM | Script | Salida principal | Resultado carga1 |
|---|---|---|---|
| Selección de datos | 00, 01 | inventario_corridas.csv, variables_seleccionadas.csv | 2 corridas, 72 vars candidatas |
| Limpieza de datos | 02 | metricas/eventos/sqlserver *_limpio.csv + resumen | 2787 + 602 + 152 válidos, 0 perdidos |
| Construcción de datos | 03 | datos_transformados.csv | 117 muestras × 74 cols, tasas reales |
| Integración de datos | 04 | dataset_steelnort_preparado.csv + datasets de detalle | 117 × 76, sin is_anomaly |
| Formateo | 05, 06 | variables_clave/principales + dataset final | 41 CLAVE → 22 principales, 62 × 26 |
