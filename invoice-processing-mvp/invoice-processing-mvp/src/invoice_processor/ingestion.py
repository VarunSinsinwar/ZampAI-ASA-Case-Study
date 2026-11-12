from pathlib import Path
import io
import fitz
from PIL import Image
import pytesseract

SUPPORTED = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}

def extract_document_text(file_path: str, min_pdf_text_chars: int = 40,
                          ocr_language: str = "eng", on_ocr=None):
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"Unsupported file type: {suffix}")

    if suffix == ".pdf":
        doc = fitz.open(path)
        page_texts = [page.get_text("text") or "" for page in doc]
        text = "\n\n".join(page_texts).strip()
        if len("".join(text.split())) >= min_pdf_text_chars:
            return text, "pdf_text"
        if on_ocr:
            on_ocr("PDF contains little or no embedded text; running OCR.")
        pages = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            pages.append(pytesseract.image_to_string(image, lang=ocr_language))
        ocr_text = "\n\n".join(pages).strip()
        return ocr_text, "ocr_pdf"
    image = Image.open(path)
    return pytesseract.image_to_string(image, lang=ocr_language).strip(), "ocr_image"
