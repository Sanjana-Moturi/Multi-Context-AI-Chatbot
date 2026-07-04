""
import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY: str   = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str     = os.getenv("GROQ_MODEL", "")

TOP_K: int    = int(os.getenv("TOP_K", "5"))

EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM: int   = 384

CHUNK_SIZE: int    = 1200
CHUNK_OVERLAP: int = 250

DATA_DIR="../data"