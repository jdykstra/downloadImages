import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from downloadImages.sourceimages import CliError, find_source_images


class SourceImagesTests(unittest.TestCase):

    def test_find_source_images_groups_extensions_for_same_source_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dcim_dir = Path(temp_dir) / "DCIM" / "100TEST"
            dcim_dir.mkdir(parents=True)
            (dcim_dir / "ABC1234.NEF").write_bytes(b"raw")
            (dcim_dir / "ABC1234.JPG").write_bytes(b"jpeg")

            image_db = find_source_images(str(Path(temp_dir) / "DCIM"), download_locked_only=False)

        image = image_db.db["ABC1234"]
        self.assertEqual(image.src_filename, "ABC1234")
        self.assertEqual(set(image.extensions), {"NEF", "JPG"})
        self.assertEqual(len(image_db.db), 1)

    def test_find_source_images_rejects_colliding_destination_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first_dir = Path(temp_dir) / "DCIM" / "100TEST"
            second_dir = Path(temp_dir) / "DCIM" / "101TEST"
            first_dir.mkdir(parents=True)
            second_dir.mkdir(parents=True)
            (first_dir / "ABC0000.NEF").write_bytes(b"older raw")
            (second_dir / "ABC0000.JPG").write_bytes(b"newer jpeg")

            with self.assertRaises(CliError) as context:
                find_source_images(str(Path(temp_dir) / "DCIM"), download_locked_only=False)

        self.assertIn("destination name ABC0000", str(context.exception))

    def test_find_source_images_rejects_mixed_case_duplicate_extensions(self):
        walk_rows = [
            ("/mock/DCIM/100TEST", [], ["ABC1234.JPG", "ABC1234.jpg"]),
        ]

        class _StatInfo:

            def __init__(self, size):
                self.st_size = size
                self.st_flags = 0

        with patch("downloadImages.sourceimages.os.walk", return_value=walk_rows), patch(
            "downloadImages.sourceimages.os.stat",
            side_effect=[_StatInfo(5), _StatInfo(5)],
        ), patch("downloadImages.sourceimages.os.access", return_value=True):
            with self.assertRaises(CliError) as context:
                find_source_images("/mock/DCIM", download_locked_only=False)

        self.assertIn("differ only by case", str(context.exception))