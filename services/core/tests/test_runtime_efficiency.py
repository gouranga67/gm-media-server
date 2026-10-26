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


if __name__ == "__main__":
    unittest.main()
