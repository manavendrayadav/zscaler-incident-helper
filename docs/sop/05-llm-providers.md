# SOP-05 — LLM Provider Setup

**Audience:** Maintainer configuring or switching LLM providers.
**When:** Initial setup, adding Ollama for privacy mode, or changing the default model.

---

## Provider overview

| Provider | Where data goes | Use for | Requires |
|----------|-----------------|---------|----------|
| Groq | Groq cloud (US) | Fast text queries, no internal data | GROQ_API_KEY |
| OpenRouter | OpenRouter cloud (US) | Wider model selection | OPENROUTER_API_KEY |
| Ollama | Local machine only | Internal logs, screenshots, privacy mode | Docker + GPU optional |

**Privacy rule:** Never send internal Zscaler logs, screenshots, or employee data to
Groq or OpenRouter. Use Ollama for any query containing internal data.

---

## Groq (default text provider)

Groq provides the fastest inference for the llama and Mixtral model families.

```ini
# .env
GROQ_API_KEY=gsk_...
DEFAULT_PROVIDER=groq
DEFAULT_MODEL=llama-3.3-70b-versatile
```

Available models (selectable in OpenWebUI):

| OpenWebUI model ID | Groq model | Notes |
|--------------------|------------|-------|
| `zscaler-rag/groq-llama-3-3-70b-versatile` | llama-3.3-70b-versatile | Best quality, default |
| `zscaler-rag/groq-llama-3-1-8b-instant` | llama-3.1-8b-instant | Fastest, for simple queries |
| `zscaler-rag/groq-mixtral-8x7b-32768` | mixtral-8x7b-32768 | Long context (32k tokens) |
| `zscaler-rag/groq-gemma2-9b-it` | gemma2-9b-it | Google's Gemma2 |

Get your key at `console.groq.com` — free tier is sufficient for team use.

---

## OpenRouter

OpenRouter is a US-based aggregator that routes to many model providers.

```ini
# .env
OPENROUTER_API_KEY=sk-or-...
```

Available models include claude, gpt-4o-mini, llama variants, and Mistral.
Note: OpenRouter routes to DeepSeek models are available but should be avoided
for Zscaler-related queries — DeepSeek's API servers are located in China.

---

## Ollama (local / private LLM)

Ollama runs models entirely on your machine. Nothing leaves your network.
Required for log analysis and screenshot investigation.

### First-time Ollama setup

```bash
make ollama-setup
```

This:
1. Starts the `zscaler-ollama` Docker container (profile: `local-llm`)
2. Pulls `llama3.2` (text) and `llama3.2-vision` (vision)

The Ollama container stores model weights in the `ollama_data` Docker volume,
which persists across restarts. You only need to pull each model once.

### Pull additional vision models

```bash
make ollama-vision
```

Pulls `llava`, `moondream`, and `qwen2-vl:7b`.

Recommended vision model: **`qwen2-vl:7b`** — highest text-in-image accuracy (DocVQA 93.1)
at a reasonable 4GB model size. Requires ~8GB RAM available to Docker.

### Available Ollama models in OpenWebUI

| OpenWebUI model ID | Model | Type | RAM needed |
|--------------------|-------|------|------------|
| `zscaler-rag/ollama-llama3-2` | llama3.2:3b | Text | 4 GB |
| `zscaler-rag/ollama-llama3-1` | llama3.1:8b | Text | 6 GB |
| `zscaler-rag/ollama-mistral` | mistral:7b | Text | 6 GB |
| `zscaler-rag/ollama-qwen2-5` | qwen2.5:7b | Text | 6 GB |
| `zscaler-rag/ollama-llama3-2-vision` | llama3.2-vision | Vision | 8 GB |
| `zscaler-rag/ollama-llava` | llava:7b | Vision | 6 GB |
| `zscaler-rag/ollama-moondream` | moondream:1.8b | Vision | 2 GB |
| `zscaler-rag/ollama-qwen2-vl:7b` | qwen2-vl:7b | Vision | 8 GB |

### GPU acceleration (optional but recommended for vision models)

Without GPU: expect 60–180s per response with vision models.
With GPU: expect 5–15s per response.

To enable NVIDIA GPU:

1. Install the NVIDIA Container Toolkit on the host:
   ```bash
   # Ubuntu example
   distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
   curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
   curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
     sudo tee /etc/apt/sources.list.d/nvidia-docker.list
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

3. Restart the Ollama container:
   ```bash
   docker compose --profile local-llm up -d ollama
   ```

4. Verify GPU is visible inside the container:
   ```bash
   docker exec zscaler-ollama nvidia-smi
   ```

---

## Changing the default provider and model

Edit `.env`:

```ini
DEFAULT_PROVIDER=ollama       # groq | openrouter | ollama
DEFAULT_MODEL=llama3.2        # provider-specific model name
```

Restart rag-api to apply:

```bash
docker compose restart rag-api
```

The default is used when OpenWebUI does not specify a model. Individual queries can
still select any provider by choosing a different model in the OpenWebUI dropdown.

---

## Testing a provider from the CLI

```bash
# Test Groq
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer zscaler-rag" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "zscaler-rag/groq-llama-3-3-70b-versatile",
    "messages": [{"role": "user", "content": "What is ZPA?"}]
  }' | python -m json.tool | grep content

# Test Ollama (must be running)
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer zscaler-rag" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "zscaler-rag/ollama-llama3-2",
    "messages": [{"role": "user", "content": "What is ZPA?"}]
  }' | python -m json.tool | grep content
```

---

## Adding a new provider

1. Create `llm/{name}_provider.py` implementing `BaseLLMProvider` from `llm/base.py`
2. Register it in `llm/factory.py` — add `"{name}": YourProvider` to `_PROVIDERS`
3. List default models for it in `DEFAULT_MODELS` within the provider class
4. Update this SOP with the provider's privacy posture and model table
