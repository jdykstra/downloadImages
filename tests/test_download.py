import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from downloadImages.download import copy_image_files
from downloadImages.sourceimages import CliError, SourceImage


class _DummyProgressTracker:

    def __init__(self, total):
        self.total = total

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def update(self, copied):
        return None


class DownloadTests(unittest.TestCase):

    def test_copy_image_files_rejects_existing_destination_with_different_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            destination_dir = Path(temp_dir) / "destination"
            source_dir.mkdir()
            destination_dir.mkdir()

            source_path = source_dir / "ABC0000.JPG"
            destination_path = destination_dir / "ABC0000.JPG"
            source_path.write_bytes(b"new source bytes")
            destination_path.write_bytes(b"old")

            image = SourceImage(
                src_filename="ABC0000",
                src_path=str(source_dir),
                extensions=["JPG"],
                file_locked=False,
                size=source_path.stat().st_size,
                dst_filename="ABC0000",
            )

            with patch("downloadImages.download._ProgressTracker", _DummyProgressTracker):
                with self.assertRaises(CliError) as context:
                    copy_image_files(
                        {"ABC0000": image},
                        [str(destination_dir)],
                        "description",
                        image.size,
                    )

            message = str(context.exception)
            self.assertIn("Destination file already exists", message)
            self.assertIn(str(source_path), message)
            self.assertIn(str(destination_path), message)
            self.assertEqual(destination_path.read_bytes(), b"old")

    def test_copy_image_files_skips_matching_existing_file_for_multi_extension_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            destination_dir = Path(temp_dir) / "destination"
            source_dir.mkdir()
            destination_dir.mkdir()

            source_jpg_path = source_dir / "ABC0001.JPG"
            source_nef_path = source_dir / "ABC0001.NEF"
            destination_jpg_path = destination_dir / "ABC0001.JPG"
            destination_nef_path = destination_dir / "ABC0001.NEF"

            source_jpg_path.write_bytes(b"jpeg-bytes")
            source_nef_path.write_bytes(b"raw-bits-here")
            destination_jpg_path.write_bytes(b"jpeg-bytes")

            image = SourceImage(
                src_filename="ABC0001",
                src_path=str(source_dir),
                extensions=["JPG", "NEF"],
                file_locked=False,
                size=source_jpg_path.stat().st_size + source_nef_path.stat().st_size,
                dst_filename="ABC0001",
            )

            with patch("downloadImages.download._ProgressTracker", _DummyProgressTracker):
                skipped_count = copy_image_files(
                    {"ABC0001": image},
                    [str(destination_dir)],
                    "description",
                    image.size,
                )

            self.assertEqual(skipped_count, 1)
            self.assertEqual(destination_jpg_path.read_bytes(), b"jpeg-bytes")
            self.assertEqual(destination_nef_path.read_bytes(), b"raw-bits-here")