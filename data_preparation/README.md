# SteelNort — Preparación de Datos (Fase CRISP-DM: Data Preparation)

Módulo que convierte los **logs crudos** de `output/` en un **dataset integrado
y depurado** de la **carga de trabajo OLTP**, listo para la fase de Modelado
(detección de anomalías no supervisada con Isolation Forest).

> **Enfoque (CRISP-DM):** en esta fase **solo se conoce la carga de trabajo**
> (los datos tal cual pasan). **NO se etiqueta ninguna anomalía** aquí; la
> decisión de si una corrida es anómala le corresponde al modelo en la fase de
> **Modelado**. Por eso el dataset de preparación no tiene columna `is_anomaly`.

> **Documentación detallada:** las sub-etapas CRISP-DM (Selección, Limpieza,
> Construcción, Integración y Formateo) están documentadas **línea por línea,
> con código y resultados reales** en
> [`docs/PREPARACION_DATOS_CRISPDM.md`](docs/PREPARACION_DATOS_CRISPDM.md).

La metodología utilizada para el informe, incluidos los criterios de limpieza,
clasificación de eventos, preparación de mensajes de SQL Server y relación
temporal entre las fuentes, está documentada en la sección **Metodología para
el informe** del documento detallado.

---

## Pipeline (en orden)

| Paso | Script | Descripción | Salida |
|------|--------|-------------|--------|
| 0 | `00_inventario.py` | Catálogo de corridas × fuentes (existencia y líneas). | `datasets/inventario/inventario_corridas.csv` |
| 1 | `01_seleccion.py` | Materializa el diccionario canónico de variables (72). | `datasets/inventario/variables_seleccionadas.csv` |
| 2 | `02_limpieza.py` | Parsers y validación de cada fuente por corrida. | `datasets/limpio/{corrida}/*_limpio.csv` |
| 3 | `03_transformacion.py` | Pivot largo→ancho, tasas (delta/dt), agregación de eventos por ventana de muestra. | `datasets/limpio/{corrida}/datos_transformados.csv` |
| 4 | `04_integracion.py` | Integra corridas y exporta eventos/logs separados. | `dataset_steelnort_preparado.csv` + `dataset_eventos.csv` + `dataset_logs.csv` |
| 5 | `05_seleccion_variables_clave.py` | Filtro de señal: variables que varían en la carga normal (descartar constantes / mucho NaN). | `dataset_carga_normal_clave.csv` + `variables_clave.csv` |
| 6 | `06_seleccion_variables_principales.py` | **Selección experta por dominio**: reduce a las **variables principales** (sin redundancias) para detección, diagnóstico, correlación y reglas. | `dataset_carga_normal_principales.csv` + `variables_principales.csv` |

Ejecución:

```bash
cd D:\Steel_Nort\data_preparation
pip install -r requirements.txt
python 00_inventario.py
python 01_seleccion.py
python 02_limpieza.py
python 03_transformacion.py
python 04_integracion.py
python 05_seleccion_variables_clave.py
python 06_seleccion_variables_principales.py
```

---

## Entregables

### Dataset integrado (toda la carga)
`datasets/integrado/dataset_steelnort_preparado.csv`
- **117 filas × 76 columnas** (timestamp + 72 variables + run_name +
  experiment_id + es_carga_normal).
- Sin `is_anomaly` (la decide el modelo en Modelado).
- `es_carga_normal=1` marca la carga normal de referencia de entrenamiento.

### Dataset de carga normal con variables principales (para Modelado)
`datasets/integrado/dataset_carga_normal_principales.csv`
- **62 filas × 26 columnas** (carga1, 22 variables principales + contexto).
- Es la base sobre la que se entrenará el Isolation Forest, y la que alimenta
  el análisis de correlación y las reglas de motor.

### Selección de variables (trazable)
- `variables_clave.csv` — filtro objetivo de señal (41 CLAVE / 27 CONSTANTE /
  3 MUCHO_NAN / 1 DESCARTADA_MEDICION de 72).
- `variables_principales.csv` — selección experta por dominio (22 finales).
- `variables_principales_descartadas.csv` — descartadas por redundancia,
  baja utilidad y medición incorrecta, con motivo.

### Datasets de diagnóstico

- `dataset_eventos.csv` — eventos de `carga1` y `carga2` clasificados como
  `USER`, `SQL_SERVER_INTERNAL` o `UNKNOWN`.
