# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x.x   | ✅ Yes     |

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

Report security issues by emailing: **manavendrayadav2@gmail.com**

Include in your report:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

You will receive an acknowledgement within **48 hours** and a resolution timeline within **7 days**.

## Privacy & Data Handling

This tool is designed to process **internal Zscaler incident logs and screenshots**. Please read these guidelines carefully before deploying:

### Data that stays local
- All content sent to **Ollama** models stays entirely on your machine — nothing leaves your network
- Crawled Zscaler documentation (`data/raw/`) is stored locally and excluded from git
- Vector embeddings (`qdrant_storage/`) are stored in a local Docker volume

### Data that leaves your machine
- Queries sent to **Groq** are processed on Groq's US-based servers
- Queries sent to **OpenRouter** are processed on OpenRouter's US-based servers
- **Never send internal logs, employee data, or sensitive incident details to Groq or OpenRouter**

### Recommended deployment
- Use **Ollama** for any query containing internal Zscaler logs, screenshots, or employee/system identifiers
- Reserve Groq/OpenRouter for general Zscaler documentation questions with no sensitive data

### API authentication
- The RAG API uses Bearer token authentication on all `/v1/*` endpoints
- Change the default `API_KEY=zscaler-rag` before team deployment
- Set `ALLOWED_ORIGINS` to your specific OpenWebUI hostname — never use `*` in production

## Scope

The following are **in scope** for security reports:
- Authentication bypass in the RAG API
- Injection attacks via chat completions payload
- Sensitive data leakage in API responses or logs
- Docker container escape or privilege escalation

The following are **out of scope**:
- Vulnerabilities in third-party dependencies (Qdrant, OpenWebUI, Groq) — report those upstream
- Denial-of-service attacks (no SLA guarantee for self-hosted deployments)
