from __future__ import annotations

import base64
from io import BytesIO

import fitz
from PIL import Image, ImageOps

from app.config import Settings, get_settings
from app.models import Document
from app.storage import ObjectStorage, get_object_storage


class DocumentPreprocessingError(Exception):
    code = "document_preprocessing_failed"


class DocumentImagePreprocessor:
    def __init__(
        self,
        *,
        storage: ObjectStorage | None = None,
        settings: Settings | None = None,
    ):
        self.storage = storage or get_object_storage()
        self.settings = settings or get_settings()

    def prepare(self, document: Document) -> list[str]:
        source = self.storage.open_stream(document.object_key)
        if source is None:
            raise DocumentPreprocessingError("A dokumentum nem olvasható az objektumtárból.")
        try:
            payload = source.read()
        except OSError as exc:
            raise DocumentPreprocessingError from exc
        finally:
            close = getattr(source, "close", None)
            if callable(close):
                close()

        try:
            if document.content_type == "application/pdf":
                return self._pdf_images(payload)
            return [self._optimize_image(payload)]
        except (fitz.FileDataError, OSError, ValueError) as exc:
            raise DocumentPreprocessingError from exc

    def _pdf_images(self, payload: bytes) -> list[str]:
        images: list[str] = []
        with fitz.open(stream=payload, filetype="pdf") as pdf:
            page_limit = min(len(pdf), self.settings.max_document_pages)
            for page_number in range(page_limit):
                page = pdf.load_page(page_number)
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                images.append(self._optimize_image(pixmap.tobytes("png")))
        if not images:
            raise DocumentPreprocessingError("A PDF nem tartalmaz feldolgozható oldalt.")
        return images

    def _optimize_image(self, payload: bytes) -> str:
        with Image.open(BytesIO(payload)) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            image.thumbnail(
                (self.settings.ai_max_image_side, self.settings.ai_max_image_side),
                Image.Resampling.LANCZOS,
            )
            output = BytesIO()
            image.save(output, format="JPEG", quality=85, optimize=True)
        return base64.b64encode(output.getvalue()).decode("ascii")
