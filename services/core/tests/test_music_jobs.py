import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import music_jobs
from app.music_analysis import MAX_ANALYSIS_SECONDS, analyze_music_beats


class MusicJobTests(unittest.TestCase):
    def fixture(self, root, row):
        database = MagicMock()
        database.__enter__.return_value = database
        database.execute.return_value.fetchone.return_value = row
        database.execute.return_value.rowcount = 1
        settings = SimpleNamespace(media_root=root, analysis_command_timeout_seconds=900)
        return database, settings, SimpleNamespace(active_music_track_id=None)

    def test_new_import_is_claimed_and_completes_without_restarting_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "music.mp3").write_bytes(b"fixture")
            row = dict(id="one", storage_key="music.mp3", duration_seconds=30, beat_analysis_attempts=1)
            database, settings, state = self.fixture(root, row)
            analyze = MagicMock(return_value={"bpm": 120, "beat_grid_seconds": [0, 0.5]})
            with patch.multiple(music_jobs, connection=MagicMock(return_value=database),
                get_settings=lambda: settings, analyze_music_beats=analyze):
                self.assertTrue(music_jobs.process_one_music_track(state))
            self.assertIsNone(state.active_music_track_id)
            analyze.assert_called_once_with(root / "music.mp3", 30.0, 120)
            queries = database.execute.call_args_list
            self.assertIn("FOR UPDATE SKIP LOCKED", queries[1].args[0])
            self.assertIn("beat_analysis_status = 'ready'", queries[2].args[0])
            self.assertIn("beat_analysis_lease_expires_at > now()", queries[2].args[0])

    def test_failed_decode_is_persisted_with_backoff_and_does_not_disable_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "music.mp3").write_bytes(b"fixture")
            row = dict(id="one", storage_key="music.mp3", duration_seconds=30, beat_analysis_attempts=2)
            database, settings, state = self.fixture(root, row)
            with patch.multiple(music_jobs, connection=MagicMock(return_value=database),
                get_settings=lambda: settings, analyze_music_beats=MagicMock(side_effect=RuntimeError("decode failed"))):
                self.assertTrue(music_jobs.process_one_music_track(state))
            sql, params = database.execute.call_args.args
            self.assertIn("beat_analysis_status = 'failed'", sql)
            self.assertEqual(params[:2], ("decode failed", 10))
            self.assertNotIn("active = false", sql)
            self.assertIsNone(state.active_music_track_id)

    def test_idle_and_exhausted_work_do_not_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            database, settings, state = self.fixture(Path(directory), None)
            analyze = MagicMock()
            with patch.multiple(music_jobs, connection=MagicMock(return_value=database),
                get_settings=lambda: settings, analyze_music_beats=analyze):
                self.assertFalse(music_jobs.process_one_music_track(state))
            analyze.assert_not_called()
            self.assertIn("beat_analysis_attempts >= 3", database.execute.call_args_list[0].args[0])

    def test_long_tracks_decode_only_bounded_window(self):
        def decode(command, **kwargs):
            self.assertEqual(float(command[command.index("-t") + 1]), MAX_ANALYSIS_SECONDS)
            with wave.open(command[-1], "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(22050)
                output.writeframes(b"\x00\x00" * 44100)
            return SimpleNamespace(returncode=0)

        with patch("app.music_analysis.run_command", side_effect=decode):
            result = analyze_music_beats(Path("fixture.mp3"), 3600, 5)
        self.assertTrue(result["beat_grid_seconds"])
        self.assertLessEqual(result["beat_grid_seconds"][-1], MAX_ANALYSIS_SECONDS)
