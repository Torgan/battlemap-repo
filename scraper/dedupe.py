"""Perceptual-hash dedupe for reposts."""
from __future__ import annotations

import imagehash
from PIL import Image


def phash_hex(img: Image.Image) -> str:
    return str(imagehash.phash(img))


def is_near_duplicate(candidate_hex: str, existing_hexes: list[str], max_distance: int) -> bool:
    """True if candidate is within max_distance (Hamming) of any existing hash."""
    cand = imagehash.hex_to_hash(candidate_hex)
    for hx in existing_hexes:
        if not hx:
            continue
        try:
            if cand - imagehash.hex_to_hash(hx) <= max_distance:
                return True
        except ValueError:
            continue
    return False
