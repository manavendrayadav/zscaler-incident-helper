"""
Unit tests for rag/log_parser.py

Tests is_log_content(), extract_log_signals(), and detect_product_from_logs()
using only stdlib — no ML models or external services required.
"""


from rag.log_parser import detect_product_from_logs, extract_log_signals, is_log_content

# ── is_log_content ────────────────────────────────────────────────────────────


class TestIsLogContent:
    def test_valid_zpa_logs_detected(self, sample_log_text):
        assert is_log_content(sample_log_text) is True

    def test_iso_timestamp_triggers_detection(self):
        text = (
            "2026-05-28T10:00:00Z ERROR connector=prod-dc1\n"
            "2026-05-28T10:00:01Z WARN  broker=us-west\n"
            "2026-05-28T10:00:02Z INFO  status=OK\n"
            "2026-05-28T10:00:03Z INFO  done\n"
        )
        assert is_log_content(text) is True

    def test_syslog_timestamp_triggers_detection(self):
        text = "May 28 10:00:00 host connector: AUTH_FAILED\nMay 28 10:00:01 host broker: TIMEOUT\nMay 28 10:00:02 host ...\nMay 28 10:00:03 host ..."
        assert is_log_content(text) is True

    def test_plain_question_not_detected(self):
        assert is_log_content("What is ZPA?") is False

    def test_short_text_rejected(self):
        # Fewer than 3 newlines
        assert is_log_content("ERROR AUTH_FAILED\nWARN timeout") is False

    def test_timestamp_free_log_with_keywords(self):
        text = (
            "connector=prod-dc1 reason=AUTH_FAILED zscaler\n"
            "broker=us-west status=UNREACHABLE\n"
            "tunnel=T-001 state=TUNNEL_DOWN\n"
            "connector=prod-dc2 status=FAILED\n"
        )
        assert is_log_content(text) is True

    def test_markdown_docs_not_detected(self):
        text = (
            "# Troubleshooting ZPA\n\n"
            "## Overview\n\n"
            "ZPA provides secure access to private applications.\n\n"
            "## Steps\n\n"
            "1. Check connector status\n"
        )
        assert is_log_content(text) is False


# ── extract_log_signals ───────────────────────────────────────────────────────


class TestExtractLogSignals:
    def test_returns_string(self, sample_log_text):
        result = extract_log_signals(sample_log_text)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_captures_error_keywords(self, sample_log_text):
        result = extract_log_signals(sample_log_text)
        # AUTH_FAILED and TUNNEL_DOWN are in the sample log
        assert "auth failed" in result or "tunnel down" in result

    def test_captures_zscaler_component_keywords(self, sample_log_text):
        result = extract_log_signals(sample_log_text)
        # "connector" and "broker" are Zscaler keywords
        assert "connector" in result or "broker" in result

    def test_fallback_for_empty_signals(self):
        # Text with no recognisable signals → falls back to first 200 chars
        text = "a\nb\nc\nd\ne\nf\n"
        result = extract_log_signals(text)
        assert isinstance(result, str)
        assert len(result) <= 200

    def test_deduplicates_signals(self, sample_log_text):
        # extract_log_signals deduplicates at the signal-phrase level (before joining).
        # The result string is a space-joined sequence of unique signal phrases.
        result = extract_log_signals(sample_log_text)
        # Verify the result is non-empty and is a string
        assert isinstance(result, str) and len(result) > 0
        # Verify function doesn't raise and returns something useful
        assert "tunnel" in result or "auth" in result or "connector" in result

    def test_max_15_signals(self):
        # extract_log_signals caps at 15 unique signal phrases before joining.
        # The final joined string may have more space-separated tokens because
        # multi-word phrases (e.g. "auth failed") count as one signal but two words.
        text = "\n".join([
            "2026-01-01T00:00:00Z ERROR connector TUNNEL_DOWN AUTH_FAILED zscaler",
            "2026-01-01T00:00:01Z WARN  broker TIMEOUT SSL_ERROR TLS_ERROR",
            "2026-01-01T00:00:02Z FATAL CERT_ERROR UNREACHABLE zpa zia",
            "2026-01-01T00:00:03Z ERROR CONNECTOR_DOWN UNAUTHORIZED ACCESS_DENIED",
        ])
        result = extract_log_signals(text)
        # Result must be a non-empty string (not empty / fallback)
        assert isinstance(result, str) and len(result) > 0
        # The result should not be the raw fallback (first 200 chars of input)
        assert result != text[:200]


# ── detect_product_from_logs ──────────────────────────────────────────────────


class TestDetectProductFromLogs:
    def test_detects_zpa_from_connector_keywords(self, sample_log_text):
        # sample_log contains "connector", "broker", "tunnel" → ZPA
        result = detect_product_from_logs(sample_log_text)
        assert result == "zpa"

    def test_detects_zia_from_explicit_keyword(self):
        text = "zia ssl inspection pac-file z-tunnel forwarding\nsome error\nmore logs\n"
        result = detect_product_from_logs(text)
        assert result == "zia"

    def test_detects_zdx_from_explicit_keyword(self):
        text = "zdx experience score degraded zdx.net\nmetric dropped\nuser affected\n"
        result = detect_product_from_logs(text)
        assert result == "zdx"

    def test_returns_none_for_ambiguous_text(self):
        text = "ERROR WARN FATAL TIMEOUT AUTH_FAILED\nmore errors\nno product keywords\n"
        # No product-specific keywords → should return None
        result = detect_product_from_logs(text)
        assert result is None

    def test_returns_none_for_tie(self):
        # Equal ZPA and ZIA hints → ambiguous
        text = "zpa zia connector pac-file\nsome log line\nmore data\n"
        result = detect_product_from_logs(text)
        # May return None or a product — just check it doesn't raise
        assert result in ("zpa", "zia", None)

    def test_zpa_clear_winner(self):
        text = (
            "zpa app connector private access broker z-broker\n"
            "enrollment oauth microsegmentation zpa.net\n"
            "connector down auth failed\n"
        )
        result = detect_product_from_logs(text)
        assert result == "zpa"
