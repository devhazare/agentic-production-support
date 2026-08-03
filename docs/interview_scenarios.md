# Interview Scenarios

Use these prompts to explain the project in interviews or architecture reviews.

## Architecture

- Explain the difference between the `/api/v1` pipeline and the MVP workflow.
- Walk through the incident lifecycle from ingestion to validation.
- Explain why remediation is simulated by default.
- Describe how RAG grounding is used during RCA.

## Python Design

- Identify examples of Template Method, Strategy, Factory, Builder, Facade,
  Command, Observer, and Repository patterns.
- Explain why agents receive dependencies through constructors.
- Explain how Pydantic models and dataclasses are used differently.

## Operations

- Explain how mock mode prevents accidental live external calls.
- Explain how human approval is routed.
- Explain current production gaps and how you would close them.

## Security

- Explain why `.env`, Terraform state, generated logs, and FAISS pickle files
  should not be committed.
- Explain the current lack of API authentication and how you would add it.
