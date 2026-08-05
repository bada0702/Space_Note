import os
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent


class Settings:
    """env 기반 설정 싱글톤. 테스트는 os.environ 설정 후 reload() 호출."""

    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        # .env의 값으로 채우되, 이미 설정된 os.environ(테스트/쉘)은 덮어쓰지 않음
        load_dotenv(BACKEND_DIR / ".env", override=False)
        self.SPACENOTE_TOKEN = os.getenv("SPACENOTE_TOKEN", "")
        self.ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
        self.DB_PATH = os.getenv("DB_PATH", str(BACKEND_DIR / "spacenote.db"))
        self.VAULT_DIR = Path(os.getenv("VAULT_DIR", str(ROOT_DIR / "vault")))
        
        # SQLite DB에서 vault_dir을 조회해 덮어씀 (순환 참조 방지를 위해 직접 sqlite3 사용)
        import sqlite3
        try:
            conn = sqlite3.connect(self.DB_PATH, timeout=30.0)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT vault_dir FROM settings WHERE id = 1").fetchone()
            if row and row["vault_dir"]:
                self.VAULT_DIR = Path(row["vault_dir"])
            conn.close()
        except Exception:
            pass

        self.ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:1420")
        self.EXTRACT_MODEL = os.getenv("EXTRACT_MODEL", "claude-haiku-4-5")
        self.VAULT_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