- `dataset_logs.csv` — mensajes de SQL Server con `error_level`,
  `error_message` y `log_category`.

---

## Variables principales (22) — para detección, diagnóstico, correlación y reglas

| Variable | Rol | Utilidad |
|---|---|---|
| cpu_usr, cpu_sys | cpu | saturación/computo OLTP y llamadas al kernel |
| memory_used_mb | memoria | presión de memoria del host |
| disk_read_per_sec, disk_write_per_sec | io | saturación de I/O (anomalías de storage) |
| net_recv_per_sec, net_send_per_sec | red | volumen de tráfico/request |
| load1 | carga | presión global del host (reactivo) |
| active_sessions, active_requests, long_queries | sesiones | concurrencia y consultas lentas |
| total_locks | locks | contenido de bloqueos |
| transactions_per_sec | transacciones | volumen OLTP (tasa real) |
| page_life_expectancy | buffer | memoria y eficiencia de lectura SQL Server |
| api_latency_ms | api | diagnóstico de extremo a extremo |
| venta_locks, kardex_locks, movimiento_caja_locks | locks_negocio | contención en módulos de ventas, kardex y caja |
| long_transactions | sesiones | bloqueo por transacción larga frente a query lenta |
| api_status | api | impacto visible para el usuario final |
| total_reads, total_writes | io_motor_sql | I/O del motor frente al sistema operativo |

### Descartadas (8)
Por redundancia / baja utilidad (7): cpu_idl (≈100−usr−sys−…), cpu_wai (~0),
memory_percent y memory_available_mb (correlación ~1 con memory_used_mb),
load5/load15 (promedios lentos frente a load1), idle_sessions (sin señal de
problema).

Por **política de medición (1)**: `buffer_cache_hit_ratio`. En la captura nueva el
collector corregido ya lo calcula correctamente (100 %, ratio real). Se mantiene
excluido de las variables principales por política conservadora
(`EXCLUIR_MEDICION_CORRUPTA`), para no alterar el set de 22 variables. Puede
reincorporarse a la selección si se prefiere.

---

## Fuentes de datos y formatos

Cada corrida (`output/<corrida>/`) tiene estos archivos crudos:

| Fuente | Formato | Contenido |
|---|---|---|
| `metrics.log` | CSV de ancho fijo (timestamp, metrica, valor) | métricas de sistema + SQL Server + negocio + API (45 métricas distintas) |
| `events.log` | JSON por línea | eventos de sesiones (login, logout, sql_batch_completed, locks, waits) |
| `sqlserver_logs.log` | log de SQL Server | mensajes y errores del motor |
| `workload_stats.log` | CSV | estadísticas de las operaciones de la carga (latencia, errores) |

> La fuente `events_xe.log` (Extended Events) se **eliminó**: no se captura ni se
> usa en la preparación. Solo quedan `events.log`, `metrics.log` y
> `sqlserver_logs.log`.

> Todos los datasets intermedios se guardan en **CSV** (no parquet) para poder
> inspeccionarlos en texto plano.

---

## Hallazgos de calidad de datos (documentados)

1. **Contadores `/sec` del collector corregido.** Tras la corrección del
   collector, `transactions_per_sec` y el resto de contadores `/sec` ya llegan
   como **tasa real por segundo** (el collector calcula `delta/dt`). `total_reads`
   y `total_writes` siguen siendo acumulativos y se convierten a tasa en `03`.
   (Se corrigió un doble delta previo: `transactions_per_sec` no se vuelve a
   diferenciar en el pipeline porque ya viene como tasa.)
2. **Doble delta corregido.** Al migrar, `transactions_per_sec` daba valores
   negativos por duplicar el delta (collector + pipeline). Se resolvió quitándolo
   de `CONTADORES_A_TASA`; ahora el valor es coherente (~79–230 txn/s).
3. **`buffer_cache_hit_ratio` recuperado con el collector corregido.** El
   collector ahora lee el numerador y el **contador base** y calcula el ratio
   real `(hits/base)*100`, que en la captura da **100.0%** (buffer suficiente).
   Sin embargo sigue excluido de las variables principales por política
   (se documenta; se puede reincorporar si se desea).
4. **`events_xe.log` eliminado.** No se captura ni se usa; las columnas
  `events_xe.log` no se incluye en el esquema; las métricas derivadas activas
  provienen de `events.log` y `sqlserver_logs.log`.
