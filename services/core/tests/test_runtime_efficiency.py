import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app import visual_index, worker
from app.runtime_metrics import measure_task, performance_snapshot


class EfficiencyTests(unittest.TestCase):
    def test_frame_budget_bounds_decodes_not_only_returned_vectors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source").write_bytes(b"source")
            segments = [
                {
                    "segment_kind": "scene",
                    "segment_index": n,
                    "start_seconds": n * 100,
                    "end_seconds": (n + 1) * 100,
                }
                for n in range(20)
            ]
            with patch.object(visual_index, "extract_visual_frame") as extract:
                frames = visual_index.build_visual_frames(
                    {
                        "id": "a",
                        "project_id": "p",
                        "storage_key": "source",
                        "mime_type": "video/mp4",
                    },
                    segments,
                    SimpleNamespace(
                        media_root=root, analysis_command_timeout_seconds=5
                    ),
                )
            self.assertEqual(extract.call_count, 120)
            self.assertEqual(frames[0]["segment_index"], 0)
            self.assertEqual(frames[-1]["segment_index"], 19)

    def test_worker_services_every_class_without_draining_uploads_or_ingest(self):
        calls = []
        tasks = [
            "catalog_one_asset",
            "process_one_edit",
            "process_one_final_export",
            "process_one_delivery_variant",
            "process_one_concept",
            "process_one_organization",
            "process_one_post",
            "process_one_caption",
            "analyze_one_asset",
        ]
        with tempfile.TemporaryDirectory() as directory:
            mocks = {
                name: Mock(
                    side_effect=lambda state, name=name: calls.append(name) or True
                )
                for name in tasks
            }
            mocks.update(
                {
                    name: Mock()
                    for name in [
                        "seed_pending_ingests",
                        "seed_pending_catalogs",
                        "recover_interrupted_concepts",
                        "recover_interrupted_organization",
                        "recover_interrupted_publishing",
                        "seed_pending_visual_indexes",
                        "index_one_asset_visually",
                    ]
                }
            )
            mocks["finalize_one_upload"] = Mock(return_value=True)
            mocks["get_settings"] = Mock(
                return_value=SimpleNamespace(media_root=Path(directory))
            )
            with patch.multiple(worker, **mocks):
                self.assertTrue(worker.run_work_cycle(worker.WorkerState()))
            self.assertEqual(calls, tasks)
            self.assertEqual(mocks["finalize_one_upload"].call_count, 4)
            mocks["index_one_asset_visually"].assert_not_called()

    def test_runtime_measurements_are_bounded_and_exclude_prompts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for _ in range(260):
                with measure_task("preview", root) as event:
                    event["did_work"] = True
            data = performance_snapshot(root)
            self.assertEqual(len(data["events"]), 240)
            self.assertEqual(data["stages"]["preview"]["samples"], 240)
            self.assertNotIn("prompt", json.dumps(data))

    def test_failed_task_is_measured_without_swallowing_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "original"):
                with measure_task("ingest", root):
                    raise ValueError("original")
            self.assertEqual(
                performance_snapshot(root)["events"][-1]["status"], "failed"
            )

    def test_history_survives_fresh_process_and_does_not_mix_media_roots(self):
        import os
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as other:
            root = Path(directory)
            with measure_task("preview", root) as event:
                event["did_work"] = True
            subprocess.run([sys.executable, "-c",
                "from pathlib import Path; import sys; from app.runtime_metrics import measure_task; "
                "\nwith measure_task('export', Path(sys.argv[1])) as event: event['did_work'] = True",
                directory], check=True, env=os.environ.copy())
            self.assertEqual([e["stage"] for e in performance_snapshot(root)["events"]], ["preview", "export"])
            with measure_task("ingest", Path(other)) as event:
                event["did_work"] = True
            self.assertEqual(len(performance_snapshot(Path(other))["events"]), 1)

    def test_corrupt_history_recovers_and_event_payloads_are_allowlisted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "analysis" / "runtime" / "worker.json"
            path.parent.mkdir(parents=True)
            path.write_text('{broken')
            with measure_task("preview", root) as event:
                event.update(did_work=True, prompt="private brief", command_output="private command")
            report = performance_snapshot(root)
            self.assertEqual(len(report["events"]), 1)
            self.assertNotIn("private", json.dumps(report))

    def test_concurrent_measurements_preserve_both_writers(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def record(index):
                with measure_task(f"task_{index}", root) as event:
                    event["did_work"] = True
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(record, range(12)))
            self.assertEqual(len(performance_snapshot(root)["events"]), 12)

    def test_diagnostics_write_failure_does_not_fail_a_successful_task(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("app.runtime_metrics.os.replace", side_effect=OSError("unavailable")):
                with measure_task("preview", Path(directory)) as event:
                    event["did_work"] = True
            self.assertEqual(list((Path(directory) / "analysis" / "runtime").glob(".worker-*")), [])

    def test_idle_worker_analyzes_one_music_track_before_visual_backfill(self):
        tasks = ["finalize_one_upload", "catalog_one_asset", "process_one_edit", "process_one_final_export",
                 "process_one_delivery_variant", "process_one_concept", "process_one_organization",
                 "process_one_post", "process_one_caption", "analyze_one_asset"]
        with tempfile.TemporaryDirectory() as directory:
            mocks = {name: Mock(return_value=False) for name in tasks}
            mocks.update({name: Mock() for name in ["seed_pending_ingests", "seed_pending_catalogs",
                "recover_interrupted_concepts", "recover_interrupted_organization", "recover_interrupted_publishing",
                "seed_pending_visual_indexes", "index_one_asset_visually"]})
            mocks["get_settings"] = Mock(return_value=SimpleNamespace(media_root=Path(directory)))
            mocks["process_one_music_track"] = Mock(return_value=True)
            with patch.multiple(worker, **mocks):
                self.assertTrue(worker.run_work_cycle(worker.WorkerState()))
            mocks["process_one_music_track"].assert_called_once()
            mocks["index_one_asset_visually"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
