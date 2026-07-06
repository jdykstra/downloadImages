import json
import os
import re
import subprocess
from dataclasses import dataclass

_EXIFTOOL_COMMAND = "exiftool"
_EXIFTOOL_ARGS = ["-api", "LargeFileSupport=1", "-j", "-G1", "-a", "-s"]
_BINARY_TAG_NAMES = {
    "PreviewImage",
    "PreviewImage1",
    "PreviewImage2",
    "ThumbnailImage",
}

from .nikon_mappings import NIKON_AF_AREA_MODE_BY_CODE as _NIKON_AF_AREA_MODE_BY_CODE


class VideoMetadataError(Exception):
    """Raised when video metadata extraction fails."""


@dataclass
class ExtractedVideoMetadata:
    resolve_metadata: dict[str, str]
    third_party_metadata: dict[str, str]
    summary: str


def extract_video_metadata_batch(file_paths: list[str], description: str | None = None) -> dict[str, ExtractedVideoMetadata]:
    if not file_paths:
        return {}

    completed = subprocess.run(
        [_EXIFTOOL_COMMAND, *_EXIFTOOL_ARGS, *file_paths],
        capture_output=True,
        check=False,
        text=True,
    )

    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip() or "unknown exiftool error"
        raise VideoMetadataError(f"exiftool failed: {stderr}")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise VideoMetadataError(f"could not parse exiftool output: {exc}") from exc

    extracted: dict[str, ExtractedVideoMetadata] = {}
    for raw_metadata in payload:
        source_path = raw_metadata.get("SourceFile")
        if not source_path:
            continue
        extracted[source_path] = _build_extracted_video_metadata(raw_metadata, description)

    return extracted


def _build_extracted_video_metadata(raw_metadata: dict[str, object], description: str | None) -> ExtractedVideoMetadata:
    normalized = {
        key: _format_metadata_value(value)
        for key, value in raw_metadata.items()
        if key != "SourceFile"
    }

    third_party_metadata = _build_third_party_metadata(normalized)
    summary = _build_summary(normalized)
    resolve_metadata = _build_resolve_metadata(normalized, description, summary)
    return ExtractedVideoMetadata(
        resolve_metadata=resolve_metadata,
        third_party_metadata=third_party_metadata,
        summary=summary,
    )


def _build_resolve_metadata(
    normalized: dict[str, str],
    description: str | None,
    summary: str,
) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if description:
        metadata["Description"] = description

    camera = _first_tag_value(normalized, ["Nikon:Model", "QuickTime:Model", "Composite:Model"])
    lens = _build_lens_display(normalized)
    keywords = _build_keywords(normalized)

    if camera:
        metadata["Camera Type"] = camera
    if lens:
        metadata["Lens"] = lens
    if keywords:
        metadata["Keywords"] = keywords

    if summary:
        metadata["Comments"] = summary

    recorded_at = _first_tag_value(normalized, ["Nikon:DateTimeOriginal", "Nikon:CreateDate", "QuickTime:CreateDate"])
    if recorded_at:
        metadata["Date Recorded"] = recorded_at

    return metadata


def _build_image_area_label(normalized: dict[str, str]) -> str:
    """Return "FX", "DX", "other", or "" for the sensor area used for this clip.

    Uses ``Nikon:CropHiSpeed`` from the maker notes.  Returns an empty string
    when the tag is absent so the caller adds nothing to the summary.

    Heuristic (verified against Z9 FX and DX 4K clips):
    - x-offset == 0 in the crop coordinates → full sensor width → "FX"
    - x-offset  > 0 and crop/source width ratio ≈ 1.5x → "DX"
    - x-offset  > 0, other ratio → "other"
    """
    tag_value = _first_tag_value(normalized, ["Nikon:CropHiSpeed"])
    if not tag_value:
        return ""

    upper = tag_value.upper()
    if "FX" in upper:
        return "FX"
    if "DX" in upper:
        return "DX"

    coord_match = re.search(r"at pixel (\d+),", tag_value)
    if not coord_match:
        return ""

    x_offset = int(coord_match.group(1))
    if x_offset == 0:
        return "FX"

    dim_match = re.search(r"(\d+)x\d+ cropped to (\d+)x", tag_value)
    if dim_match:
        source_w, crop_w = int(dim_match.group(1)), int(dim_match.group(2))
        if source_w and 1.4 <= source_w / crop_w <= 1.6:
            return "DX"

    return "other"


