from dataclasses import dataclass
from pathlib import Path
import os

@dataclass
class Settings:
    root_dir: Path
    data_dir: Path
    database_path: Path
    tolerance_percent: float = 2.0
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    use_llm: bool = False
    min_pdf_text_chars: int = 40
    ocr_language: str = "eng"

    @classmethod
    def from_env(cls, root: Path):
        data_dir = Path(os.getenv("DATA_DIR", root / "data")).expanduser()
        db = Path(os.getenv("DATABASE_PATH", root / "outputs" / "invoice_audit.db")).expanduser()
        if not db.is_absolute():
            db = root / db
        if not data_dir.is_absolute():
            data_dir = root / data_dir
        return cls(
            root_dir=root, data_dir=data_dir, database_path=db,
            tolerance_percent=float(os.getenv("PO_TOLERANCE_PERCENT", "2.0")),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            use_llm=os.getenv("USE_LLM", "false").lower() in {"1", "true", "yes"},
            min_pdf_text_chars=int(os.getenv("MIN_PDF_TEXT_CHARS", "40")),
            ocr_language=os.getenv("OCR_LANGUAGE", "eng"),
        )
