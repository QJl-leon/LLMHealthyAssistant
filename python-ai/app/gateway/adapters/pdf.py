import os

class PDFAdapter:

    def __init__(self):
        self.engine = os.getenv('PDF_ENGINE', 'pdfplumber')
        self.vlm_fallback = os.getenv('PDF_VLM_FALLBACK', 'true').lower() == 'true'

    def parse_tables(self, pdf_path: str) -> list[dict]:
        return []
