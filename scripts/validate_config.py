"""
Pre-flight configuration validator.
Run before crawl/ingest to catch misconfigured environments early.

Usage:
  python scripts/validate_config.py
  make validate-config
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from rich.console import Console

console = Console(highlight=False, markup=True, emoji=False)

PASS = "[bold green]PASS[/]"
WARN = "[bold yellow]WARN[/]"
FAIL = "[bold red]FAIL[/]"


def _check(label: str, status: str, detail: str = ""):
    icon = {"PASS": PASS, "WARN": WARN, "FAIL": FAIL}[status]
    line = f"  {icon}  {label}"
    if detail:
        line += f"  [dim]{detail}[/dim]"
    console.print(line)
    return status


def main() -> int:
    from config import cfg

    console.rule("[bold cyan]Zscaler RAG — Config Validator[/]")
    failures = 0
    warnings = 0

    # ── API keys ─────────────────────────────────────────────────────────────
    console.print("\n[bold]API Keys[/]")

    if cfg.GROQ_API_KEY:
        # Quick test: list models (1 token, no cost)
        try:
            r = httpx.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {cfg.GROQ_API_KEY}"},
                timeout=6,
            )
            if r.status_code == 200:
                _check("GROQ_API_KEY", "PASS", "authenticated")
            else:
                _check("GROQ_API_KEY", "WARN", f"HTTP {r.status_code} — key may be invalid")
                warnings += 1
        except Exception as e:
            _check("GROQ_API_KEY", "WARN", f"network error: {e}")
            warnings += 1
    else:
        _check("GROQ_API_KEY", "WARN", "not set — Groq provider will not work")
        warnings += 1

    if cfg.OPENROUTER_API_KEY:
        _check("OPENROUTER_API_KEY", "PASS", "set")
    else:
        _check("OPENROUTER_API_KEY", "WARN", "not set — OpenRouter provider will not work")
        warnings += 1

    # Ollama reachability
    try:
        r = httpx.get(f"{cfg.OLLAMA_BASE_URL}/api/tags", timeout=4)
        models = [m["name"] for m in r.json().get("models", [])]
        _check("OLLAMA_BASE_URL", "PASS", f"reachable — {len(models)} model(s) available")
    except Exception:
        _check("OLLAMA_BASE_URL", "WARN", f"{cfg.OLLAMA_BASE_URL} not reachable — Ollama provider will not work")
        warnings += 1

    at_least_one = cfg.GROQ_API_KEY or cfg.OPENROUTER_API_KEY
    try:
        httpx.get(f"{cfg.OLLAMA_BASE_URL}/api/tags", timeout=3)
        at_least_one = True
    except Exception:
        pass
    if not at_least_one:
        _check("LLM provider", "FAIL", "no provider is configured — set GROQ_API_KEY or OLLAMA_BASE_URL")
        failures += 1

    # ── Qdrant ────────────────────────────────────────────────────────────────
    console.print("\n[bold]Qdrant[/]")
    try:
        r = httpx.get(f"http://{cfg.QDRANT_HOST}:{cfg.QDRANT_PORT}/health", timeout=5)
        if r.status_code == 200:
            _check("Qdrant", "PASS", f"{cfg.QDRANT_HOST}:{cfg.QDRANT_PORT} healthy")
        else:
            _check("Qdrant", "FAIL", f"HTTP {r.status_code}")
            failures += 1
    except Exception as e:
        _check("Qdrant", "FAIL", f"not reachable at {cfg.QDRANT_HOST}:{cfg.QDRANT_PORT} — {e}")
        failures += 1

    # ── Embedding dim consistency ─────────────────────────────────────────────
    console.print("\n[bold]Embedding model[/]")
    try:
        from pipeline.embedder import embed_query
        vec = embed_query("test")
        actual_dim = len(vec)
        if actual_dim == cfg.EMBEDDING_DIM:
            _check(f"{cfg.EMBEDDING_MODEL}", "PASS", f"dim={actual_dim}")
        else:
            _check(
                f"{cfg.EMBEDDING_MODEL}", "FAIL",
                f"model outputs dim={actual_dim} but EMBEDDING_DIM={cfg.EMBEDDING_DIM} — update config",
            )
            failures += 1
    except Exception as e:
        _check(cfg.EMBEDDING_MODEL, "WARN", f"could not load model: {e}")
        warnings += 1

    # ── Security checks ────────────────────────────────────────────────────────
    console.print("\n[bold]Security[/]")

    if cfg.API_KEY == "zscaler-rag":
        _check("API_KEY", "WARN", "using default value — change before team deployment")
        warnings += 1
    else:
        _check("API_KEY", "PASS", "custom key set")

    if cfg.ALLOWED_ORIGINS == ["http://localhost:3000"]:
        _check("ALLOWED_ORIGINS", "WARN", "localhost only — add your team's OpenWebUI URL for deployment")
        warnings += 1
    elif "*" in cfg.ALLOWED_ORIGINS:
        _check("ALLOWED_ORIGINS", "FAIL", "wildcard '*' — restrict to specific origins")
        failures += 1
    else:
        _check("ALLOWED_ORIGINS", "PASS", f"{cfg.ALLOWED_ORIGINS}")

    # ── Summary ───────────────────────────────────────────────────────────────
    console.print()
    console.rule()
    if failures:
        console.print(f"[bold red]{failures} failure(s), {warnings} warning(s) — fix failures before proceeding[/]")
        return 1
    elif warnings:
        console.print(f"[bold yellow]{warnings} warning(s) — review before team deployment[/]")
        return 0
    else:
        console.print("[bold green]All checks passed.[/]")
        return 0


if __name__ == "__main__":
    sys.exit(main())
