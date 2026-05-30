# Hardware Requirements

This document answers "can I run this on my machine?" before you invest time in setup.

---

## Quick Answer

| Use case | Minimum spec | Notes |
|----------|-------------|-------|
| Groq queries only (no Ollama) | 8 GB RAM, 4-core CPU, 15 GB disk | Groq runs in the cloud; your machine only runs Docker services |
| Ollama text models | 8 GB RAM, 4-core CPU, 25 GB disk | Adds ~4 GB for Llama 3.2 model weights |
| Ollama vision models | 16 GB RAM, 4-core CPU, 40 GB disk | qwen2-vl:7b = 8 GB weights |
| GPU acceleration (Ollama) | 16 GB RAM, NVIDIA GPU (8 GB VRAM), 40 GB disk | Cuts Ollama inference from ~2 min to ~10 sec |

---

## Detailed Requirements

### RAM

| Service | Idle | Peak |
|---------|------|------|
| rag-api (bge-m3 loaded) | 2.5 GB | 3.5 GB (during embedding query) |
| Qdrant | 0.5 GB | 1 GB |
| OpenWebUI | 0.3 GB | 0.5 GB |
| Crawl4AI | 0.5 GB | 1.5 GB (during crawl, 3 parallel browsers) |
| Ollama llama3.2:3b | 4 GB | 4 GB |
| Ollama qwen2-vl:7b (vision) | 8 GB | 8 GB |
| **Total (Groq mode)** | **~4 GB** | **~7 GB** |
| **Total (Ollama text mode)** | **~8 GB** | **~12 GB** |
| **Total (Ollama vision mode)** | **~12 GB** | **~16 GB** |

**Rule of thumb:**
- Running Groq only: 8 GB RAM minimum
- Running Ollama text: 16 GB RAM recommended
- Running Ollama vision: 24 GB RAM recommended (or use GPU offloading)

### CPU

| Task | CPU usage | Duration |
|------|-----------|----------|
| Docker services idle | Low (< 5%) | Ongoing |
| bge-m3 query embedding | High (all cores) | 0.2–1 second per query |
| bge-m3 full ingest (13,800 chunks) | 100% all cores | ~4 hours |
| Ollama inference (CPU) | High (all cores) | 60–180 seconds per response |
| Ollama inference (GPU) | Low CPU, GPU active | 5–15 seconds per response |
| Crawl4AI (3 parallel pages) | Moderate (30–60%) | Until crawl completes |

**Recommendation:** 8-core CPU significantly reduces the initial 4-hour embedding time and Ollama inference latency.

### Disk space

| Component | Size | Notes |
|-----------|------|-------|
| Docker images (all services) | ~10 GB | rag-api image includes bge-m3 (~2.5 GB) |
| Crawled Markdown files (`data/raw/`) | ~500 MB | 1,825 files |
| Qdrant vector storage | ~2 GB | 13,800 chunks × 1024-dim |
| Ollama llama3.2:3b | ~2 GB | Optional |
| Ollama qwen2-vl:7b | ~5 GB | Optional vision model |
| Ollama llava:7b | ~5 GB | Optional vision model |
| Embeddings cache (`data/embeddings_cache.npz`) | ~60 MB | Temporary; deleted after successful ingest |
| **Total (Groq mode, no Ollama)** | **~13 GB** | |
| **Total (with Ollama + vision)** | **~25 GB** | |

**Recommendation:** 20 GB free disk space for Groq mode. 40 GB for Ollama with vision models.

---

## Setup Time Expectations

| Step | Time on minimum spec | Time on recommended spec | Notes |
|------|---------------------|--------------------------|-------|
| `docker compose up` | 5–10 min (first run, image pulls) | 5–10 min | One-time only |
| `make crawl-all` (1,825 pages) | 60–90 min | 45–60 min | Crawl4AI rate-limited |
| `make ingest` (13,800 chunks) | **3–4 hours** (CPU) | **~30 min** (GPU) | Most of the wait |
| rag-api startup (subsequent) | ~20 seconds | ~20 seconds | Models baked into image |
| Per-query latency (Groq) | 3–8 seconds | 3–8 seconds | Network-limited |
| Per-query latency (Ollama CPU) | 60–180 seconds | 60–120 seconds | CPU-limited |
| Per-query latency (Ollama GPU) | 5–15 seconds | 5–10 seconds | VRAM-limited |

