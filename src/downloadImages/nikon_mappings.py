"""Nikon-specific mapping tables used when decoding maker-note values.

This module centralizes small lookup tables so they can be reused by
decoding helpers without embedding large literals in multiple modules.
"""

NIKON_AF_AREA_MODE_BY_CODE: dict[str, str] = {
    "192": "Pinpoint",
    "193": "Single",
    "195": "Wide (S)",
    "196": "Wide (L)",
    "197": "Auto",
    "199": "Auto (Animal)",
    "200": "Normal-area AF",
    "201": "Wide-area AF",
    "202": "Face-priority AF",
    "203": "Subject-tracking AF",
    "204": "Dynamic Area (S)",
    "205": "Dynamic Area (M)",
    "206": "Dynamic Area (L)",
    "207": "3D-tracking",
    "208": "Wide (C1/C2)",
}
