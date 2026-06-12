import unittest
from types import SimpleNamespace
from unittest.mock import patch

from downloadImages.cli import main


class CliMainTests(unittest.TestCase):

    def test_main_waits_for_ok_before_post_processing_when_warnings_were_shown(self):
        image_db = SimpleNamespace(file_type_count={"MOV": 1})

        with patch("downloadImages.cli._do_download", return_value=(image_db, True)), patch(
            "downloadImages.cli.os.path.exists", return_value=True
        ), patch("downloadImages.cli.input", side_effect=["later", "ok"]) as input_mock, patch(
            "downloadImages.cli.play_warning_pause_sound"
        ) as warning_sound_mock, patch(
            "downloadImages.cli.os.system"
        ) as os_system_mock, patch("downloadImages.cli.ingestMotionClips") as ingest_motion_mock:
            result = main(["downloadImages", "-a", "-r", "C:/dest"])

        self.assertEqual(result, 0)
        self.assertEqual(input_mock.call_count, 2)
        warning_sound_mock.assert_called_once()
        os_system_mock.assert_called_once()
        ingest_motion_mock.assert_called_once()

    def test_main_does_not_wait_for_ok_without_warnings(self):
        image_db = SimpleNamespace(file_type_count={"MOV": 1})

        with patch("downloadImages.cli._do_download", return_value=(image_db, False)), patch(
            "downloadImages.cli.os.path.exists", return_value=True
        ), patch("downloadImages.cli.input") as input_mock, patch(
            "downloadImages.cli.play_warning_pause_sound"
        ) as warning_sound_mock, patch(
            "downloadImages.cli.os.system"
        ) as os_system_mock, patch("downloadImages.cli.ingestMotionClips") as ingest_motion_mock:
            result = main(["downloadImages", "-a", "-r", "C:/dest"])

        self.assertEqual(result, 0)
        input_mock.assert_not_called()
        warning_sound_mock.assert_not_called()
        os_system_mock.assert_called_once()
        ingest_motion_mock.assert_called_once()