import os
import sys
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

@dataclass
class Config:
    api_id: int
    api_hash: str
    phone_number: str
    chat_id: int
    download_dir: str
    data_dir: str
    log_dir: str
    max_concurrent_downloads: int
    min_disk_space_gb: float

    @classmethod
    def load(cls) -> "Config":
        """Loads and validates configuration from environment variables."""
        api_id_str = os.getenv("API_ID")
        api_hash = os.getenv("API_HASH")
        phone_number = os.getenv("PHONE_NUMBER", "").strip()
        chat_id_str = os.getenv("CHAT_ID")
        
        if not api_id_str or not api_hash or api_hash == "your_api_hash_here":
            print("[CONFIG ERROR] API_ID y API_HASH deben estar configurados en su archivo .env.")
            sys.exit(1)

        try:
            api_id = int(api_id_str.strip())
        except ValueError:
            print("[CONFIG ERROR] API_ID en .env debe ser un número entero válido.")
            sys.exit(1)

        chat_id = 0
        if chat_id_str:
            try:
                chat_id = int(chat_id_str.strip())
            except ValueError:
                print("[CONFIG ERROR] CHAT_ID en .env debe ser un número entero válido.")
                sys.exit(1)

        download_dir = os.path.abspath(os.getenv("DOWNLOAD_DIR", "./downloads"))
        data_dir = os.path.abspath(os.getenv("DATA_DIR", "./data"))
        log_dir = os.path.abspath(os.getenv("LOG_DIR", "./logs"))

        try:
            max_concurrent = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "1"))
        except ValueError:
            max_concurrent = 1

        try:
            min_disk_space = float(os.getenv("MIN_DISK_SPACE_GB", "5.0"))
        except ValueError:
            min_disk_space = 5.0

        os.makedirs(download_dir, exist_ok=True)
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)

        return cls(
            api_id=api_id,
            api_hash=api_hash,
            phone_number=phone_number,
            chat_id=chat_id,
            download_dir=download_dir,
            data_dir=data_dir,
            log_dir=log_dir,
            max_concurrent_downloads=max_concurrent,
            min_disk_space_gb=min_disk_space,
        )

# Lazy instance helper
_config_instance = None

def get_config() -> Config:
    global _config_instance
    if _config_instance is None:
        _config_instance = Config.load()
    return _config_instance
