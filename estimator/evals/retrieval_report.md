# Evaluación de recuperación — Sesión 10

Se ejecutó el golden set oficial de cinco consultas representativas, con tres
mediciones por consulta después de una petición de calentamiento descartada.
Las embeddings de consulta se calcularon una sola vez y no se incluyen en las
latencias. La descarga inicial del cross-encoder también queda fuera gracias al
calentamiento.

| Configuración | Búsqueda | Reranking | Precisión@5 | Latencia media (ms) |
| --- | --- | --- | ---: | ---: |
| A | Vectorial | No | 0.92 | 5.0 |
| B | Híbrida | No | 0.92 | 5.6 |
| C | Vectorial | Sí | 0.92 | 586.9 |
| D | Híbrida | Sí | 0.92 | 459.2 |

Para este corpus y golden set usaría búsqueda híbrida sin reranking: mantiene la
mejor precisión observada y solo añade 0.6 ms frente a la búsqueda vectorial. El
cross-encoder no mejora la precisión media@5 y aumenta la latencia media entre
0.45 y 0.58 segundos, por lo que su ganancia de relevancia no compensa el coste
en este caso de uso. Lo mantendría como opción activable: mejora Q4 de 0.80 a
1.00, aunque reduce Q1 de 1.00 a 0.80.
