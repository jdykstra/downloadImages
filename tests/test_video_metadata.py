import unittest
from unittest.mock import patch

from downloadImages.video_metadata import extract_video_metadata_batch


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
            "downloadImages.video_metadata.subprocess.run",
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


if __name__ == "__main__":
    unittest.main()