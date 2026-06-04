FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt .
RUN pip install --no-cache-dir --timeout 300 -r requirements-api.txt

# ── Pre-download models at build time ────────────────────────────────────────
# Baking models into the image layer means:
#   - Container starts in <30s instead of 5-10 min (no runtime download)
#   - Health check always passes on cold start
#   - Works fully offline after first `docker compose build`
#
# bge-m3: ~1.5 GB  (dense+sparse hybrid embeddings, MTEB 64.3)
RUN python -c "\
from FlagEmbedding import BGEM3FlagModel; \
model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True); \
print('OK bge-m3 cached')"

# cross-encoder: ~90 MB  (re-ranker for retrieval quality)
RUN python -c "\
from sentence_transformers import CrossEncoder; \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2'); \
print('OK cross-encoder cached')"

# ─────────────────────────────────────────────────────────────────────────────

COPY . .

EXPOSE 8000

# Single-process mode (no --workers flag).
# bge-m3 uses PyTorch internally; forked worker processes corrupt PyTorch's
# thread-pool state causing silent SIGBUS crashes. Single-process mode avoids
# the fork entirely — one uvicorn process handles everything.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
