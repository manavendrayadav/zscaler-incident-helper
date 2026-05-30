# ADR-005: Remove DeepSeek as an LLM Provider

**Status:** Accepted  
**Date:** 2026-05-28  
**Deciders:** @manavendrayadav

---

## Context

DeepSeek (deepseek-chat, deepseek-reasoner) was initially included as a low-cost LLM provider option. However, DeepSeek's API infrastructure is operated by DeepSeek Artificial Intelligence Co., Ltd., a company incorporated in China, and API requests route through servers located in China.

This project is designed to process **internal Zscaler incident logs, screenshots, and support tickets** — corporate data that may include:
- Internal IP addresses and network topology
- Employee identifiers (usernames, device IDs)
- Security incident details (attack vectors, affected systems)
- Authentication tokens and credentials appearing in logs

Routing this data through a provider subject to Chinese data laws (specifically the 2021 Data Security Law and the 2021 Personal Information Protection Law, which grant Chinese authorities broad data access rights) is unacceptable for this use case.

---

## Decision

Remove `llm/deepseek_provider.py` entirely. Remove `"deepseek"` from `llm/factory.py`, `api/main.py` model routing, and `.env.example`.

Add an explicit comment in documentation explaining the removal rationale so future contributors do not re-add the provider.

---

## Consequences

**Positive:**
- Eliminates the risk of sensitive corporate incident data being processed by a provider subject to Chinese data regulations.
- Reduces the risk of inadvertent data exposure — removing the option prevents misconfigured deployments.

**Negative:**
- DeepSeek models (particularly deepseek-reasoner) had strong performance on technical reasoning tasks. This capability is partially compensated by Groq's llama-3.3-70b-versatile.

---

## Guidance for Future Contributors

Do not re-add DeepSeek or any other provider whose API infrastructure routes data through jurisdictions with broad government data access powers (e.g., China's Data Security Law, Russia). The intended users of this tool handle sensitive corporate security data, and provider data residency must be considered.

Acceptable providers for this project:
- **Groq** — US-based, SOC 2 compliant
- **OpenRouter** — US-based (verify individual model providers)
- **Ollama** — local-only, no external data transmission

---

## References

- China Data Security Law (2021): https://digichina.stanford.edu/work/translation-data-security-law-of-the-peoples-republic-of-china/
- DeepSeek Privacy Policy: https://www.deepseek.com/privacy_policy
