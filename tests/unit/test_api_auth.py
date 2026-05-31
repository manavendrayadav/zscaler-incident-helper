"""
Unit tests for API authentication (api/main.py verify_api_key).

Tests the critical auth fix: empty/missing Authorization header must return 401.
Uses FastAPI's TestClient — no Docker required.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(scope="module")
def client():
    """
    Create a TestClient for the FastAPI app.
    Patches heavy startup (model loading, Qdrant) so tests run fast.
    QdrantClient is imported lazily inside functions in retriever.py and indexer.py,
    so we patch at the qdrant_client module level.
    """
    mock_model = MagicMock()
    mock_qdrant = MagicMock()
    mock_qdrant.return_value.get_collections.return_value.collections = []
    mock_qdrant.return_value.get_collection.return_value.points_count = 0
    mock_qdrant.return_value.get_collection.return_value.status = "green"

    with (
        patch("pipeline.embedder.get_model", return_value=mock_model),
        patch("qdrant_client.QdrantClient", mock_qdrant),
    ):
        from fastapi.testclient import TestClient

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

    def test_key_without_bearer_prefix_also_accepted(self, client):
        """
        The auth handler strips 'Bearer ' then compares the remainder.
        Sending the raw key without the prefix also works (the replace is a no-op).
        This is intentional: clients using the raw key string still authenticate.
        """
        resp = client.get("/v1/models", headers={"Authorization": "zih-api"})
        assert resp.status_code == 200

    def test_correct_key_returns_200(self, client):
        resp = client.get("/v1/models", headers={"Authorization": "Bearer zih-api"})
        assert resp.status_code == 200

    def test_health_endpoint_requires_no_auth(self, client):
        """Health check must be publicly accessible for Docker health checks."""
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_models_response_structure(self, client):
        resp = client.get("/v1/models", headers={"Authorization": "Bearer zih-api"})
        body = resp.json()
        assert "data" in body
        assert isinstance(body["data"], list)
        assert len(body["data"]) > 0
        assert "id" in body["data"][0]

    def test_chat_completions_missing_auth_returns_401(self, client):
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "zih/groq-llama-3-1-8b-instant",
                "messages": [{"role": "user", "content": "Hi"}],
            },
        )
        assert resp.status_code == 401

    def test_empty_bearer_value_returns_401(self, client):
        """'Authorization: Bearer ' with nothing after the space must return 401."""
        resp = client.get("/v1/models", headers={"Authorization": "Bearer "})
        assert resp.status_code == 401
