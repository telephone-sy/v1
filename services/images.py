from pathlib import Path
from io import BytesIO
from uuid import uuid4
import warnings

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError


MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGES = 5
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_UPLOADS = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
}


async def save_images(files: list[UploadFile], upload_dir: Path) -> list[str]:
    if len(files) > MAX_IMAGES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "الحد الأقصى خمس صور")
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    try:
        for file in files:
            suffix = Path(file.filename or "").suffix.lower()
            if file.content_type not in ALLOWED_UPLOADS or suffix not in ALLOWED_UPLOADS[file.content_type]:
                raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "ارفع صورة JPEG أو PNG أو WebP فقط")
            raw = await file.read(MAX_IMAGE_BYTES + 1)
            if len(raw) > MAX_IMAGE_BYTES:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "حجم الصورة يتجاوز 5 ميغابايت")
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    image = Image.open(BytesIO(raw))
                    if image.format not in ALLOWED_FORMATS:
                        raise ValueError("unsupported image format")
                    image.verify()
                    image = Image.open(BytesIO(raw)).convert("RGB")
                    image.thumbnail((1600, 1600))
                    path = f"{uuid4().hex}.jpg"
                    image.save(upload_dir / path, format="JPEG", quality=82, optimize=True)
                    saved.append(path)
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "صيغة الصورة غير مدعومة أو الملف تالف") from None
        return saved
    except Exception:
        delete_images(saved, upload_dir)
        raise


def delete_images(paths: list[str], upload_dir: Path) -> None:
    for name in paths:
        path = (upload_dir / name).resolve()
        if path.parent == upload_dir.resolve():
            path.unlink(missing_ok=True)