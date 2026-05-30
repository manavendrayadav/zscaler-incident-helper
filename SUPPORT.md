# Support

## Before asking for help

Run these checks first — they resolve most issues without needing to file a ticket:

```bash
make doctor          # check all services, API keys, chunk count
make validate-config # check .env configuration
```

Review [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — it covers the 30 most common issues with root causes and fixes.

---

## Asking a question

For general usage questions, configuration help, or "how do I...":

1. Search existing [GitHub Issues](https://github.com/manavendrayadav/zscaler-rag/issues)
2. Open a new issue with the **Question** label if not already answered
3. Include the output of `make doctor` in your question

---

## Reporting a bug

1. Verify the bug is in this project (not in Qdrant, OpenWebUI, or the LLM provider)
2. Open a [GitHub Issue](https://github.com/manavendrayadav/zscaler-rag/issues/new/choose) using the **Bug Report** template
3. Include: `make doctor` output, error message, steps to reproduce, OS and Docker version

---

## Reporting a security vulnerability

**Do not use GitHub Issues for security vulnerabilities.**

Email: **manavendrayadav2@gmail.com**

See [SECURITY.md](SECURITY.md) for the full disclosure policy.

---

## Response time expectations

| Type | Expected response |
|------|------------------|
| Security vulnerability | Acknowledgement within 48 hours |
| Bug report | Triage within 1 week |
| Feature request | Reviewed monthly |
| Questions | Best-effort; community may answer faster |

This is a community project maintained in spare time. Response times are not guaranteed.
