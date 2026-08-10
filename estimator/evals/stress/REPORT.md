# Informe de estrés de CAG

## Ejecución

Esta ejecución contiene 315 turnos correctos: 3 escenarios (`growing`,
`pivot` y `contradiction`) x 5 tamaños de adjunto x 3 repeticiones x 7 turnos.
Cada adjunto se reenvía en todos los turnos; por tanto, es un caso deliberado
de estrés con contexto repetido. `turn_observed` se obtiene de
`GET /sessions/{id}` junto con el snapshot de sesión, lo que evita correlacionar
líneas de logs de Docker por timestamp. Las métricas de estrés viven en
`evals/stress/metrics.py` porque reciben telemetría y memoria de sesión, no un
par `(GoldenCase, EstimationResult)`.

Las estimaciones conversacionales omiten deliberadamente las cachés exacta y
semántica, por lo que ambos porcentajes de aciertos son 0% en todas las filas.

## Resumen

| Escenario | Adjunto KiB | Latencia P50 ms | Latencia P95 ms | Coste total USD | Hit exacta | Hit semántica | Recall medio de hechos |
|---|---:|---:|---:|---:|---:|---:|---:|
| growing | 0 | 4.208 | 7.221 | 0.015140 | 0% | 0% | 83,3% |
| growing | 5 | 4.062 | 13.251 | 0.024999 | 0% | 0% | 88,9% |
| growing | 20 | 4.346 | 13.918 | 0.058485 | 0% | 0% | 83,3% |
| growing | 50 | 7.252 | 22.617 | 0.127081 | 0% | 0% | 83,3% |
| growing | 100 | 11.940 | 31.626 | 0.153671 | 0% | 0% | 88,9% |
| pivot | 0 | 4.060 | 8.659 | 0.016574 | 0% | 0% | 100,0% |
| pivot | 5 | 3.723 | 8.738 | 0.025679 | 0% | 0% | 100,0% |
| pivot | 20 | 5.345 | 12.744 | 0.059726 | 0% | 0% | 100,0% |
| pivot | 50 | 8.689 | 18.079 | 0.127968 | 0% | 0% | 100,0% |
| pivot | 100 | 12.484 | 26.693 | 0.143257 | 0% | 0% | 100,0% |
| contradiction | 0 | 3.610 | 6.049 | 0.013580 | 0% | 0% | 77,8% |
| contradiction | 5 | 3.597 | 10.869 | 0.024020 | 0% | 0% | 88,9% |
| contradiction | 20 | 4.336 | 10.913 | 0.058347 | 0% | 0% | 88,9% |
| contradiction | 50 | 5.664 | 19.102 | 0.125945 | 0% | 0% | 88,9% |
| contradiction | 100 | 9.844 | 27.677 | 0.145072 | 0% | 0% | 88,9% |

El coste total de API de la ejecución fue **$1.119544**.

## Curvas

### Latencia frente a tokens de entrada

| Adjunto KiB | Tokens P50 de entrada | Tokens P95 de entrada | Latencia P50 ms | Latencia P95 ms |
|---:|---:|---:|---:|---:|
| 0 | 3.253 | 5.632 | 4.013 | 7.221 |
| 5 | 6.859 | 10.714 | 3.870 | 10.869 |
| 20 | 17.687 | 29.613 | 4.489 | 13.918 |
| 50 | 39.100 | 67.086 | 7.252 | 19.974 |
| 100 | 44.899 | 77.755 | 11.940 | 31.626 |

### Coste acumulado medio en USD frente a índice de turno

| Turno | growing | pivot | contradiction |
|---:|---:|---:|---:|
| 1 | 0.00125 | 0.00120 | 0.00120 |
| 2 | 0.00326 | 0.00329 | 0.00318 |
| 3 | 0.00604 | 0.00605 | 0.00585 |
| 4 | 0.01004 | 0.00958 | 0.00938 |
| 5 | 0.01435 | 0.01389 | 0.01362 |
| 6 | 0.01943 | 0.01903 | 0.01866 |
| 7 | 0.02529 | 0.02488 | 0.02446 |

### MemoryDriftMetric frente a N

| Turno N | growing | pivot | contradiction | Recall medio |
|---:|---:|---:|---:|---:|
| 1 | n/a | n/a | n/a | n/a |
| 2 | 100,0% | 100,0% | 100,0% | 100,0% |
| 3 | 100,0% | 100,0% | 100,0% | 100,0% |
| 4 | 100,0% | 100,0% | 100,0% | 100,0% |
| 5 | 100,0% | 100,0% | 100,0% | 100,0% |
| 6 | 100,0% | 100,0% | 60,0% | 86,7% |
| 7 | 13,3% | 100,0% | 60,0% | 57,8% |

## Lectura de resultados

El CAG empieza a romperse cuando entra en juego la compresión. En el turno
N=6, el recall de `contradiction` cae al 60,0%; en N=7, tras la primera
expulsión de mensajes y el resumen, el recall medio cae por debajo del 60%,
hasta el **57,8%**. `growing` es el fallo más brusco: en N=7 solo 2 de 15
observaciones retienen todos los hechos previos (13,3%). `pivot` conserva el
100,0% porque su decisión tecnológica crítica se mantiene en metadata,
mientras que los presupuestos de `contradiction` no tienen un campo durable
equivalente.

El tamaño del adjunto domina latencia y coste antes que la memoria. Al pasar de
0 a 100 KiB, la latencia P50 agregada sube de 4.013 ms a 11.940 ms (3,0x), y
la P95 de 7.221 ms a 31.626 ms (4,4x); el coste total de los grupos de 100 KiB
es aproximadamente 9,8x el de los grupos de 0 KiB. Un límite práctico para
saltar a RAG es una conversación que reenvía documentos de 50+ KiB o que debe
conservar hechos más allá de N=6: hay que recuperar los fragmentos relevantes
y persistir decisiones/presupuestos explícitamente, en vez de repetir los
adjuntos completos en cada turno.
