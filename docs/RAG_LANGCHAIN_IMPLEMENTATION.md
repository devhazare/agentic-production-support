# RAG and LangChain Implementation

## Summary

Yes, this project has a RAG implementation and uses the LangChain ecosystem.

- RAG is implemented with a custom FAISS-backed indexer and retriever.
- Embeddings use `sentence-transformers` by default, with an offline TF-IDF fallback.
- LangGraph is used for workflow orchestration. LangGraph is part of the LangChain ecosystem.
- The RAG layer does not currently use LangChain's built-in retriever or vector store abstractions directly.

## RAG Components

### Indexing

Implemented in:

- `rag/indexer/__init__.py`

Main class:

- `FAISSIndexer`

Responsibilities:

- Reads knowledge documents from `data/knowledge_base/`.
- Also indexes resolved sample incidents from `data/sample_incidents/incidents.json`.
- Splits documents into chunks.
- Encodes chunks using the embedding service.
- Builds and persists a FAISS `IndexFlatL2` vector index.
- Stores chunk metadata beside the FAISS index.

Configured through:

- `core/config/settings.py`

Relevant settings:

- `vector_store = "faiss"`
- `faiss_index_path = "./data/faiss_index"`
- `knowledge_base_path = "./data/knowledge_base"`
- `rag_top_k = 4`
- `embed_model = "all-MiniLM-L6-v2"`
- `embed_device = "cpu"`

### Retrieval

Implemented in:

- `rag/retriever/__init__.py`

Main class:

- `RAGRetriever`

Responsibilities:

- Encodes an incoming query with the same embedder used by the index.
- Searches the FAISS index.
- Returns ranked `ContextChunk` results to agents and API endpoints.

### Embeddings

Implemented in:

- `services/embedding/__init__.py`

Main behavior:

- Uses `sentence-transformers` when available.
- Falls back to a local TF-IDF plus SVD embedder when the sentence-transformer model is unavailable or cannot be downloaded.

Dependencies in `requirements.txt`:

- `sentence-transformers>=2.2.0`
- `faiss-cpu==1.12.0`

## RAG Usage in Agents

### RCA Agent

Implemented in:

- `agents/rca/__init__.py`

The `RCAAgent` receives a `RAGRetriever` through dependency injection. It builds a query from incident fields, retrieves relevant runbooks or incident-history chunks, and includes that context in the RCA LLM prompt.

### Remediation Agent

Implemented in:

- `agents/remediation/__init__.py`

The `RemediationAgent` also receives a `RAGRetriever`. It retrieves remediation-specific context and includes that context when asking the LLM to generate a remediation plan.

## RAG API Endpoints

Implemented in:

- `api/v1/routers/rag.py`

Available endpoints:

- `GET /rag/health` - returns index health and metadata.
- `POST /rag/search` - searches the RAG knowledge base.
- `POST /rag/rebuild` - rebuilds the FAISS vector index.

Startup index loading/building is also handled in:

- `api/main.py`

## Orchestration and LangChain Ecosystem

LangGraph orchestration is implemented in:

- `orchestration/langgraph_workflow.py`

Main class:

- `IncidentWorkflow`

The workflow imports:

- `langgraph.checkpoint.memory.MemorySaver`
- `langgraph.graph.END`
- `langgraph.graph.StateGraph`

This builds a graph of operational agents:

- `incident_agent`
- `retrieval_agent`
- `rca_agent`
- `decision_agent`
- `approval_agent`
- `mock_remediation_agent`
- `communication_agent`
- `learning_agent`

If LangGraph is unavailable or graph construction fails, the code falls back to a local `_FallbackGraph` implementation.

Dependencies in `requirements.txt`:

- `langchain==0.2.16`
- `langchain-community==0.2.16`
- `langchain-core==0.2.39`
- `langgraph==0.2.74`

## End-to-End Flow

1. Knowledge base documents and resolved incidents are collected.
2. Text is chunked and embedded.
3. FAISS index is built or loaded.
4. Incident agents create RAG queries from alert, service, and log fields.
5. `RAGRetriever` returns relevant context chunks.
6. RCA and remediation prompts are grounded with retrieved context.
7. LangGraph coordinates the incident workflow when available.

## Important Note

The project uses LangGraph for agent orchestration, but the RAG implementation is custom. It uses FAISS and local embedding services directly instead of LangChain's `VectorStore`, `Retriever`, or chain abstractions.
