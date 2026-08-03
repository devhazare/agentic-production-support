# RAG Implementation Notes

The current repository does not use LangChain for the primary local RAG path.

Implemented local RAG uses:

- `FAISSIndexer`
- `RAGRetriever`
- `services.embedding.get_embedder`
- SentenceTransformers model `all-MiniLM-L6-v2`
- Offline TF-IDF fallback

The MVP knowledge service uses local keyword scoring when `USE_AWS=false`, and
optional S3/OpenSearch behavior when `USE_AWS=true`.

For current details, see [rag_and_llm.md](rag_and_llm.md).
