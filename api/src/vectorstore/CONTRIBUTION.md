# Vectorstore Contribution Guide

`vectorstore/` is the embedding and vector-search layer for knowledge bases: embedding providers, a Pinecone client, and a `SemanticSearch` that ties them together. It has no HTTP surface and no DynamoDB items. `crawler/` and `knowledge/` write vectors; agent search reads them.

## Layout

```text
src/vectorstore/
  __init__.py         Public exports and singletons accessors
  embeddings.py       EmbeddingProvider protocol; BedrockEmbeddings, OllamaEmbeddings; create_embeddings_service
  pinecone_client.py  PineconeClient (upsert, query, delete, namespace ops); VectorRecord/VectorMetadata
  search.py           SemanticSearch: embed query, query Pinecone, shape results
```

## Conventions

- One Pinecone index, one namespace per knowledge base: `kb_{kb_id}` (`_get_namespace`). Deleting a KB deletes its namespace. Never query across namespaces.
- The embedding backend is `settings.embedding_backend` (`bedrock` or `ollama`), chosen in `create_embeddings_service`; `get_embeddings_service` is the process singleton. The dimension (`embedding_dimension`, 1024) must match the Pinecone index: changing the model or backend means re-embedding every KB.
- Pinecone credentials are `pinecone_api_key`, `pinecone_host`, `pinecone_index` in `config/settings.py`; `get_pinecone_client(validate=True)` fails early when unset.
- Batched upserts (default 100). Vector ids are the chunk ids from `crawler.worker.generate_chunk_id`, so re-upserts overwrite.
- Pinecone failures on delete are logged and reported as a boolean; callers (`KnowledgeBaseService`) decide what to do.

## Add an embedding backend

1. Implement the `EmbeddingProvider` protocol in `embeddings.py` (see `OllamaEmbeddings`, the smaller one).
2. Add a branch to `create_embeddings_service` and any new setting to `config/settings.py` (default in code, env override), plus the Railway/Terraform config.
3. Add a case to `tests/test_embedding_providers.py`.

## Testing

```bash
uv run pytest tests/test_embedding_providers.py tests/test_knowledge_access.py -q
uv run ruff check src/vectorstore && uv run mypy src/vectorstore
```

Mock boto3/httpx and the Pinecone index; tests must not reach AWS, Ollama or Pinecone.

## Do / Don't

- Do keep the namespace derivation in one place (`_get_namespace`).
- Do pass `kb_id` on every call so isolation is structural, not filtered.
- Don't construct clients at import time; use the `get_*` accessors.
- Don't add a vector-store abstraction layer for a second database until there is one.
