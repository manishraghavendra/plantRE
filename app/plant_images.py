"""Save or clear uploaded plant images under static/uploads/plants/."""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_BYTES = 4 * 1024 * 1024


def upload_dir() -> Path:
    return Path(__file__).resolve().parent / "static" / "uploads" / "plants"


def clear_uploaded_images(plant_id: int) -> None:
    d = upload_dir()
    if not d.is_dir():
        return
    for f in d.glob(f"{plant_id}.*"):
        f.unlink(missing_ok=True)


def save_plant_upload(plant_id: int, upload: UploadFile) -> str | None:
    if not upload.filename:
        return None
    suf = Path(upload.filename).suffix.lower()
    if suf not in ALLOWED_SUFFIXES:
        return None
    upload_dir().mkdir(parents=True, exist_ok=True)
    clear_uploaded_images(plant_id)
    dest = upload_dir() / f"{plant_id}{suf}"
    raw = upload.file.read()
    if len(raw) > MAX_BYTES:
        return None
    dest.write_bytes(raw)
    return f"/static/uploads/plants/{dest.name}"
