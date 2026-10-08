# ollama-embeddings

Private Railway service that serves knowledge-base embeddings to the API when
`EMBEDDING_BACKEND=ollama` (the production default, because Bedrock model invocation is blocked for
the AWS account). It runs the same model as local development, `qwen3-embedding:0.6b` at 1024
dimensions, so it fits the existing Pinecone index.

The model is pulled at build time, so the service needs no volume. It has no public domain; the API
reaches it at `http://${{ollama-embeddings.RAILWAY_PRIVATE_DOMAIN}}:11434`.

`scripts/deploy_prod_railway.sh` creates and deploys it. Set `PROD_EMBEDDING_BACKEND=bedrock` in
`.envrc` to go back to Bedrock and skip this service.

Vectors from different models are not comparable: after changing the embedding model or backend,
re-crawl every knowledge base.
