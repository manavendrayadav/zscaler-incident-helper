"""
Unit tests for config.py

Tests environment variable loading, type coercion, and defaults.
"""

import os
from pathlib import Path
from unittest.mock import patch


class TestConfigDefaults:
    """Test default values when no env vars are set."""

    def _fresh_config(self, env_overrides: dict | None = None):
        """Import a fresh Config instance with optional env overrides."""
        import importlib

        env = {
            "GROQ_API_KEY": "",
            "OPENROUTER_API_KEY": "",
        }
        if env_overrides:
            env.update(env_overrides)
        with patch.dict(os.environ, env, clear=False):
            import config as config_module

            importlib.reload(config_module)
            return config_module.Config()

    def test_default_provider_is_groq(self):
        cfg = self._fresh_config()
        assert cfg.DEFAULT_PROVIDER == "groq"

    def test_default_model(self):
        cfg = self._fresh_config()
        assert cfg.DEFAULT_MODEL == "llama-3.3-70b-versatile"

    def test_default_qdrant_port_is_int(self):
        cfg = self._fresh_config()
        assert isinstance(cfg.QDRANT_PORT, int)
        assert cfg.QDRANT_PORT == 6333

    def test_default_embedding_dim_is_1024(self):
        cfg = self._fresh_config()
        assert cfg.EMBEDDING_DIM == 1024

    def test_sparse_enabled_is_bool(self):
        cfg = self._fresh_config()
        assert isinstance(cfg.SPARSE_ENABLED, bool)
        assert cfg.SPARSE_ENABLED is True

    def test_top_k_is_int(self):
        cfg = self._fresh_config()
        assert isinstance(cfg.TOP_K, int)
        assert cfg.TOP_K == 5

    def test_min_score_is_float(self):
        cfg = self._fresh_config()
        assert isinstance(cfg.MIN_SCORE, float)
        assert cfg.MIN_SCORE == 0.3

    def test_allowed_origins_is_list(self):
        cfg = self._fresh_config()
        assert isinstance(cfg.ALLOWED_ORIGINS, list)
        assert "http://localhost:3000" in cfg.ALLOWED_ORIGINS

    def test_data_dir_is_path(self):
        cfg = self._fresh_config()
        assert isinstance(cfg.DATA_DIR, Path)

    def test_raw_dir_is_subdir_of_data(self):
        cfg = self._fresh_config()
        assert cfg.RAW_DIR == cfg.DATA_DIR / "raw"

    def test_manifest_file_is_json(self):
        cfg = self._fresh_config()
        assert cfg.MANIFEST_FILE.suffix == ".json"


class TestConfigEnvOverrides:
    """Test that env vars correctly override defaults."""

    def _cfg_with(self, **kwargs):
        import importlib

        with patch.dict(os.environ, {k: str(v) for k, v in kwargs.items()}, clear=False):
            import config as config_module

            importlib.reload(config_module)
            return config_module.Config()

    def test_groq_api_key_set(self):
        cfg = self._cfg_with(GROQ_API_KEY="gsk_test123")
        assert cfg.GROQ_API_KEY == "gsk_test123"

    def test_qdrant_port_overridden(self):
        cfg = self._cfg_with(QDRANT_PORT="6334")
        assert cfg.QDRANT_PORT == 6334
        assert isinstance(cfg.QDRANT_PORT, int)

    def test_sparse_disabled(self):
        cfg = self._cfg_with(SPARSE_ENABLED="false")
        assert cfg.SPARSE_ENABLED is False

    def test_allowed_origins_multiple(self):
        cfg = self._cfg_with(ALLOWED_ORIGINS="http://localhost:3000,http://myserver:3000")
        assert len(cfg.ALLOWED_ORIGINS) == 2
        assert "http://myserver:3000" in cfg.ALLOWED_ORIGINS

    def test_custom_collection_name(self):
        cfg = self._cfg_with(COLLECTION_NAME="my_custom_collection")
        assert cfg.COLLECTION_NAME == "my_custom_collection"
