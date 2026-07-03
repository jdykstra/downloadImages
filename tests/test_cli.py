import unittest
from types import SimpleNamespace
from unittest.mock import patch

from downloadImages.cli import _do_download, main


class CliMainTests(unittest.TestCase):

    def test_main_skips_lightroom_ingest_when_no_stills_or_motions_exist(self):
        image_db = SimpleNamespace(file_type_count={})

        with patch("downloadImages.cli._do_download", return_value=(image_db, False)), patch(
            "downloadImages.cli.os.path.exists", return_value=True
        ), patch("downloadImages.cli.os.system") as os_system_mock, patch(
            "downloadImages.cli.ingestMotionClips"
        ) as ingest_motion_mock:
            result = main(["downloadImages", "-a", "C:/dest"])

        self.assertEqual(result, 0)
        os_system_mock.assert_not_called()
        ingest_motion_mock.assert_not_called()

    def test_main_waits_for_ok_before_post_processing_when_warnings_were_shown(self):
        image_db = SimpleNamespace(file_type_count={"MOV": 1})

        with patch("downloadImages.cli._do_download", return_value=(image_db, True)), patch(
            "downloadImages.cli.os.path.exists", return_value=True
        ), patch("downloadImages.cli.input", side_effect=["later", "ok"]) as input_mock, patch(
            "downloadImages.cli.play_warning_pause_sound"
        ) as warning_sound_mock, patch(
            "downloadImages.cli.os.system"
        ) as os_system_mock, patch("downloadImages.cli.ingestMotionClips") as ingest_motion_mock:
            result = main(["downloadImages", "-a", "C:/dest"])

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
            result = main(["downloadImages", "-a", "C:/dest"])

        self.assertEqual(result, 0)
        input_mock.assert_not_called()
        warning_sound_mock.assert_not_called()
        os_system_mock.assert_called_once()
        ingest_motion_mock.assert_called_once()

    def test_main_rejects_removed_resolve_option(self):
        with self.assertRaises(SystemExit) as e:
            main(["downloadImages", "-r", "C:/dest"])
        self.assertEqual(e.exception.code, 2)

    def test_do_download_accepts_relative_destination_paths(self):
        image_db = SimpleNamespace(
            file_type_count={},
            locked_file_count=0,
            db=[],
            total_to_transfer=0,
            rollover_occurred_prefixes=[],
            near_rollover_prefixes=[],
        )

        args = SimpleNamespace(
            download_locked_only=False,
            description=None,
            delete=False,
        )

        class DummyUsage:
            free = 10 * 1024 * 1024 * 1024

        def fake_disk_usage(path):
            if path == "":
                raise AssertionError("empty path should not be used")
            return DummyUsage()

        with patch("downloadImages.cli.find_source_volume", return_value=[("TestCard", "/Volumes/TestCard")]), patch(
            "downloadImages.cli.find_source_images", return_value=image_db
        ), patch("downloadImages.cli.copy_image_files", return_value=0), patch(
            "downloadImages.cli.shutil.disk_usage", side_effect=fake_disk_usage
        ), patch("downloadImages.cli.os.path.isdir", return_value=False), patch(
            "downloadImages.cli.os.makedirs"
        ), patch("downloadImages.cli.play_notification_sound"), patch(
            "downloadImages.cli.play_warning_pause_sound"
        ), patch("downloadImages.cli.subprocess.Popen"), patch("downloadImages.cli.subprocess.run"), patch(
            "downloadImages.cli.input", return_value="n"
        ):
            result = _do_download(args, ["relative-dest"])

        self.assertIsNotNone(result)
        self.assertEqual(result[0], image_db)
        self.assertFalse(result[1])
