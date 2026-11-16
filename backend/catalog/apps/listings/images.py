"""Image normalisation: validate the upload and render web variants without metadata."""

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SOURCE_PIXELS = 50_000_000
MIN_SOURCE_SIDE = 400
VARIANT_SIZES = {"large": 1600, "thumb": 400}


class InvalidImageError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Variant:
    name: str
    data: bytes
    width: int
    height: int


def render_variants(raw: bytes) -> list[Variant]:
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
        image: Image.Image = Image.open(io.BytesIO(raw))
        if image.width * image.height > MAX_SOURCE_PIXELS:
            raise InvalidImageError("Image is too large.")
        image.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as exc:
        raise InvalidImageError("File is not a valid image.") from exc

    if min(image.size) < MIN_SOURCE_SIDE:
        raise InvalidImageError(f"Image must be at least {MIN_SOURCE_SIDE}px on each side.")

    # Re-encoding drops EXIF (including GPS) after applying its orientation.
    image = ImageOps.exif_transpose(image).convert("RGB")
    variants = []
    for name, max_side in VARIANT_SIZES.items():
        copy = image.copy()
        copy.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        copy.save(buffer, format="WEBP", quality=82, method=4)
        variants.append(Variant(name, buffer.getvalue(), copy.width, copy.height))
    return variants
