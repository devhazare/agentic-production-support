# Contributing

Thank you for considering a contribution to Agentic Support Framework.

This project is an AI Operations and Production Support reference
implementation. Contributions should preserve the safe local developer
experience and clearly distinguish implemented behavior from mock,
experimental, or planned behavior.

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

Run the UI:

```bash
streamlit run ui/dashboard.py
```

Run tests:

```bash
pytest tests/ -q
```

## Contribution Principles

- Keep `APP_MODE=mock` and `USE_AWS=false` working for first-time users.
- Do not make live remediation the default behavior.
- Do not commit secrets, tokens, credentials, local logs, generated vector
  indexes, Terraform state, IDE files, or virtual environments.
- Clearly label new behavior as implemented, partial, mocked, experimental, or
  planned.
- Add or update tests when behavior changes.
- Update `.env.example` when adding configuration.
- Update documentation when changing API routes, workflows, provider behavior,
  or operational commands.

## Pull Request Checklist

Before opening a pull request:

- Run `git status --short --ignored`.
- Confirm `.env`, `.local/`, `.venv/`, generated logs, FAISS artifacts, build
  archives, and Terraform state are not staged.
- Run `pytest tests/ -q`.
- Confirm README and docs links still work.
- Describe whether the change affects mock mode, live mode, AWS mode, RAG, LLM,
  approval, or remediation behavior.

## Safe Areas for First Contributions

- Documentation improvements.
- Additional sample runbooks or sanitized sample incidents.
- Unit tests for existing agents, parsers, and workflow decisions.
- New mock integrations behind clear interfaces.
- Better validation and evaluation documentation.

## Security-Sensitive Contributions

Do not open public issues or pull requests containing real credentials,
customer data, production logs, private URLs, or exploit details. Follow
[SECURITY.md](SECURITY.md) for vulnerability reporting.
