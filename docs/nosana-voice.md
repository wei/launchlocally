# Nosana voice deployment (workstream A)

Narration audio comes from Kokoro TTS running on a Nosana GPU deployment.
Client: `launchlocal/voice.py`. Machine-readable state: `docs/nosana-voice.json`.

| | |
|---|---|
| Deployment id | `7cVoC6ZGh7yoZNushn377U13EA3rvw4B26QuVVFr2dWi` |
| Endpoint | `https://5BdSWyBFzdsvkzPNCLAbdFAC6J4L9s4cG5WuLtpQL68H.node.k8s.prd.nos.ci` (OpenAI-style `POST /v1/audio/speech`, health at `/health`) |
| Image | `ghcr.io/remsky/kokoro-fastapi-gpu:latest` (Kokoro-FastAPI, port 8880) |
| Market | NVIDIA 3060 PREMIUM, `7AtiXMSH6R1jjBxrcYjehCkkSF7zvYWte63gwEDBcGHq` |
| Cost | $0.0436/hour (market price at creation); account had 10 credits |
| Strategy / timeout | `SIMPLE`, 300 minutes |
| Created | 2026-11-14 06:19 UTC (15:19 JST) |
| Stops | about 2026-11-14 11:20 UTC (20:20 JST), when the job timeout ends |
| Voices | Japanese `jf_alpha` (also `jf_gongitsune`, `jf_nezumi`, `jf_tebukuro`), English `af_heart` |

Override the endpoint with env `NOSANA_TTS_URL`. Kokoro-FastAPI takes one-letter
`lang_code` (`j`, `a`, `b`); `voice.py` maps pack codes like `ja` / `en-us`.
Measured on the fixture: 1.6 to 2.5 s per line for 2.9 to 6.0 s of audio.
`デイトナ` phonemizes as `deːtona`.

## How it was created

REST API, key from `.env` (`NOSANA_API_KEY`, never printed):

```sh
curl -s -X POST https://api.nosana.com/api/deployments/create \
  -H "Authorization: Bearer $NOSANA_API_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"launchlocal-kokoro-tts",
       "market":"7AtiXMSH6R1jjBxrcYjehCkkSF7zvYWte63gwEDBcGHq",
       "replicas":1,"timeout":300,"strategy":"SIMPLE","autostart":true,
       "job_definition":{"version":"0.1","type":"container","meta":{"trigger":"api"},
         "ops":[{"type":"container/run","id":"kokoro",
                 "args":{"image":"ghcr.io/remsky/kokoro-fastapi-gpu:latest","gpu":true,"expose":8880}}]}}'
```

The response carries the deployment `id` and `endpoints[].url`. Markets and prices:
`GET https://api.nosana.com/api/markets/` (no auth). Balance:
`GET https://api.nosana.com/api/credits/balance`.

## Check, stop

```sh
H="Authorization: Bearer $NOSANA_API_KEY"; D=7cVoC6ZGh7yoZNushn377U13EA3rvw4B26QuVVFr2dWi
curl -s https://api.nosana.com/api/deployments/$D -H "$H" | jq '{status,endpoints}'
curl -s https://api.nosana.com/api/deployments/$D/events -H "$H" | jq
curl -s -X POST https://api.nosana.com/api/deployments/$D/stop -H "$H"      # stop
```

To extend past the timeout, create a new deployment with the command above and
update `endpoint` / `deployment_id` in `docs/nosana-voice.json`.

## Fallback

If the endpoint fails, `voice.py` runs Kokoro locally on CPU (`kokoro-onnx`,
Japanese via `misaki[ja]` with the `unidic-lite` dictionary; the full `unidic`
package was removed because its dictionary is a separate 500 MB download), with model files in `~/.cache/kokoro-onnx/`
(`kokoro-v1.0.onnx`, `voices-v1.0.bin` from the kokoro-onnx `model-files-v1.0`
release). It emits a `voice` `log` event with `fallback: true` saying so.
