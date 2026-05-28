from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).parent / ".env")


class Config:
    # LLM providers
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    DEFAULT_PROVIDER: str = os.getenv("DEFAULT_PROVIDER", "groq")
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "llama-3.3-70b-versatile")

    # Qdrant
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
    COLLECTION_NAME: str = os.getenv("COLLECTION_NAME", "zscaler_docs")

    # Embeddings
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024"))
    SPARSE_ENABLED: bool = os.getenv("SPARSE_ENABLED", "true").lower() == "true"

    # RAG tuning
    TOP_K: int = int(os.getenv("TOP_K", "5"))
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1500"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "150"))

    # API
    API_KEY: str = os.getenv("API_KEY", "zscaler-rag")
    ALLOWED_ORIGINS: list[str] = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

    # RAG quality
    MIN_SCORE: float = float(os.getenv("MIN_SCORE", "0.3"))

    # Crawl4AI Docker service
    CRAWL4AI_BASE_URL: str = os.getenv("CRAWL4AI_BASE_URL", "http://localhost:11235")

    # Data paths
    DATA_DIR: Path = Path(__file__).parent / "data"
    RAW_DIR: Path = DATA_DIR / "raw"
    MANIFEST_FILE: Path = DATA_DIR / "crawl_manifest.json"

    def __init__(self):
        self.RAW_DIR.mkdir(parents=True, exist_ok=True)


cfg = Config()
