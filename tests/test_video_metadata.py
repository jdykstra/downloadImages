import os
import unittest
from unittest.mock import patch

from downloadImages.decode_metadata import extract_still_metadata_summaries, extract_video_metadata_batch


class _CompletedProcess:

    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


class VideoMetadataTests(unittest.TestCase):

    def test_extract_video_metadata_batch_builds_resolve_and_third_party_payloads(self):
        sample_json = """[
  {
    "SourceFile": "/tmp/CKQ8954.MOV",
    "Nikon:Model": "NIKON Z 9",
    "Nikon:LensModel": "VR 600mm f/4E",
    "Nikon:FocalLength": "850.0 mm",
    "Nikon:ExposureTime": "1/125",
    "Nikon:FNumber": 11.0,
    "Nikon:ISO": 14368,
    "Nikon:WhiteBalance": "NATURAL AUTO",
    "Nikon:FocusMode": "AF-C",
    "Nikon:VibrationReduction": "On",
    "Nikon:PictureControlName": "0310STANDARD",
    "Nikon:DateTimeOriginal": "2026:04:12 19:51:11",
    "Track1:CompressorName": "Apple ProRes 422 HQ",
    "Track1:ImageWidth": 3840,
    "Track1:ImageHeight": 2160,
    "Track1:VideoFrameRate": 59.94,
    "Nikon:PreviewImage": "(Binary data omitted)",
    "ExifTool:Warning": "sample warning"
  }
]"""

        with patch(
            "downloadImages.decode_metadata.subprocess.run",
            return_value=_CompletedProcess(sample_json),
        ):
            metadata = extract_video_metadata_batch(["/tmp/CKQ8954.MOV"], "test description")

        item = metadata["/tmp/CKQ8954.MOV"]
        self.assertEqual(item.resolve_metadata["Description"], "test description")
        self.assertEqual(item.resolve_metadata["Camera Type"], "NIKON Z 9")
        self.assertEqual(item.resolve_metadata["Lens"], "850.0 mm (VR 600mm f/4E)")
        self.assertEqual(
            item.resolve_metadata["Comments"],
            "1/125 at f/11.0, ISO 14368, 850.0 mm (VR 600mm f/4E), 0310STANDARD, VR On, NATURAL AUTO, Z 9",
        )
        self.assertEqual(item.resolve_metadata["Date Recorded"], "2026:04:12 19:51:11")
        self.assertIn("Nikon Model", item.third_party_metadata)
        self.assertIn("ExifTool Warning", item.third_party_metadata)
        self.assertNotIn("Nikon Preview Image", item.third_party_metadata)

    def test_af_area_mode_unknown_code_normalized_in_summary(self):
        """Unknown (203) should appear as Subject-tracking AF, not Unknown (203)."""
        sample_json = """[{
            "SourceFile": "/tmp/test.MOV",
            "Nikon:ExposureTime": "1/60",
            "Nikon:FNumber": 9.0,
            "Nikon:ISO": 79,
            "Nikon:LensModel": "NIKKOR Z 800mm f/6.3 VR S Z TC-1.4x",
            "Nikon:FocalLength": "1120.0 mm",
            "Nikon:AFAreaMode": "Unknown (203)"
        }]"""
        with patch(
            "downloadImages.decode_metadata.subprocess.run",
            return_value=_CompletedProcess(sample_json),
        ):
            metadata = extract_video_metadata_batch(["/tmp/test.MOV"])
        summary = metadata["/tmp/test.MOV"].summary
        self.assertIn("Subject-tracking AF", summary)
        self.assertNotIn("Unknown", summary)

    def test_af_area_mode_human_readable_passes_through_unchanged(self):
        """A value already decoded by exiftool should pass through without alteration."""
        sample_json = """[{
            "SourceFile": "/tmp/test.MOV",
            "Nikon:ExposureTime": "1/500",
            "Nikon:FNumber": 9.0,
            "Nikon:ISO": 640,
            "Nikon:LensModel": "NIKKOR Z 800mm f/6.3 VR S",
            "Nikon:FocalLength": "800.0 mm",
            "Nikon:AFAreaMode": "3D-tracking"
        }]"""
        with patch(
            "downloadImages.decode_metadata.subprocess.run",
            return_value=_CompletedProcess(sample_json),
        ):
            metadata = extract_video_metadata_batch(["/tmp/test.MOV"])
        summary = metadata["/tmp/test.MOV"].summary
        self.assertIn("3D-tracking", summary)

    def test_still_summary_ch_mode_shows_fps(self):
        """CH drive mode with CHModeShootingSpeed should display fps, not 'Continuous'."""
        sample_json = """[{
            "SourceFile": "/tmp/test.NEF",
            "Nikon:AFAreaMode": "3D-tracking",
            "Nikon:ShootingMode": "Continuous, Auto ISO",
            "Nikon:HighFrameRate": "CH",
            "NikonCustom:CHModeShootingSpeed": "20 fps"
        }]"""
        with patch(
            "downloadImages.decode_metadata.subprocess.run",
            return_value=_CompletedProcess(sample_json),
        ):
            summaries = extract_still_metadata_summaries(["/tmp/test.NEF"])
        summary = summaries[os.path.normpath("/tmp/test.NEF")]
        self.assertIn("20 fps", summary)
        self.assertNotIn("Continuous", summary)

    def test_still_summary_high_frame_rate_mode_shows_fps(self):
        """C30/C60/C120 modes should show the encoded fps number."""
        sample_json = """[{
            "SourceFile": "/tmp/test.NEF",
            "Nikon:HighFrameRate": "C120"
        }]"""
        with patch(
            "downloadImages.decode_metadata.subprocess.run",
            return_value=_CompletedProcess(sample_json),
        ):
            summaries = extract_still_metadata_summaries(["/tmp/test.NEF"])
        summary = summaries[os.path.normpath("/tmp/test.NEF")]
        self.assertIn("120 fps", summary)

    def test_still_summary_single_frame_shows_shooting_mode(self):
        """Without HighFrameRate, shooting mode falls back to ShootingMode tag."""
        sample_json = """[{
            "SourceFile": "/tmp/test.NEF",
            "Nikon:ShootingMode": "Single-Frame"
        }]"""
        with patch(
            "downloadImages.decode_metadata.subprocess.run",
            return_value=_CompletedProcess(sample_json),
        ):
            summaries = extract_still_metadata_summaries(["/tmp/test.NEF"])
        summary = summaries[os.path.normpath("/tmp/test.NEF")]
        self.assertIn("Single-Frame", summary)


if __name__ == "__main__":
    unittest.main()