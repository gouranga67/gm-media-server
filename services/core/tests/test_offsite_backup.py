"""Execute the real shell pipeline against a fake transport, never OneDrive."""
import json
import os
import subprocess
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RCLONE = os.environ.get("GM_TEST_RCLONE") or shutil.which("rclone")


class OffsiteBackupTests(unittest.TestCase):
    def run_backup(self, failed_stage="", previous=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status = root / "status.json"
            if previous is not None:
                status.write_text(json.dumps(previous))
            # Use the production JSON writer; replace only root ownership
            # installation and the external transport with local fixture code.
            runner = (ROOT / "scripts/run-offsite-backup.sh").read_text()
            writer = runner[runner.index("write_status() {"):runner.index("offsite_failed() {")]
            failure_handler = runner[runner.index("offsite_failed() {"):runner.index('write_status "running"')]
            script = r'''
set -Eeuo pipefail
status_file=$1
status_directory=$(dirname "$status_file")
commands=$2
remote_root='fixture:backup'
history_stamp='fixture-run'
started_at='2026-01-01T00:00:00Z'
stage=preflight
transfer_state=pending
verification_state=pending
retention_state=pending
verified_at=null
docker() {
  printf '%s\n' "$*" >> "$commands"
  case "$7" in
    "$FAIL_STAGE") return 23 ;;
  esac
}
''' + writer + failure_handler + r'''
source "$3"
mirror_offsite_repository
'''
            result = subprocess.run(["bash", "-c", script, "fixture", str(status), str(root / "commands"),
                str(ROOT / "scripts/lib/offsite-backup.sh")], capture_output=True, text=True,
                env={**os.environ, "FAIL_STAGE": failed_stage}, timeout=10)
            return result, json.loads(status.read_text()), (root / "commands").read_text()

    def test_success_preserves_current_copy_and_reports_each_stage(self):
        result, status, commands = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(status["state"], "ready")
        self.assertEqual(set(status["stages"].values()), {"ready"})
        self.assertEqual(status["verification_method"], "one_way_file_size_comparison")
        self.assertIsNotNone(status["last_verified_at"])
        delete = next(line for line in commands.splitlines() if "offsite-sync delete" in line)
        self.assertIn("fixture:backup/restic-history --min-age 90d", delete)
        self.assertNotIn("--rmdirs", commands)
        self.assertNotIn("restic-current", delete)
        today = datetime.now(timezone.utc).date()
        for offset in (0, 1, 89, 90):
            bucket = (today - timedelta(days=offset)).strftime("%Y/%m/%d")
            self.assertIn(f"--exclude /{bucket}/**", delete)

    def test_retention_failure_is_distinct_from_copy_failure(self):
        result, status, _ = self.run_backup("delete")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(status["state"], "attention")
        self.assertEqual(status["stages"], {"transfer": "ready", "verification": "ready", "retention": "failed"})
        self.assertIsNotNone(status["last_verified_at"])

    def test_failed_verification_never_runs_retention_or_advances_last_match(self):
        result, status, commands = self.run_backup("check", {"state": "ready", "completed_at": "2025-12-31T00:00:00Z"})
        self.assertEqual(result.returncode, 23)
        self.assertEqual(status["state"], "failed")
        self.assertEqual(status["stages"]["verification"], "failed")
        self.assertEqual(status["last_verified_at"], "2025-12-31T00:00:00Z")
        self.assertIsNone(status["verified_at"])
        self.assertNotIn("offsite-sync delete", commands)

    def test_failed_transfer_stops_before_verification(self):
        result, status, commands = self.run_backup("sync")
        self.assertEqual(result.returncode, 23)
        self.assertEqual(status["stages"]["transfer"], "failed")
        self.assertEqual(status["stages"]["verification"], "pending")
        self.assertNotIn("offsite-sync check", commands)

    def test_missing_history_root_can_be_created_on_the_first_copy(self):
        result, status, commands = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = commands.splitlines()
        mkdir = next(n for n, line in enumerate(lines) if "offsite-sync mkdir" in line)
        delete = next(n for n, line in enumerate(lines) if "offsite-sync delete" in line)
        self.assertLess(mkdir, delete)
        self.assertEqual(status["stages"]["retention"], "ready")

    def test_history_creation_failure_keeps_successful_match_visible(self):
        result, status, commands = self.run_backup("mkdir")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(status["state"], "attention")
        self.assertEqual(status["stages"]["verification"], "ready")
        self.assertNotIn("offsite-sync delete", commands)

    @unittest.skipUnless(RCLONE, "rclone is required for disposable local retention integration")
    def test_real_retention_protects_recent_displacements_with_old_modification_times(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, remote = root / "source", root / "remote"
            source.mkdir()
            (source / "config").write_text("fixture repository")
            current = remote / "restic-current"
            current.mkdir(parents=True)
            (current / "config").write_text("fixture repository")
            now = datetime.now(timezone.utc)
            def stored(path, age):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture object")
                timestamp = (now - timedelta(days=age)).timestamp()
                os.utime(path, (timestamp, timestamp))
            # This old object is displaced by sync *today*. It must survive.
            stored(current / "displaced-object", 180)
            fixtures = []
            for bucket_age, file_age, keep in [(1, 180, True), (90, 180, True), (100, 180, False), (100, 10, True)]:
                day = (now - timedelta(days=bucket_age)).strftime("%Y/%m/%d")
                path = remote / "restic-history" / day / "000000Z" / f"object-{file_age}"
                stored(path, file_age)
                fixtures.append((path, keep))
            script = r'''
set -Eeuo pipefail
source "$1"
fixture_rclone=$2
fixture_source=$3
remote_root=$4
history_stamp=$(date -u +%Y/%m/%d/%H%M%SZ)
write_status() { :; }
docker() {
  local -a args=("${@:7}")
  case "${args[0]}" in sync|check) args[1]=$fixture_source ;; esac
  "$fixture_rclone" --config /dev/null "${args[@]}" --quiet
}
mirror_offsite_repository
'''
            result = subprocess.run(["bash", "-c", script, "fixture",
                str(ROOT / "scripts/lib/offsite-backup.sh"), str(RCLONE), str(source), str(remote)],
                text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((current / "config").read_text(), "fixture repository")
            self.assertFalse((current / "displaced-object").exists())
            today = now.strftime("%Y/%m/%d")
            self.assertEqual(len(list((remote / "restic-history" / today).rglob("displaced-object"))), 1)
            for path, keep in fixtures:
                self.assertEqual(path.exists(), keep, str(path.relative_to(root)))
