# Deployment: home server and GPU PC

Status: proposal (2026-11-20), based on the owner's self-hosting plan. Nothing here is installed yet; ports and services are targets, not facts. Items marked **Open** need the owner's answer.

## Topology

| Machine | Role | Runs |
| --- | --- | --- |
| Dell OptiPlex 7050 (always on, Ubuntu Server 24.04 LTS) | App server | Docker Compose: Skarbonka API, built frontend, PostgreSQL 17 + pgvector, CPU embedding model (from M6). Other services of the owner (LiteLLM, Open WebUI) may share the box. |
| PC with RTX 2070 8 GB (Windows + WSL2, not always on) | Inference only | `llama-server` (llama.cpp) or Ollama, exposing an OpenAI-compatible `/v1` on the LAN/tailnet |
| Laptop / PC WSL | Development | Repo, tests, CI parity. Real exports stay out of the repo as before |

Skarbonka never depends on the GPU PC being awake for anything except the optional LLM tier.

## Network and access

- Remote access only through **Tailscale**. Nothing is published to the internet; no Cloudflare Tunnel (it terminates TLS on Cloudflare's edge), no port forwarding, no public domain.
- Tailscale ACLs: the Skarbonka port is reachable only from the owner's devices; parent devices are added in stage 5.
- The API binds to the tailnet/LAN interface, never `0.0.0.0` on a public interface.
- The only outbound traffic: NBP exchange rates (M3.5, requests carry currency codes and dates only) and the Gmail draft (M11).

## LLM access

- The app talks **OpenAI-compatible `chat.completions`** to a configurable endpoint: `SKARBONKA_LLM_BASE_URL`, `SKARBONKA_LLM_MODEL`. This works with `llama-server`, Ollama (`/v1`) and LiteLLM alike, so the runtime can change without code changes.
- **Local-only guard:** at startup the app refuses an LLM base URL whose host is not loopback, a private range (RFC 1918), the Tailscale range (100.64.0.0/10) or a `*.ts.net` name. A gate test covers it. This makes "no financial data to cloud models" a check, not a promise.
- **Open: direct vs. LiteLLM.** The owner's gateway on the OptiPlex mixes local aliases with cloud ones (DeepSeek, Kimi, OpenRouter). Recommended: Skarbonka calls the GPU PC directly. If it goes through LiteLLM, it gets its own virtual key whose model allowlist holds only local aliases, with no `fallbacks` to cloud models for those aliases (a fallback would silently send transaction text to a cloud API). The guard above cannot see past LiteLLM, so this config is part of the security boundary.
- LLM tracing (e.g. Langfuse) stores prompts, which contain transaction descriptions. Off by default; if enabled, self-hosted only.

## When the GPU PC is asleep

- Categorization order stays: manual → rules → merchant memory → ML → LLM → review queue. Rules and ML run on the OptiPlex CPU and cover most rows.
- Rows that need the LLM get status `pending_llm` and are processed when the endpoint's health check passes. **There is never a cloud fallback.**
- Later option: Wake-on-LAN from the OptiPlex before a batch. Not in the MVP.

## Models and vectors

- Vectors live in the Skarbonka Postgres (pgvector). No Qdrant for Skarbonka.
- Embeddings run on the OptiPlex CPU (candidates: Qwen3-Embedding 0.6B, BGE-M3); chosen in M6 on fixtures and on the owner's aggregate metrics.
- LLM candidates (8 GB VRAM, one model at a time): Qwen3.5 9B, Ministral 8B, Gemma 4 E4B, Bielik 11B at the edge. Chosen after `llama-bench` and an eval on the owner's data, run by the owner.

## Data at rest

- Real exports are uploaded through the UI over the tailnet and stored on the OptiPlex in a folder outside the repo and outside Docker images.
- Recommended: full-disk encryption (LUKS) on the OptiPlex, since it holds the bank history.
- Postgres binds to the Docker network only (no published port in the production compose file).

## Backups

- Nightly `pg_dump -Fc`, encrypted with `age` before it leaves the container, kept 7 daily + 4 weekly.
- Target: **Open** (external disk on the OptiPlex, another machine on the LAN, or off-site; off-site only as client-side encrypted files).
- Monthly restore test into a scratch database, scripted.
- Not backed up: model files (re-downloadable), Docker images.

## Open questions for the owner

1. Direct to the GPU PC, or through LiteLLM with a local-only key?
2. OptiPlex variant, RAM and disk size (sets the RAM budget next to LiteLLM and Open WebUI).
3. Backup target.
4. `llama-server` or Ollama as the runtime on the PC (the app does not care; the docs and the setup guide do).
