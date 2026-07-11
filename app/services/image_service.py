from __future__ import annotations

import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import Settings


class ImageValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessedImage:
    content: bytes
    content_type: str
    width: int
    height: int
    sha256: str


class ImageService:
    ALLOWED_SIGNATURES = (
        b"\xff\xd8\xff",  # JPEG
        b"\x89PNG\r\n\x1a\n",  # PNG
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @classmethod
    def _has_allowed_magic_bytes(cls, content: bytes) -> bool:
        return (
            any(content.startswith(signature) for signature in cls.ALLOWED_SIGNATURES)
            or (content.startswith(b"RIFF") and content[8:12] == b"WEBP")
        )

    def process_profile_image(self, content: bytes) -> ProcessedImage:
        if not content:
            raise ImageValidationError("Image file is empty")
        if len(content) > self.settings.profile_image_max_bytes:
            raise ImageValidationError("Image exceeds the maximum allowed size")
        if not self._has_allowed_magic_bytes(content):
            raise ImageValidationError("Only JPEG, PNG, and WebP images are allowed")

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as probe:
                    probe.verify()
                with Image.open(BytesIO(content)) as source:
                    if source.format not in {"JPEG", "PNG", "WEBP"}:
                        raise ImageValidationError("Only JPEG, PNG, and WebP images are allowed")
                    width, height = source.size
                    if width < 1 or height < 1 or width > self.settings.profile_image_max_dimension or height > self.settings.profile_image_max_dimension:
                        raise ImageValidationError("Image dimensions are outside allowed limits")
                    if width * height > self.settings.profile_image_max_pixels:
                        raise ImageValidationError("Image has too many pixels")
                    source.load()
                    image = ImageOps.exif_transpose(source)
                    width, height = image.size
                    if image.mode not in {"RGB", "RGBA"}:
                        image = image.convert("RGBA" if "transparency" in image.info else "RGB")
                    output = BytesIO()
                    image.save(output, format="WEBP", quality=85, method=6)
        except ImageValidationError:
            raise
        except (Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, SyntaxError, UnidentifiedImageError) as error:
            raise ImageValidationError("Invalid or unsafe image file") from error

        normalized = output.getvalue()
        if not normalized or len(normalized) > self.settings.profile_image_max_bytes:
            raise ImageValidationError("Processed image exceeds the maximum allowed size")
        return ProcessedImage(
            content=normalized, content_type="image/webp", width=width, height=height,
            sha256=hashlib.sha256(normalized).hexdigest(),
        )
