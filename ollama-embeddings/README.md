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

`railway.toml` requests Railway Serverless (`deploy.sleepApplication = true`). Also enable
Serverless on the production Railway service. Verify the resolved deployment manifest, not just
the local file or dashboard toggle: the deploy script rejects successful or unchanged deployments
whose manifest does not enable sleep, and does not record a new fingerprint for them. A redeploy
of an old deployment can retain its old resolved configuration; upload fresh source with
`railway up ollama-embeddings --path-as-root` using the production project/environment/service
flags to apply the current settings. This rollout must target Ollama only.

After roughly
5–10 minutes without network activity, Railway sleeps the container; the API's next private-network
request wakes it. This applies to crawler content embeddings **and** knowledge-base search query
embeddings. Do not add periodic requests that keep the service awake.

The model unloads after one minute without embedding requests (`OLLAMA_KEEP_ALIVE=1m`), releasing
model memory while Ollama stays running. This retains the model across crawler batches without
keeping it in RAM indefinitely. Railway sleep separately releases the entire container's memory.
The next request reloads the same model from the image; no download or re-indexing is needed.
A Railway service variable can override the image default; keep it at `1m` when deploying.
The API retries connection failures and HTTP 502/503/504 up to four attempts with 1, 2, and 4 second
backoffs to tolerate cold starts; other failures are not retried. Changing the sleep setting requires
a deployment, not just a settings update. Verify a real embedding request after an idle period when
rolling this out; the first request can be slower.

Vectors from different models are not comparable: after changing the embedding model or backend,
re-crawl every knowledge base.
