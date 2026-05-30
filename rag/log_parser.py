"""
Zscaler log detection and signal extraction.

Used by api/main.py to:
  1. Detect whether a user message contains structured log output
  2. Extract searchable signals (error codes, product keywords) for Qdrant retrieval
     Using Drain3 for template-based extraction when available, regex fallback otherwise
  3. Auto-detect the Zscaler product from log content (ZIA / ZPA / ZDX)
"""

import re

# ── Patterns ──────────────────────────────────────────────────────────────────

_TIMESTAMP_PATTERNS = [
    re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"),          # ISO 8601 / syslog
    re.compile(r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}"),            # MM/DD/YYYY HH:MM
    re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+\s+\d{2}:\d{2}", re.I),
    re.compile(r"\[\d{4}-\d{2}-\d{2}"),                         # [2026-05-28...
]

_ERROR_KEYWORDS = [
    "ERROR", "WARN", "WARNING", "CRITICAL", "FATAL",
    "FAILED", "FAILURE", "TIMEOUT", "TIMED_OUT",
    "AUTH_FAILED", "AUTHENTICATION_FAILED",
    "TUNNEL_DOWN", "TUNNEL_FAILED",
    "SSL_ERROR", "TLS_ERROR", "CERT_ERROR",
    "CONNECTION_REFUSED", "CONNECTION_RESET", "UNREACHABLE",
    "ACCESS_DENIED", "UNAUTHORIZED",
    "CONNECTOR_DOWN", "BROKER_UNREACHABLE",
]

_ZSCALER_KEYWORDS = [
    "zscaler", "zia", "zpa", "zdx", "zcc",
    "connector", "app connector",
    "broker", "z-broker",
    "gateway", "cloud gateway",
    "pac", "pac-file", "z-tunnel",
    "ssl inspection", "ssl-inspection",
    "forwarding", "traffic forwarding",
    "enrollment", "oauth",
    "policy", "access policy",
    "nanolog", "nss",
]

_ERROR_CODE_RE = re.compile(
    r"(?:error|code|status|reason|result)[:\s=]+([A-Z][A-Z0-9_]{2,})", re.I
)

_PRODUCT_ZPA_HINTS = ["zpa", "app connector", "private access", "broker", "z-broker",
                       "zpa.net", "enrollment", "oauth", "microsegmentation"]
_PRODUCT_ZIA_HINTS = ["zia", "internet access", "pac file", "pac-file", "ssl inspection",
                       "z-tunnel", "ztunnel", "web proxy", "forwarding", "nanolog", "nss"]
_PRODUCT_ZDX_HINTS = ["zdx", "digital experience", "zdx.net", "experience score"]


# ── Public API ────────────────────────────────────────────────────────────────

def is_log_content(text: str) -> bool:
    """
    Return True if the text looks like structured log output.

    Heuristics (all must pass):
    - At least 3 newlines (multi-line content)
    - Contains at least one timestamp pattern OR at least 2 error keywords
    """
    if text.count("\n") < 3:
        return False

    has_timestamp = any(p.search(text) for p in _TIMESTAMP_PATTERNS)
    if has_timestamp:
        return True

    # Timestamp-free logs (some ZPA connector logs omit them)
    text_upper = text.upper()
    error_hits = sum(1 for kw in _ERROR_KEYWORDS if kw in text_upper)
    zscaler_hits = sum(1 for kw in _ZSCALER_KEYWORDS if kw.upper() in text_upper)
    return error_hits >= 2 and zscaler_hits >= 1


_drain_miner = None


def _get_drain_miner():
    global _drain_miner
    if _drain_miner is None:
        try:
            from drain3 import TemplateMiner
            from drain3.template_miner_config import TemplateMinerConfig
            config = TemplateMinerConfig()
            config.drain_depth = 4
            config.drain_sim_th = 0.4
            _drain_miner = TemplateMiner(config=config)
        except ImportError:
            _drain_miner = False  # drain3 not available — use regex fallback
    return _drain_miner


def _drain_extract(text: str) -> list[str]:
    """Use Drain3 to extract log templates and named variables as signals."""
    miner = _get_drain_miner()
    if not miner:
        return []

    # Feed each line and collect discovered templates + parameter tokens
    signals: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            result = miner.add_log_message(line)
            if result:
                template = result.get("template_mined", "")
                # Extract concrete parameter values from the log line
                # by comparing template (has <*> wildcards) to actual line
                params = re.findall(r"(?:=|:)\s*([A-Z][A-Z0-9_\-]{2,})", line)
                for p in params[:3]:
                    signals.append(p.lower().replace("_", " "))
                # Also grab template keywords (skip <*>)
                for word in template.split():
                    if word != "<*>" and len(word) > 3 and word.upper() in _ERROR_KEYWORDS:
                        signals.append(word.lower())
        except Exception:
            continue
    return signals


def extract_log_signals(text: str) -> str:
    """
    Extract a concise search query from raw log content for Qdrant retrieval.

    Uses Drain3 template mining to extract structured parameters, with regex
    fallback for keyword and error-code extraction.

    Returns a space-joined string of unique signals (≤15 terms).
    Falls back to the first 200 characters of text if nothing is found.
    """
    signals: list[str] = []
    text_upper = text.upper()

    # Drain3 template-based extraction (primary)
    drain_signals = _drain_extract(text)
    signals.extend(drain_signals)

    # Error keywords (always run — Drain3 may miss some)
    for kw in _ERROR_KEYWORDS:
        if kw in text_upper:
            signals.append(kw.lower().replace("_", " "))

    # Zscaler component keywords
    for kw in _ZSCALER_KEYWORDS:
        if kw.upper() in text_upper:
            signals.append(kw.lower())

    # Explicit error codes from regex
    codes = _ERROR_CODE_RE.findall(text)
    for code in codes[:5]:
        signals.append(code.lower().replace("_", " "))

    # Deduplicate preserving order
    seen: set[str] = set()
    unique_signals: list[str] = []
    for s in signals:
        if s not in seen:
            seen.add(s)
            unique_signals.append(s)

    result = " ".join(unique_signals[:15])
    return result if result else text[:200]


def detect_product_from_logs(text: str) -> str | None:
    """
    Try to infer the Zscaler product from log content.

    Returns 'zpa', 'zia', 'zdx', or None if ambiguous / not detected.
    Confidence is based on keyword hit count — highest wins.
    """
    text_lower = text.lower()

    scores = {
        "zpa": sum(1 for h in _PRODUCT_ZPA_HINTS if h in text_lower),
        "zia": sum(1 for h in _PRODUCT_ZIA_HINTS if h in text_lower),
        "zdx": sum(1 for h in _PRODUCT_ZDX_HINTS if h in text_lower),
    }

    best_product = max(scores, key=lambda k: scores[k])
    best_score   = scores[best_product]

    if best_score == 0:
        return None

    # Require a clear winner (at least 1 point ahead of runner-up)
    sorted_scores = sorted(scores.values(), reverse=True)
    if len(sorted_scores) >= 2 and sorted_scores[0] == sorted_scores[1]:
        return None  # tie → ambiguous

    return best_product
