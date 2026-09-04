# Recaptura de Baseline (carga normal de referencia)

> Para la documentación **detallada línea-por-línea** de las sub-etapas
> CRISP-DM de Data Preparation (Selección, Limpieza, Construcción, Integración
> y Formateo) con los resultados de cada script (00–06), ver
> [`PREPARACION_DATOS_CRISPDM.md`](PREPARACION_DATOS_CRISPDM.md).

## Situación actual (tras la recaptura)

La fase de preparación usa ahora como **carga normal de referencia** la corrida
`carga1` (62 muestras), capturada con el collector corregido. El dataset de
entrenamiento (`dataset_carga_normal_principales.csv`) tiene **62 muestras × 15
variables principales**.

La recaptura sustituyó a `test_run` (32 muestras, 43 s, latencias ~7 ms), que
era insuficiente y tenía métricas del collector sin corregir.

## Qué se corrigió en el collector (`workload-collector/`)

1. **`events_xe.log` eliminado.** Se quitó la captura de Extended Events de
   `run.py`; solo quedan `events.log`, `metrics.log`, `sqlserver_logs.log` (+
   `workload_stats.log`). `events_xe.log` no forma parte del esquema actual;
   las derivadas activas provienen de `events.log` y `sqlserver_logs.log`.
2. **Contadores `/sec` → tasa real en el collector.** El collector calcula ahora
   `delta/dt` para los contadores `/sec` (Transactions/sec, Page reads/sec, …).
   `buffer_cache_hit_ratio` se calcula con el numerador y el contador **base**
   reales: en la captura dio **100.0 %** (buffer suficiente).
3. **Doble delta corregido en el pipeline.** Al ser `transactions_per_sec` ya una
   tasa del collector, se quitó de `CONTADORES_A_TASA` en `03_transformacion.py`
   para no diferenciar dos veces (daba valores negativos). Ahora es coherente
   (~79–230 txn/s, media 151).

## Notas de la captura `carga1`

- Muestreo ~10 s; duración ~10 min; 30 workers de carga.
- `api_latency_ms` media ~4.9 s y `cpu_usr` media ~44 %: la captura se hizo con
  carga media-alta (API saturada), no en reposo. Conviene considerarlo al
  interpretar la "normalidad" aprendida por el modelo en Modelado.
- `page_life_expectancy` ~1109 s (subiendo) y `buffer` al 100 %: buffer con buena
  salud durante la captura.

## Pendiente / mejora futura

Para un Isolation Forest más robusto conviene **ampliar la carga normal** con
más corridas y franjas horarias (mañana/tarde/noche) y en condiciones de menor
carga (latencias bajas), de modo que la frontera de normalidad capture mejor la
variabilidad natural del OLTP.

## Cómo integrar una recaptura adicional

1. Colocar la nueva corrida en `D:\Steel_Nort\output\<nombre>`.
2. Registrar su `run_name` en `config.py:CORRIDAS_CARGA_NORMAL`.
3. Re-ejecutar el pipeline:
   ```bash
   cd D:\Steel_Nort\data_preparation
   python 00_inventario.py
   python 01_seleccion.py
   python 02_limpieza.py
   python 03_transformacion.py
   python 04_integracion.py
   python 05_seleccion_variables_clave.py
   python 06_seleccion_variables_principales.py
   ```
4. El dataset de entrenamiento resultante se genera en
   `dataset_carga_normal_principales.csv`.
