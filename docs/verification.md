# Verification

Use this checklist before publishing or demoing the project.

## Static Checks

```bash
git status --short --ignored
```

Confirm generated and local-only files are not staged:

- `.env`
- `.local/`
- `.venv/`
- `.pytest_cache/`
- generated logs
- FAISS index and pickle files
- Terraform state
- build archives

## Tests

```bash
pytest tests/ -q
```

The current test suite covers agent logic, log parsers, RCA parser coercion,
Magento log generation behavior, and MVP workflow routing.

## API Health

```bash
uvicorn api.main:app --reload --port 8000
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/health
```

## RAG Health

```bash
curl http://localhost:8000/api/v1/rag/health
curl -X POST http://localhost:8000/api/v1/rag/rebuild
```

## UI

```bash
streamlit run ui/dashboard.py
```

Open `http://localhost:8501` and confirm the dashboard connects to the API.
