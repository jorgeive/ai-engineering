# Comprobación de cordura de embeddings

| Pareja | Texto A | Texto B | Similitud coseno |
| --- | --- | --- | ---: |
| A — semánticamente cercanos | OAuth 2.0 authentication backend with JWT tokens for fintech mobile app | Authorization service using JSON Web Tokens for a banking application | 0.5957 |
| B — no relacionados | OAuth 2.0 authentication backend with JWT tokens for fintech mobile app | Database migration from MySQL to PostgreSQL with zero downtime | 0.1920 |
| C — genéricos | Backend services | API development | 0.5407 |

La pareja B encaja claramente con la intuición: el embedding distingue autenticación de una migración de base de datos. La pareja A está mucho más cerca que B, aunque su valor `0.5957` queda justo bajo el umbral orientativo de `0.6`; merece discusión porque ambos textos describen la misma capacidad general con vocabulario distinto. La pareja C muestra una similitud moderadamente alta pese a su ambigüedad, algo razonable porque ambas frases son conceptos amplios de backend. Esta es una comprobación de cordura, no una evaluación formal del modelo.
