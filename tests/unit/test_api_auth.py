"""
Unit tests for API authentication (api/main.py verify_api_key).

Tests the critical auth fix: empty/missing Authorization header must return 401.
Uses FastAPI's TestClient — no Docker required.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture(scope="module")
def client():
    """
    Create a TestClient for the FastAPI app.
    Patches heavy startup (model loading, Qdrant) so tests run fast.
    """
    with patch("pipeline.embedder.get_model"), \
         patch("rag.retriever.QdrantClient"):
        from api.main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


class TestApiKeyAuth:
    def test_missing_auth_header_returns_401(self, client):
        """Empty Authorization header must NOT silently pass — this was the auth bypass bug."""
        resp = client.get("/v1/models")
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, client):
        resp = client.get("/v1/models", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 401

    def test_bearer_prefix_required(self, client):
        """Key without 'Bearer ' prefix must fail."""
        resp = client.get("/v1/models", headers={"Authorization": "zscaler-rag"})
        assert resp.status_code == 401

    def test_correct_key_returns_200(self, client):
        resp = client.get("/v1/models", headers={"Authorization": "Bearer zscaler-rag"})
        assert resp.status_code == 200

    def test_health_endpoint_requires_no_auth(self, client):
        """Health check must be publicly accessible for Docker health checks."""
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_models_response_structure(self, client):
        resp = client.get("/v1/models", headers={"Authorization": "Bearer zscaler-rag"})
        body = resp.json()
        assert "data" in body
        assert isinstance(body["data"], list)
        assert len(body["data"]) > 0
        assert "id" in body["data"][0]

    def test_chat_completions_missing_auth_returns_401(self, client):
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "zscaler-rag/groq-llama-3-1-8b-instant",
                  "messages": [{"role": "user", "content": "Hi"}]},
        )
        assert resp.status_code == 401

    def test_empty_bearer_value_returns_401(self, client):
        """'Authorization: Bearer ' with nothing after the space must return 401."""
        resp = client.get("/v1/models", headers={"Authorization": "Bearer "})
        assert resp.status_code == 401
