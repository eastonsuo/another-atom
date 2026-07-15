import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

from another_atom.config import get_settings
from another_atom.domain.errors import AppError

MAX_IMAGE_BYTES = 10_000_000
MAX_IMAGE_PIXELS = 40_000_000
SUPPORTED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


@dataclass(frozen=True)
class ImageInfo:
    media_type: str
    width: int
    height: int


def inspect_image(data: bytes) -> ImageInfo:
    if not data:
        raise AppError("ATTACHMENT_DECODE_FAILED", "The image file is empty", 422)
    if len(data) > MAX_IMAGE_BYTES:
        raise AppError("ATTACHMENT_TOO_LARGE", "Images must be 10 MB or smaller", 413)
    try:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            info = _inspect_png(data)
        elif data.startswith(b"\xff\xd8"):
            info = _inspect_jpeg(data)
        elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            info = _inspect_webp(data)
        else:
            raise AppError(
                "ATTACHMENT_TYPE_UNSUPPORTED",
                "Only PNG, JPEG, and static WebP images are supported",
                422,
            )
    except AppError:
        raise
    except (IndexError, struct.error, ValueError) as exc:
        raise AppError(
            "ATTACHMENT_DECODE_FAILED", "The image could not be decoded safely", 422
        ) from exc
    if info.width <= 0 or info.height <= 0 or info.width * info.height > MAX_IMAGE_PIXELS:
        raise AppError(
            "ATTACHMENT_DECODE_FAILED",
            "The image dimensions exceed the supported pixel limit",
            422,
        )
    return info


def image_content_hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def store_image(user_id: str, attachment_id: str, data: bytes, media_type: str) -> str:
    extension = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[
        media_type
    ]
    root = get_settings().attachment_storage_root.resolve()
    relative = Path(user_id) / f"{attachment_id}{extension}"
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise AppError("ATTACHMENT_STORAGE_FAILED", "Invalid attachment storage path", 500)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.write_bytes(data)
    temporary.replace(target)
    return relative.as_posix()


def attachment_path(storage_key: str) -> Path:
    root = get_settings().attachment_storage_root.resolve()
    target = (root / storage_key).resolve()
    if not target.is_relative_to(root):
        raise AppError("ATTACHMENT_NOT_FOUND", "Attachment was not found", 404)
    return target


def _inspect_png(data: bytes) -> ImageInfo:
    if len(data) < 33 or data[12:16] != b"IHDR":
        raise ValueError("invalid PNG header")
    width, height = struct.unpack(">II", data[16:24])
    offset = 8
    saw_end = False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        next_offset = offset + 12 + length
        if next_offset > len(data):
            raise ValueError("truncated PNG chunk")
        if chunk_type == b"acTL":
            raise AppError(
                "ATTACHMENT_TYPE_UNSUPPORTED", "Animated PNG images are not supported", 422
            )
        if chunk_type == b"IEND":
            saw_end = True
            break
        offset = next_offset
    if not saw_end:
        raise ValueError("PNG has no IEND chunk")
    return ImageInfo("image/png", width, height)


def _inspect_jpeg(data: bytes) -> ImageInfo:
    offset = 2
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while offset + 4 <= len(data):
        while offset < len(data) and data[offset] != 0xFF:
            offset += 1
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker in {0xD8, 0xD9}:
            continue
        if marker == 0xDA:
            break
        if offset + 2 > len(data):
            break
        length = struct.unpack(">H", data[offset : offset + 2])[0]
        if length < 2 or offset + length > len(data):
            raise ValueError("invalid JPEG segment")
        if marker in sof_markers:
            if length < 7:
                raise ValueError("invalid JPEG SOF segment")
            height, width = struct.unpack(">HH", data[offset + 3 : offset + 7])
            return ImageInfo("image/jpeg", width, height)
        offset += length
    raise ValueError("JPEG dimensions were not found")


def _inspect_webp(data: bytes) -> ImageInfo:
    if len(data) < 30:
        raise ValueError("truncated WebP")
    offset = 12
    width = height = 0
    while offset + 8 <= len(data):
        chunk_type = data[offset : offset + 4]
        length = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
        payload = data[offset + 8 : offset + 8 + length]
        if len(payload) != length:
            raise ValueError("truncated WebP chunk")
        if chunk_type in {b"ANIM", b"ANMF"}:
            raise AppError(
                "ATTACHMENT_TYPE_UNSUPPORTED", "Animated WebP images are not supported", 422
            )
        if chunk_type == b"VP8X":
            if len(payload) < 10:
                raise ValueError("invalid VP8X header")
            if payload[0] & 0x02:
                raise AppError(
                    "ATTACHMENT_TYPE_UNSUPPORTED", "Animated WebP images are not supported", 422
                )
            width = 1 + int.from_bytes(payload[4:7], "little")
            height = 1 + int.from_bytes(payload[7:10], "little")
        elif chunk_type == b"VP8 " and not width:
            if len(payload) < 10 or payload[3:6] != b"\x9d\x01\x2a":
                raise ValueError("invalid VP8 frame")
            width = int.from_bytes(payload[6:8], "little") & 0x3FFF
            height = int.from_bytes(payload[8:10], "little") & 0x3FFF
        elif chunk_type == b"VP8L" and not width:
            if len(payload) < 5 or payload[0] != 0x2F:
                raise ValueError("invalid VP8L frame")
            bits = int.from_bytes(payload[1:5], "little")
            width = 1 + (bits & 0x3FFF)
            height = 1 + ((bits >> 14) & 0x3FFF)
        offset += 8 + length + (length % 2)
    if not width or not height:
        raise ValueError("WebP dimensions were not found")
    return ImageInfo("image/webp", width, height)