5. **Carga de una sola corrida (`carga1`, 62 muestras).** Es la carga normal de
   referencia actual. Muestreo ~10 s, duración ~10 min, con workload real.
6. **API bajo carga durante la captura.** `api_latency_ms` media ~4.9 s (picos
   5 s) y `cpu_usr` media ~44 %, porque la captura se hizo con 30 workers de
   carga. Es una carga media-alta, no una carga ligera ocurría en reposo; conviene
   considerarlo al interpretar la "normalidad" aprendida por el modelo.
7. **PLE y buffer saludables.** `page_life_expectancy` ~1109 s (subiendo) y
   `buffer_cache_hit_ratio=100 %` indican un buffer con buena salud durante la
   captura.

---

## Trazabilidad: decisiones tomadas

| Decisión | Detalle |
|---|---|
| Fase CRISP-DM | Solo **Data Preparation**; sin etiquetado de anomalías (lo decide el modelo en Modelado). |
| Fuentes de captura | Solo `events.log`, `metrics.log`, `sqlserver_logs.log` (+ `workload_stats.log`); `events_xe.log` eliminado. |
| Carga normal de referencia | `carga1` = 62 muestras (workload real, collector corregido, ratio buffer 100 %). |
| Reducción de variables | 66 → 43 (señal en carga1) → **22 principales** (experta por dominio) − 1 por medición. |
| Formato | Datasets intermedios y final en CSV para inspección. |
| Umbrales | `UMBRAL_NAV=50%`, `MIN_UNICOS=2`. |

---

## Estructura de salida

```
data_preparation/
├── config.py              # rutas, variables, umbrales, carga normal
├── 00_inventario.py … 06_seleccion_variables_principales.py
├── requirements.txt
├── datasets/
│   ├── inventario/        # inventario_corridas, variables_seleccionadas
│   ├── limpio/<corrida>/  # *_limpio.csv + datos_transformados.csv + resumenes
│   └── integrado/         # dataset integrado + dataset de variables principales
└── docs/
    ├── PREPARACION_DATOS_CRISPDM.md        # sub-etapas CRISP-DM detalladas línea a línea
    └── TAREAS_RECAPTURA_BASELINE.md
```

---

## Configuración clave (`config.py`)

- `OUTPUT_BASE_DIR` → `D:\Steel_Nort\output` (logs crudos; no se tocan).
- `CORRIDAS_CARGA_NORMAL` → `["carga1"]`: la corrida de carga de aplicación real
  (workload presente, collector corregido, ratio buffer 100 %). Es la referencia
  normal de entrenamiento de la fase de Modelado.
- `EXCLUIR_MEDICION_CORRUPTA` → `["buffer_cache_hit_ratio"]`: se excluye de la
  selección (aunque hoy llegue correcto al 100 %), política conservadora para no
  cambiar el set de 22 variables.
- Umbrales de selección: `UMBRAL_NAV=50`, `MIN_UNICOS=2`.
- `FORMATO_INTERMEDIO = "csv"` → los datasets intermedios se escriben en CSV.

---

## Historial de trabajo

- **Iteración 1 (`anomaly_detection`):** pipeline inicial con 00→04 + un paso de
  etiquetado supervisado (`05_etiquetado_corridas.py`) que etiquetaba anomalías por
  latencia. Se descartó porque en CRISP-DM la preparación NO etiqueta (la detección
  la hace el modelo).
- **Iteración actual (`data_preparation`):** construida **desde cero** con el
  enfoque correcto:
  - Paso 0–4 en `data_preparation/` (inventario, selección, limpieza,
    transformación, integración) **sin etiquetado de anomalías**.
  - Paso 5: filtro de señal (30 variables con variación real).
  - Paso 6: **selección experta por dominio** → 22 variables principales para
    detección, diagnóstico, correlación y reglas de motor.
  - Recaptura: se eliminó `events_xe.log`, se corrigió el collector (tasa real
    de contadores `/sec` y `buffer_cache_hit_ratio` con contador base) y el doble
    delta en `03`. Referencia normal actual: `carga1` (62 muestras).
  - Todos los datasets en **CSV** para poder ver los datos.
- **Pendiente (fase Modelado):** Isolation Forest (train-only-normal) sobre
  `dataset_carga_normal_principales.csv`, análisis de correlación y reglas de motor.