> **The 4-hour embedding is a one-time cost.** After the first `make ingest`, subsequent updates (`make update && make ingest`) only re-embed changed pages — typically 0–50 pages per week.

---

## Windows-Specific Notes

### Docker Desktop WSL2 memory limit

By default, Docker Desktop on Windows uses up to 50% of your physical RAM. With 16 GB RAM, this means Docker gets 8 GB — potentially insufficient for Ollama + rag-api.

**Fix:** Edit `%USERPROFILE%\.wslconfig`:

```ini
[wsl2]
memory=12GB    # increase for Ollama; adjust based on your machine
processors=8   # use more CPU cores for faster embedding
```

Restart Docker Desktop after changing this file.

### WSL2 filesystem performance

The initial embedding (4 hours) reads model weights from Docker's overlay filesystem in WSL2. This is slower than native Linux by 20–30%.

### Path separators

All file paths in the project use forward slashes in Python code — this works on Windows via WSL2/Docker. If running Python scripts directly on Windows PowerShell (outside Docker), paths work correctly due to `pathlib.Path` usage.

---

## GPU Acceleration (NVIDIA)

GPU acceleration dramatically reduces Ollama inference time. **Not required** for basic operation.

### Supported hardware
- NVIDIA GPU with 8+ GB VRAM (for 7B models)
- NVIDIA driver 525+ 
- NVIDIA Container Toolkit

### Setup

1. Install NVIDIA Container Toolkit on the host:
   ```bash
   # Ubuntu/Debian
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
   sudo systemctl restart docker
   ```

2. In `docker-compose.yml`, uncomment the `deploy` block under the `ollama` service:
   ```yaml
   deploy:
     resources:
       reservations:
         devices:
           - driver: nvidia
             count: 1
             capabilities: [gpu]
   ```

3. Restart Ollama: `docker compose --profile local-llm up -d ollama`

4. Verify GPU is visible: `docker exec zscaler-ollama nvidia-smi`

### bge-m3 does NOT use GPU

The bge-m3 embedding model (used for ingest and query embedding) runs on CPU inside the Docker container. GPU acceleration for bge-m3 is not currently configured. This only affects the initial 4-hour ingest — per-query embedding takes <1 second regardless.

---

## Network Requirements

The following outbound HTTPS connections are required during setup:

| Destination | Port | Purpose | When needed |
|-------------|------|---------|-------------|
| `hub.docker.com`, `ghcr.io` | 443 | Docker image pulls | First `make up` only |
| `help.zscaler.com` | 443 | Crawling documentation pages | `make crawl-all` and `make update` |
| `api.groq.com` | 443 | Groq LLM queries | Every Groq-model query |
| `openrouter.ai` | 443 | OpenRouter queries | Every OpenRouter-model query |
| `huggingface.co` | 443 | Model downloads (bge-m3, cross-encoder) | First `docker compose build rag-api` |

**Ollama queries use no outbound connections** — all inference is local.

### Corporate proxy / Zscaler ZCC considerations

If you're running this on a machine with Zscaler Client Connector (ZCC) installed:
- ZCC intercepts HTTPS traffic from Docker containers
- Docker containers don't trust the Zscaler root CA by default
- This causes SSL errors when the rag-api container calls `api.groq.com`

**Fix options:**
1. Export the Zscaler root CA and inject it into the Docker image (see [TROUBLESHOOTING.md](TROUBLESHOOTING.md))
2. Add `api.groq.com` to the Zscaler SSL inspection bypass list
3. Use Ollama only (no external API calls)
