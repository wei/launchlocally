# Nosana LLM deployment (text generation)

The hosted Nosana inference catalog dropped `qwen/qwen3.8-27b` at about 15:52 JST
on 2026-11-14 (chat calls return 404 `model_not_found`). Text generation now runs
on our own Nosana GPU deployment: vLLM's OpenAI-compatible server.
Machine-readable state: `docs/nosana-llm.json` (written only once the endpoint answered chat calls).

| | |
|---|---|
| Deployment id | `BBptm8tbTmyovxqe8FNyjyjfKJSE6CiQmgXQ3LfmnRff` |
| Endpoint | `https://4t2Q9myjses4v5riEVBUPUJPwf2fpTqFEu2EgXzSqVmd.node.k8s.prd.nos.ci` (`POST /v1/chat/completions`, `GET /v1/models`, health at `/health`) |
| Model id to send | `qwen2.5-14b` (weights `Qwen/Qwen2.5-14B-Instruct-AWQ`, 4-bit AWQ, no thinking mode) |
| Image | `docker.io/vllm/vllm-openai:v0.10.2` (pre-cached on Nosana nodes), port 8000 |
| Market | NVIDIA 3090 PREMIUM (24 GB), `CA5pMpqkYFKtme7K31pNB1s62X2SdhEv1nN9RdxKCpuQ` |
| Cost | $0.1745/hour (market price at creation), about 0.7 credits for the full 4 hours |
| Strategy / timeout | `SIMPLE`, 240 minutes |
| Created | 2026-11-14 07:05 UTC (16:05 JST); serving from 16:07 JST |
| Stops | about 2026-11-14 11:05 UTC (20:05 JST), when the job timeout ends |
| API key | none (server runs without `--api-key`; any bearer value is accepted) |

Server settings: context 16,384 tokens, up to 16 concurrent sequences batched.

Measured at 16:08 JST: a short chat call took 1.5 s. Eight concurrent calls, each
asking for about 300 tokens of Japanese JSON (188 to 312 tokens returned), finished
in 6.1 s wall time (4.2 to 6.1 s each). All 8 replies parsed as valid JSON.
The Japanese is natural, polite business register, a little generic.

## How it was created

REST API, key from `.env` (`NOSANA_API_KEY`, never printed):

```sh
curl -s -X POST https://api.nosana.com/api/deployments/create \
  -H "Authorization: Bearer $NOSANA_API_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"launchlocal-vllm-nvidia-3090",
       "market":"CA5pMpqkYFKtme7K31pNB1s62X2SdhEv1nN9RdxKCpuQ",
       "replicas":1,"timeout":240,"strategy":"SIMPLE","autostart":true,
       "job_definition":{"version":"0.1","type":"container","meta":{"trigger":"api"},
         "ops":[{"type":"container/run","id":"vllm",
           "args":{"image":"docker.io/vllm/vllm-openai:v0.10.2","gpu":true,"expose":8000,
             "cmd":["--model","Qwen/Qwen2.5-14B-Instruct-AWQ","--served-model-name","qwen2.5-14b",
                    "--max-model-len","16384","--gpu-memory-utilization","0.92",
                    "--max-num-seqs","16","--host","0.0.0.0","--port","8000"]}}]}}'
```

The response carries the deployment `id` and `endpoints[].url`.

What did not work: the same idea on the NVIDIA 4090 PREMIUM market with
`vllm/vllm-openai:latest` and `Qwen/Qwen3-14B-AWQ` sat `QUEUED` with no node for
9 minutes and was stopped. Markets list `required_images` that nodes keep cached
(`vllm/vllm-openai:v0.10.2` among them); using one of those skips the image pull.
v0.10.2 has no `--default-chat-template-kwargs`, so Qwen3 models would think by
default there; Qwen2.5 avoids that.

## Check, stop

```sh
H="Authorization: Bearer $NOSANA_API_KEY"; D=BBptm8tbTmyovxqe8FNyjyjfKJSE6CiQmgXQ3LfmnRff
E=https://4t2Q9myjses4v5riEVBUPUJPwf2fpTqFEu2EgXzSqVmd.node.k8s.prd.nos.ci
curl -s https://api.nosana.com/api/deployments/$D -H "$H" | jq '{status,endpoints}'
curl -s https://api.nosana.com/api/deployments/$D/jobs -H "$H" | jq '.jobs[]|{state,node}'
curl -s $E/v1/models | jq
curl -s -X POST https://api.nosana.com/api/deployments/$D/stop -H "$H"      # stop
```

To run past 20:05 JST, create a new deployment with the command above and update
`endpoint` / `deployment_id` in `docs/nosana-llm.json`.
