# RAG and LLM

This project has two related knowledge/RCA paths:

1. The versioned `/api/v1` pipeline uses local FAISS RAG.
2. The MVP workflow uses `KnowledgeService`, which supports local keyword
   search or optional AWS S3/OpenSearch.

## Local FAISS RAG

Files:

- `rag/indexer/__init__.py`
- `rag/retriever/__init__.py`
- `services/embedding/__init__.py`

The FAISS indexer reads:

- Markdown, text, and PSV files under `KNOWLEDGE_BASE_PATH`
- Resolved incidents from `data/sample_incidents/incidents.json`

It chunks text by words, encodes chunks, and stores:

- `data/faiss_index.index`
- `data/faiss_index_meta.pkl`
- `data/faiss_index_embedder.pkl` when TF-IDF fallback is used

These generated files should not be committed.

## Embedding Model

Default:

```env
EMBED_MODEL=all-MiniLM-L6-v2
EMBED_DEVICE=cpu
```

The embedder factory tries to load the configured SentenceTransformers model.
If model loading fails, or if `EMBED_MODEL` is set to `tfidf`, `offline`, or
`local`, it uses an offline TF-IDF + SVD + normalization pipeline.

## RAG Endpoints

```bash
curl http://localhost:8000/api/v1/rag/health
curl -X POST http://localhost:8000/api/v1/rag/rebuild
curl -X POST http://localhost:8000/api/v1/rag/search \
  -H "Content-Type: application/json" \
  -d '{"query":"checkout database timeout","top_k":5}'
```

## LLM Service

Files:

- `services/llm/__init__.py`
- `services/bedrock_rca.py`

The main LLM service uses a provider strategy:

| Provider | Status | Notes |
|---|---|---|
| Mock | Implemented | Default when `APP_MODE=mock`; deterministic and safe for local runs. |
| Ollama | Implemented | Used when `APP_MODE=live` and `LLM_PROVIDER=ollama`. |
| Bedrock | Partial/experimental | Used by the MVP Bedrock wrapper when `USE_AWS=true`. |
| OpenAI | Not available | Settings reference OpenAI, but provider module is not present in the current tree. |
| Anthropic | Not available | Settings reference Anthropic, but provider module is not present in the current tree. |
| Azure OpenAI | Not available | Enum value exists; no provider implementation is present. |

## Mock Mode

Default `.env.example` behavior:

```env
APP_MODE=mock
```

In mock mode, the main LLM service returns deterministic RCA and remediation
text. This is useful for tests, demos, and offline development.

## Ollama Mode

Example:

```env
APP_MODE=live
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

Start Ollama separately and pull the configured model before running the API.

## MVP Bedrock Wrapper

The MVP workflow uses `BedrockRCAClient`.

- When `USE_AWS=false`, it returns local mock RCA output.
- When `USE_AWS=true`, it creates a Bedrock Runtime client and calls the
  configured `BEDROCK_MODEL_ID`.

The wrapper requests structured JSON and parses the response into `RCAOutput`.
This path is useful as an AWS reference, but it still routes remediation through
mock action services in the current codebase.

## Grounding and Safety Notes

- Retrieved documents are passed into RCA prompts as grounding context.
- The MVP workflow scrubs simple prompt-injection and sensitive-text patterns.
- Citation checks exist in `scripts/evaluate_rca.py`.
- Human review is required for high-risk or low-confidence MVP incidents.
- No automatic knowledge-base learning is implemented yet.
