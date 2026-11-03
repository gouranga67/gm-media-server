# Phase 31 — Publishing and release acceptance

Source checkpoint: 2026-11-03. Deployment and real release acceptance pending.

## Result

Studio → Pilot acceptance now saves owner observations to the database, tied to the deployed commit. The visit-only checkboxes are replaced by explicit Pass, Fail and, for role/platform checks, Not applicable records. Select an exact recent preview or already published record, describe the result, confirm it was checked, then Save. Typing, selecting, refreshing and opening history save nothing. Failed saves preserve the draft and stable request ID. Identical retries reuse the observation; changed payloads cannot overwrite it. Later results append another record; the latest result for that build/check supplies its status. New builds need fresh observations; old history remains visible.

Passing playback checks need an exact available ready preview. The downloaded-phone check also requires an available approved final export of that version. File availability does not prove the owner downloaded or watched it: the confirmation remains a human attestation. Publishing passes need a matching-platform record whose stored state is published. Scheduling checks additionally require explicit scheduling intent recorded at approval. They do not automatically prove remote publication at the intended time; observe that on the account and describe it. Historical scheduling intent remains unknown rather than being inferred from timestamps.

Machine evidence is separate: installed migration, configured private access, a running-service/disk snapshot under ten minutes old, a bounded Redis heartbeat read, a completed USB backup under 30 hours old, off-site file-size verification under 36 hours old, and passing restore/reboot evidence under 30 days old. A heartbeat does not prove every task is advancing. A running-service count does not replace container health checks. Failure/queue counts are distinct from current service health. Backup verification is not a substitute for a restore.

The restore verifier now atomically saves running/passed/failed results in the root-managed status directory, with timestamps and recovered-original count. No command output, keys, private paths or recovered media enter that record. A failed attempt replaces the previous result. The drill still restores into an isolated temporary directory and cleans it afterward. It checks a database dump listing with `pg_restore --list`; it does not import the database into live or temporary PostgreSQL. No automatic restore or reboot is added. Existing changed-boot interrupted-render evidence is reused.

## Publishing reliability

Migration 046 adds nullable scheduling intent to posting records and creates release observations that the API only appends. New approvals record whether a time was supplied. After a lost response, an identical scheduled request returns its existing records even after that time passes. Changing its time, destinations or revision cannot alter the earlier approval. New approvals retain the existing 30-day window. Upload, processing, publication and uncertain-outcome handling remain; no automatic remote-write retry is introduced.

The release page and APIs are owner-only at the private web boundary and backend. The core service receives the existing private-access-required setting for readiness reporting. No account token is returned, and reading readiness makes no Meta request. It never connects accounts, generates copy, creates edits, posts, marks a test passed or runs a drill automatically. Configuration and token expiry are local evidence; actual account testing establishes current remote eligibility and permissions.

## Acceptance and limits

`verify-phase31.py` is read-only. Its default pass means the infrastructure/schema contract is installed, even if human checks or Meta setup are pending. `--require-private` and `--require-publishing` fail until their respective recorded checks and current machine evidence pass. Neither runs missing work. Private acceptance can complete independently of publishing. Publishing also needs applicable platform checks, at least one actual platform pass and a scheduled-post pass. Public customer launch remains false: this is one shared private studio, not isolated customer workspaces.

The page lists 100 recent observations, 50 ready preview versions and 50 published results. Current-build results use a separate latest-per-check query, so older history cannot displace them. Full pagination and external performance analytics remain future work. Human records bind to a build, not every later library/configuration change. Current machine evidence is re-read; recheck affected human tasks after substantive changes. Notes are private studio data: do not enter credentials.

A read-only check during development found Meta unconfigured and no connected accounts. No real post, account connection, acceptance observation, production database mutation, backup restore or reboot was performed during this build. Follow [the Phase 31 testing plan](../testing-plan.md) and [Meta setup](../meta-publishing-setup.md) for those owner actions.

## Technical validation

719 backend tests passed, including real CPU renders, acceptance/configuration/worker-evidence tests, restore-status writer checks, read-only verifier tests and scheduled-approval retry tests. All 87 web interaction tests and eight source-suite gates passed, including TypeScript, production build, Compose validation and release audit. All 46 migrations and actual observation/posting/readiness SQL executed in isolated PGlite, covering legacy scheduling preservation, retries, latest-failure precedence and build separation. Desktop/phone browser checks use synthetic intercepted data to verify explicit save/reload behaviour, controls and absence of horizontal overflow. They are not real-footage or live Meta acceptance.
