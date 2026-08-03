# Contributing

Thanks for improving Agentic Support Framework.

## Local Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Run the API:

```bash
uvicorn api.main:app --reload --port 8000
```

Run tests:

```bash
pytest tests/ -v
```

## Contribution Guidelines

- Keep mock/local mode working without cloud credentials.
- Do not commit `.env`, Terraform state, local logs, or generated vector indexes.
- Prefer small, focused pull requests.
- Add or update tests for behavior changes.
- Document new environment variables in `.env.example`.

## Code Style

The project targets Python 3.11 and uses type hints, Pydantic v2, FastAPI,
LangGraph, and pytest.
