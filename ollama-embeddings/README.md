# ollama-embeddings

Private Railway service that serves knowledge-base embeddings to the API when
`EMBEDDING_BACKEND=ollama` (the production default, because Bedrock model invocation is blocked for
the AWS account). It runs the same model as local development, `qwen3-embedding:0.6b` at 1024
dimensions, so it fits the existing Pinecone index.

The model is pulled at build time, so the service needs no volume. It has no public domain; the API
reaches it at `http://${{ollama-embeddings.RAILWAY_PRIVATE_DOMAIN}}:11434`.

`scripts/deploy_prod_railway.sh` creates and deploys it. Set `PROD_EMBEDDING_BACKEND=bedrock` in
`.envrc` to go back to Bedrock and skip this service.

## Idle sleep

`railway.toml` enables Railway Serverless (`deploy.sleepApplication = true`). After roughly
5–10 minutes without network activity, Railway sleeps the container; the API's next private-network
request wakes it. This applies to crawler content embeddings **and** knowledge-base search query
embeddings. Do not add periodic requests that keep the service awake.

The model stays loaded while the container runs (`OLLAMA_KEEP_ALIVE=-1`), but sleep releases the
container's memory. The model is baked into the image and does not need downloading on wake.
The API retries connection failures and HTTP 502/503/504 up to four attempts with 1, 2, and 4 second
backoffs to tolerate cold starts; other failures are not retried. Changing the sleep setting requires
a deployment, not just a settings update. Verify a real embedding request after an idle period when
rolling this out; the first request can be slower.

Vectors from different models are not comparable: after changing the embedding model or backend,
re-crawl every knowledge base.
