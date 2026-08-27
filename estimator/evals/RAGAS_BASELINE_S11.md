# Baseline RAGAS — Sesión 11

Evaluación real sobre Q1–Q5 del golden set. El pipeline utilizó búsqueda híbrida con reranking; el juez fue `gpt-4o-mini` y los embeddings `text-embedding-3-small`.

| consulta | faithfulness | answer_relevancy | context_precision | context_recall |
|---|---:|---:|---:|---:|
| Q1 | 0.000 | 0.063 | 0.806 | 0.000 |
| Q2 | 0.000 | 0.037 | 0.000 | 0.000 |
| Q3 | 0.000 | 0.132 | 1.000 | 0.000 |
| Q4 | 0.667 | 0.240 | 0.833 | 0.000 |
| Q5 | 0.000 | 0.000 | 0.833 | 0.000 |
| **promedio** | **0.133** | **0.094** | **0.694** | **0.000** |

Los datos completos, incluidas las puntuaciones sin redondear, están en `evals/ragas_baseline_s11.json`.

Lo que más chirría es que la `faithfulness` sea nula en cuatro consultas pese a que el pipeline exige citaciones por línea. El `context_recall` es nulo en las 5 consultas, parece que hay un desajuste.