def _build_summary(normalized: dict[str, str]) -> str:
    parts: list[str] = []

    exposure = _first_tag_value(normalized, ["Nikon:ExposureTime", "Composite:ShutterSpeed"])
    aperture = _first_tag_value(normalized, ["Nikon:FNumber", "Composite:Aperture"])
    iso = _first_tag_value(normalized, ["Nikon:ISO"])
    lens = _build_lens_display(normalized)
    af_area_mode = _normalize_af_area_mode(_first_tag_value(normalized, ["Nikon:AFAreaMode"]))
    subject_detection = _first_tag_value(normalized, ["Nikon:SubjectDetection"])
    picture_control = _first_tag_value(normalized, ["Nikon:PictureControlName"])
    vibration_reduction = _first_tag_value(normalized, ["Nikon:VibrationReduction", "Nikon:ElectronicVR"])
    white_balance = _first_tag_value(normalized, ["Nikon:WhiteBalance"])
    camera = _first_tag_value(normalized, ["Nikon:Model", "QuickTime:Model", "Composite:Model"])

    exposure_summary = ""
    if exposure and aperture:
        exposure_summary = f"{exposure} at f/{aperture}"
    elif exposure:
        exposure_summary = exposure
    elif aperture:
        exposure_summary = f"f/{aperture}"

    if exposure_summary and iso:
        parts.append(f"{exposure_summary}, ISO {iso}")
    elif exposure_summary:
        parts.append(exposure_summary)
    elif iso:
        parts.append(f"ISO {iso}")

    if lens:
        parts.append(lens)
    if af_area_mode:
        parts.append(af_area_mode)
    if subject_detection:
        parts.append(subject_detection)
    if picture_control:
        parts.append(picture_control)
    if vibration_reduction:
        parts.append(f"VR {vibration_reduction}")
    if white_balance:
        parts.append(white_balance)
    image_area = _build_image_area_label(normalized)
    if image_area:
        parts.append(image_area)
    if camera:
        parts.append(_short_camera_name(camera))

    return ", ".join(parts)


def _build_still_frame_rate(normalized: dict[str, str]) -> str:
    """Return a display fps string for continuous-drive still images.

    Uses ``Nikon:HighFrameRate`` to determine the drive mode, then resolves
    the actual rate from the appropriate custom-settings tag.  Returns an
    empty string for single-frame shots or when the rate cannot be determined.

    Nikon:HighFrameRate values:
      - ``CH``  – Continuous High; rate stored in NikonCustom:CHModeShootingSpeed
      - ``C30`` / ``C60`` / ``C120`` – high-frame-rate modes; fps encoded in the name
      - tag absent – single-frame or CL (tag not written for CL mode)
    """
    high_frame_rate = _first_tag_value(normalized, ["Nikon:HighFrameRate"])
    if not high_frame_rate:
        return ""
    m = re.fullmatch(r"C(\d+)", high_frame_rate)
    if m:
        return f"{m.group(1)} fps"
    if high_frame_rate == "CH":
        return _first_tag_value(normalized, ["NikonCustom:CHModeShootingSpeed"])
    return ""


def _build_still_summary(normalized: dict[str, str]) -> str:
    """Build a shooting summary for still images.

    Omits shutter speed, aperture, ISO, focal length, and lens model because
    Lightroom Classic already surfaces those from standard EXIF tags.
    Adds AF area mode, subject detection (when available), and release mode.
    """
    parts: list[str] = []

    af_area_mode = _first_tag_value(normalized, ["Nikon:AFAreaMode"])
    subject_detection = _first_tag_value(normalized, ["Nikon:SubjectDetection"])
    shooting_mode = _first_tag_value(normalized, ["Nikon:ShootingMode"])
    picture_control = _first_tag_value(normalized, ["Nikon:PictureControlName"])
    vibration_reduction = _first_tag_value(normalized, ["Nikon:VibrationReduction", "Nikon:ElectronicVR"])
    white_balance = _first_tag_value(normalized, ["Nikon:WhiteBalance"])

    if af_area_mode:
        parts.append(af_area_mode)
    if subject_detection:
        parts.append(subject_detection)
    fps = _build_still_frame_rate(normalized)
    if fps:
        parts.append(fps)
    elif shooting_mode:
        parts.append(shooting_mode)
    if picture_control:
        parts.append(picture_control)
    if vibration_reduction:
        parts.append(f"VR {vibration_reduction}")
    if white_balance:
        parts.append(white_balance)

    return ", ".join(parts)


