# Google Drive media import

Google Drive import is an optional owner-only library source. A phone uploads footage to Google Drive once; after explicit selection, the GM Studio server downloads the selected files directly into its existing Library Inbox. The browser never relays the media bytes and can close after the import is queued.

## One-time Google Cloud setup

1. Create or select a Google Cloud project.
2. Enable **Google Drive API** and **Google Picker API**.
3. Configure the OAuth consent screen. During private testing, add the owner's Google account as a test user.
4. Create an OAuth 2.0 **Web application** client.
5. Create a browser API key for Google Picker. Restrict it to the production studio origin and the Google Picker API.
6. Find the numeric Google Cloud project number; Picker calls this the app ID.
7. Run `python3 scripts/configure-google-drive.py` from the repository. Secrets are entered locally and written only to the ignored `.env` file.
8. Add the exact JavaScript origin and OAuth redirect URI printed by the helper to the Google Cloud credentials.
9. Redeploy GM Studio so migration 051 and the separate `cloud-importer` service start.

The application requests only `drive.file`, so it can access files explicitly shared through Google Picker. It does not request read access to the owner's whole Drive.

## Everyday use

1. Let the phone finish synchronising recordings to Google Drive.
2. Open **Library → Add media → Google Drive**.
3. On first use, choose **Connect Google Drive** and approve the narrow file permission.
4. Choose the destination folder, optional naming prefix and footage role.
5. Choose files in Google's picker, then choose **Import**.
6. The phone or browser may close. Follow queued, downloading, analysing and ready states in GM Studio.
7. Review ready recordings in the Library Inbox, then choose them when creating an edit.

Drive originals are never modified or deleted. GM Studio keeps a verified local original for reliable analysis and rendering. Selecting the same unchanged Drive file again reuses its existing import rather than downloading another copy.

## Operational behaviour

- OAuth refresh tokens are encrypted at rest with a dedicated key.
- OAuth state is single-use and expires after ten minutes.
- Only the Tailscale appliance owner can connect an account, request a Picker token or create imports.
- Downloads resume from a partial staging file, retry bounded transient failures and never run inside the GPU worker.
- Completed downloads enter the ordinary asset finalisation, duplicate-storage and analysis pipeline.
- Disconnect is refused while a transfer is active. Disconnecting later removes the provider connection and import transport records, not local library originals.
- Automatic watched folders are deliberately not part of version 1.

