"""
Shared pytest fixtures for the Zscaler RAG test suite.

All fixtures here avoid loading heavy ML models (bge-m3, cross-encoder).
Tests that need real models should be marked @pytest.mark.integration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ── Path helpers ──────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent


# ── Sample data ───────────────────────────────────────────────────────────────

SAMPLE_CHUNKS = [
    {
        "chunk_id": "abc001",
        "text": "ZPA App Connector enrollment fails when the authentication certificate is expired.",
        "metadata": {
            "url": "https://help.zscaler.com/zpa/troubleshooting-app-connectors",
            "title": "Troubleshooting App Connectors",
            "section": "Authentication Issues",
            "product": "zpa",
        },
    },
    {
        "chunk_id": "abc002",
        "text": "ZIA SSL inspection can cause AUTH_FAILED errors for SAML-based authentication.",
        "metadata": {
            "url": "https://help.zscaler.com/zia/troubleshooting-ssl-inspection",
            "title": "Troubleshooting SSL Inspection",
            "section": "SAML Issues",
            "product": "zia",
        },
    },
    {
        "chunk_id": "abc003",
        "text": "ZDX digital experience monitoring tracks latency and packet loss for end users.",
        "metadata": {
            "url": "https://help.zscaler.com/zdx/about-zdx",
            "title": "About ZDX",
            "section": "Overview",
            "product": "zdx",
        },
    },
]


@pytest.fixture
def sample_chunks() -> list[dict[str, Any]]:
    """Return a small list of realistic chunk dicts for unit tests."""
    return [dict(c) for c in SAMPLE_CHUNKS]


@pytest.fixture
def sample_log_text() -> str:
    """Return multi-line ZPA log content for log_parser tests."""
    return (FIXTURES_DIR / "sample_logs.txt").read_text()


# ── Mock embedder ─────────────────────────────────────────────────────────────

MOCK_DENSE_VEC = np.random.rand(1024).astype(np.float32)
MOCK_SPARSE_VEC = {"531": 0.8, "1024": 0.5, "2048": 0.3}


@pytest.fixture
def mock_embed_query_hybrid():
    """
    Patch embed_query to return a pre-computed hybrid vector (dense+sparse dict).
    Prevents loading the bge-m3 model in unit tests.
    """
    with patch("rag.retriever.embed_query") as mock:
        mock.return_value = {
            "dense": MOCK_DENSE_VEC.tolist(),
            "sparse": MOCK_SPARSE_VEC,
        }
        yield mock


@pytest.fixture
def mock_embed_query_dense():
    """Patch embed_query to return a dense-only vector list."""
    with patch("rag.retriever.embed_query") as mock:
        mock.return_value = MOCK_DENSE_VEC.tolist()
        yield mock


# ── Mock Qdrant ───────────────────────────────────────────────────────────────


def _make_qdrant_point(chunk: dict) -> MagicMock:
    """Build a fake Qdrant ScoredPoint from a chunk dict."""
    point = MagicMock()
    point.id = chunk["chunk_id"]
    point.score = 0.85
    point.payload = {"text": chunk["text"], **chunk["metadata"]}
    return point


@pytest.fixture
def mock_qdrant_client(sample_chunks):
    """
    Patch QdrantClient so retriever tests don't need a running Qdrant.
    Returns the first 2 sample chunks as search results.
    """
    with patch("rag.retriever.QdrantClient") as MockClient:
        client_instance = MockClient.return_value
        mock_results = MagicMock()
        mock_results.points = [_make_qdrant_point(c) for c in sample_chunks[:2]]
        client_instance.query_points.return_value = mock_results
        client_instance.search.return_value = [_make_qdrant_point(c) for c in sample_chunks[:2]]
        yield client_instance


# ── Mock LLM provider ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm_response():
    """Return a fixed LLMResponse-like object for generator tests."""
    response = MagicMock()
    response.content = (
        "## Root Cause\nThe connector authentication failed.\n## Resolution\nRenew the certificate."
    )
    response.prompt_tokens = 100
    response.completion_tokens = 50
    return response


@pytest.fixture
def mock_generate(mock_llm_response):
    """Patch rag.generator.generate to return a fixed response."""
    with patch("rag.generator.generate") as mock:
        mock.return_value = mock_llm_response
        yield mock
