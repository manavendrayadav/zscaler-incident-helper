# ADR-002: Run uvicorn Without --workers Flag (Single-Process Mode)

**Status:** Accepted  
**Date:** 2026-05-29  
**Deciders:** @manavendrayadav

---

## Context

FastAPI + uvicorn can run in multi-worker mode (`uvicorn --workers N`) to handle concurrent requests across multiple worker processes. This is the standard deployment pattern for high-concurrency production APIs.

The initial Dockerfile used `--workers 1`, which activates uvicorn's subprocess worker mode even for a single worker. When deployed, the rag-api container crashed silently on the first chat completions request — the container exited with code 0 (no Python traceback), the health check subsequently failed, Docker restarted the container, and the cycle repeated.

---

## Root Cause Identified

`--workers 1` activates uvicorn's multiprocessing worker mode: the master process forks a worker subprocess. PyTorch (used internally by bge-m3 and the cross-encoder) is not fork-safe. After `fork()`, the child process inherits a copy of the parent's thread pool state, which is invalid in the child's address space. The first call to `bge-m3.encode()` in the worker process triggers a SIGBUS (bus error) in a C extension thread, killing the worker silently. The master uvicorn process then exits gracefully (code 0) because it treats worker death as a controlled shutdown.

---

## Decision

Remove the `--workers` flag entirely from the uvicorn CMD:

```dockerfile
# Before (broken)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

# After (fixed)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Without `--workers`, uvicorn runs in single-process mode: the main uvicorn process IS the worker. No forking occurs. PyTorch operates correctly in the single process.

---

## Consequences

**Positive:**
- Eliminates the silent crash on first chat completion request.
- Simpler process model — easier to debug.
- Container health check now passes reliably within ~20 seconds.

**Negative:**
- Single-process mode handles requests sequentially. Under high concurrency (many simultaneous users), requests queue. For the expected usage pattern (team of ~10 engineers, non-simultaneous queries), this is acceptable.
- If high concurrency becomes a requirement, the correct fix is to run multiple Docker containers behind a load balancer — NOT to add `--workers` (which would re-introduce the fork issue).

---

## Alternatives Considered

| Alternative | Rejected because |
|-------------|-----------------|
| `--workers 2+` | Multiplies the fork-safety issue; still crashes |
| `uvicorn[standard]` with `--worker-class uvloop` | Same forking mechanism; same issue |
| Gunicorn with `--worker-class uvicorn.workers.UvicornWorker` | Gunicorn also uses fork; same issue |
| `torch.multiprocessing.set_start_method('spawn')` before uvicorn | Complex; requires modifying uvicorn startup sequence |
| Run bge-m3 in a separate process (microservice) | Significant architectural change; deferred to future version |

---

## References

- PyTorch documentation on multiprocessing: https://pytorch.org/docs/stable/multiprocessing.html
- uvicorn `--workers` documentation: https://www.uvicorn.org/deployment/#gunicorn