def _build_keywords(normalized: dict[str, str]) -> str:
    keyword_values = [
        _first_tag_value(normalized, ["Nikon:Make"]),
        _first_tag_value(normalized, ["Nikon:Model"]),
        _build_lens_display(normalized),
        _first_tag_value(normalized, ["Nikon:WhiteBalance"]),
        _first_tag_value(normalized, ["Nikon:PictureControlName"]),
    ]
    deduped = []
    seen = set()
    for value in keyword_values:
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return ", ".join(deduped)


def _build_third_party_metadata(normalized: dict[str, str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for grouped_name, value in normalized.items():
        group_name, _, tag_name = grouped_name.partition(":")
        if not tag_name:
            continue
        if group_name == "ExifTool" and tag_name == "Warning":
            metadata["ExifTool Warning"] = value
            continue
        if tag_name in _BINARY_TAG_NAMES:
            continue
        if group_name not in {"Nikon", "Composite", "QuickTime", "Track1", "Track2", "File"}:
            continue
        metadata[f"{group_name} {_humanize_tag_name(tag_name)}"] = value
    return metadata


def _normalize_af_area_mode(value: str) -> str:
    """Translate ``Unknown (NNN)`` AF area mode codes to human-readable names.

    exiftool returns ``Unknown (NNN)`` for Nikon video maker-note AF area mode
    codes not yet mapped in its tag tables.  This applies a local mapping
    derived from exiftool Nikon.pm so motion-file summaries show the same
    friendly strings as still-image summaries.
    """
    m = re.fullmatch(r"Unknown \((\d+)\)", value)
    if m:
        return _NIKON_AF_AREA_MODE_BY_CODE.get(m.group(1), value)
    return value


def _first_tag_value(normalized: dict[str, str], tag_paths: list[str]) -> str:
    for tag_path in tag_paths:
        value = normalized.get(tag_path)
        if value:
            return value
    return ""


def _format_metadata_value(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(_format_metadata_value(item) for item in value)
    return str(value).strip()


def _build_lens_display(normalized: dict[str, str]) -> str:
    lens_model = _first_tag_value(normalized, ["Nikon:LensModel", "Nikon:Lens", "Composite:LensSpec"])
    focal_length = _first_tag_value(normalized, ["Nikon:FocalLength", "Composite:FocalLength35efl"])

    if focal_length and lens_model:
        return f"{focal_length} ({lens_model})"
    if lens_model:
        return lens_model
    return focal_length


def _humanize_tag_name(tag_name: str) -> str:
    tag_name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", tag_name)
    tag_name = tag_name.replace("/", " ")
    return " ".join(tag_name.split())


def _short_camera_name(camera_name: str) -> str:
    camera_name = camera_name.strip()
    if camera_name.upper().startswith("NIKON "):
        return camera_name[6:].strip()
    return camera_name


def extract_still_metadata_summary(file_path: str) -> str:
    """Run exiftool on a still image and return a Nikon-style shooting summary string."""
    extracted = extract_video_metadata_batch([file_path])
    metadata = extracted.get(file_path)
    return metadata.summary if metadata else ""


def extract_still_metadata_summaries(file_paths: list[str]) -> dict[str, str]:
    """Run exiftool once across all still image paths, returning {path: summary_string}.

    Uses a still-specific field set (see _build_still_summary).
    Keys are normalised with os.path.normpath so callers can use os.path.join()
    paths regardless of slash style.
    """
    if not file_paths:
        return {}

    completed = subprocess.run(
        [_EXIFTOOL_COMMAND, *_EXIFTOOL_ARGS, *file_paths],
        capture_output=True, check=False, text=True,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip() or "unknown exiftool error"
        raise VideoMetadataError(f"exiftool failed: {stderr}")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise VideoMetadataError(f"could not parse exiftool output: {exc}") from exc

    result: dict[str, str] = {}
    for raw_metadata in payload:
        source_path = raw_metadata.get("SourceFile")
        if not source_path:
            continue
        normalized = {
            key: _format_metadata_value(value)
            for key, value in raw_metadata.items()
            if key != "SourceFile"
        }
        result[os.path.normpath(source_path)] = _build_still_summary(normalized)

    return result
