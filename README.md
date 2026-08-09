# Estimator

Servicio FastAPI para generar estimaciones de proyectos mediante un LLM. El
contrato de entrada usa `EstimationRequest` y los prompts se renderizan con
Jinja2 desde `app/prompts/estimation/v1/`.

## Arranque

Requisitos: Docker, Docker Compose y `uv`.

```bash
cd estimator
cp .env.example .env       # configura OPENAI_API_KEY o ANTHROPIC_API_KEY
docker compose up --build
```

La API queda disponible en `http://localhost:8000` y Swagger en
`http://localhost:8000/docs`.

En otra terminal, arranca el formulario Streamlit:

```bash
cd estimator
uv sync
uv run streamlit run streamlit_app.py
```

Abre `http://localhost:8501`.

## Tests

```bash
cd estimator
uv sync
uv run pytest
uv run ruff check app tests streamlit_app.py
```

Los tests de prompts son unitarios y no llaman a APIs externas.

## Contrato HTTP

`POST /api/v1/estimate` acepta:

```json
{
  "description": "A web platform for managing appointments and notifications.",
  "project_type": "web_saas",
  "detail_level": "detailed",
  "output_format": "phases_table"
}
```

La respuesta actual es texto libre:

```json
{
  "text": "...",
  "prompt_version": "v1"
}
```
