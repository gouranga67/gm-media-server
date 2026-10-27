# Meta publishing in GM Studio

Implemented 2026-10-27. This connects the existing private studio to Meta; it does not make the library public. Publication is separate from approving an edit.

## What is available

- Owner-only Meta account connection through Facebook Login for Business, using a Facebook Page and its linked professional Instagram account.
- Encrypted account tokens, connection expiry information and disconnect/reconnect controls.
- Posting drafts pinned to a completed approved vertical final export, its exact file hash and a caption revision.
- Manual captions plus three optional AI-written caption choices. Generation requires explicit opt-in for that draft and makes one bounded request using the approved export's VTT transcript, existing copy and brief. No source media is re-analyzed, and generating copy does not select it or publish anything.
- Explicit Post now or approval of a scheduled post within 30 days. Time is entered in the browser's timezone, converted to UTC and displayed in local time. The server must be online; an overdue queued post runs when it returns. Nothing is scheduled merely by saving a draft.
- Separate Instagram/Facebook upload and publication records, processing status, cancellation before work starts, remote status checks, and a live link when Meta supplies one.
- Protection against double-click publication of one draft, ambiguous-response retries, changed exports/captions, disconnected accounts and retention removing a queued export.

Post from the final-delivery screen, not the preview screen. The first release supports the primary 1080 × 1920 final MP4 under 1 GB; delivery variants, photo/carousel posts, in-app music selection and automatic performance analytics are future work. The finished video's current audio and effects are uploaded together. Platform compatibility is checked against recorded music/effect permissions, including catalogue lookup for older effect manifests.

## 1. Create/configure the Meta app

Use Meta for Developers to create an app for your business and configure Facebook Login for Business. The owner connecting it needs permission to create content on the chosen Facebook Page, with its professional Instagram account linked to the Page.

The integration requests these permissions:

- `pages_show_list`
- `pages_read_engagement`
- `pages_manage_posts`
- `instagram_basic`
- `instagram_content_publish`

This intentionally uses the Facebook Login route for both destinations. Do not substitute the `instagram_business_*` scopes used by the separate Instagram Login route. If using a Facebook Login for Business configuration ID, select these permissions and account assets in that configuration.

Start with your own eligible accounts and app roles. External customer rollout requires a separate assessment of Meta App Review/Advanced Access, business verification, permissions, public privacy/deletion URLs and account-specific restrictions. Those public policy endpoints and a general customer onboarding service are not included in this private-studio release. Meta controls app eligibility and permissions; local tests cannot establish approval.

The Graph version is explicitly pinned to `v24.0`, rather than automatically changing versions. Set `META_GRAPH_VERSION` deliberately when upgrading and repeat the account/upload smoke tests.

## 2. Save app settings on the server

In the repository directory run:

```bash
python3 scripts/configure-meta-publishing.py
```

It asks for the app ID, the app secret through a hidden prompt, and an optional Facebook Login for Business configuration ID. It reads the studio origin already configured in `.env`, preserves an existing token-encryption key or generates one, and writes the configuration with mode 0600. It never prints app secrets, encryption keys or account tokens. It does not contact Meta, connect accounts or post anything.

Register the exact HTTPS redirect printed by the script in the Meta app. It ends in `/publishing/connect`. Your browser follows this redirect, so the device completing sign-in must be able to reach your private studio through Tailscale. If Meta refuses the chosen redirect/domain, resolve the app-domain requirements first; this release does not automatically open a tunnel or public studio endpoint.

The encryption key lives in `.env` alongside the app configuration and belongs in your encrypted disaster-recovery backup. Keep it when reconfiguring: replacing it makes existing account tokens unreadable until reconnection. No separate token copying through chat is needed.

Rebuild the services:

```bash
sudo ./scripts/install-service.sh
python3 scripts/verify-publishing.py
```

The read-only verifier passes with publishing unconfigured too, and reports `meta_configured: false` until setup is complete. It never creates captions, connects accounts or publishes a post.

## 3. Connect accounts in GM Studio

Open Jobs → Publishing → Connect or reconnect Meta. Sign in through Meta and grant access to the desired Page and linked Instagram account. The studio validates the returned accounts and stores encrypted tokens. A one-time, short-lived state value binds the sign-in callback to the studio owner. Completing sign-in does not publish anything.

Page tokens can be invalidated by Meta even before the displayed expiry. Reconnect when requested. Expiry uses the associated long-lived user-token lifetime conservatively; this release does not promise permanent connections or silently renew every kind of Meta credential.

## 4. Prepare and publish one post

1. Open an approved reel with a finished full-quality vertical export.
2. Choose Prepare a post. Merely opening it performs read-only requests.
3. Write a caption, or opt in and generate three caption options. Select one, edit it and save. The description is separate from burned-in subtitles.
4. Select Instagram, Facebook or both. Check the named destinations and export version.
5. Leave the time blank and press Post now, or choose a local time and approve the scheduled post.
6. Follow the per-account statuses. The worker operates after the page closes. A successful upload or processing result is not presented as a live publication.

The draft caption freezes when posting records are created. Existing records remain in history. After completed/failed/cancelled records, Prepare another posting draft creates a separate deliberate draft. Do not use a new draft as a substitute for resolving an uncertain previous publication.

## Recovery and limits

Instagram uses a media container, direct binary upload, processing checks and `media_publish`. Facebook uses a Reel upload session, direct binary upload, processing checks and finish/publish. Only the approved export is uploaded; the server does not expose originals or the library over a public URL. Account callbacks and tokens are not passed through the editor model.

The worker persists a container before streaming and records that publication started before the publish call. An interrupted or ambiguous write becomes Outcome uncertain. Check remote status rather than repeating publication. When no publish was attempted and an interrupted upload is confirmed ready, an explicit status/resume check can continue the already-approved post. If a remote container ID was lost, check the destination account manually; the owner can explicitly mark an unknown attempt unpublished to unlock a separate draft. That is a recorded owner decision, not an automated assertion. Once a publish may have happened, checks never send it again. Meta may confirm publication without returning a retrievable permalink; the UI says so rather than inventing a live link.

Processing checks are bounded (roughly 20 worker checks); long-running cases stop for review. Direct upload has a bounded time budget. This is conservative recovery, not a claim of network-level exactly-once delivery. An upload creation whose response was lost can leave an unpublished remote container; without its ID the studio cannot inspect it automatically.

The existing worker services publishing alongside editing, so queued processing checks may wait behind a render. Scheduled posting is suitable for this always-on private appliance, not a real-time delivery guarantee. A later dedicated publishing worker can improve timing isolation.

## First real acceptance test

Use one approved reel and one destination first. Check the account, caption, audio, crop, subtitles, cover frame and actual live link. Then test the second platform and combined posting. Test an app-role/owner account before attempting external customer access. Local automated verification uses synthetic records and simulated Meta responses: a real account connection and an explicitly approved live post remain required to validate your Meta app.

## Primary API references

- [Meta's Instagram API collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-5216d45b-1e24-4bff-bdc8-e1bf15358477)
- [Meta's Instagram Reels upload sample](https://github.com/fbsamples/reels_publishing_apis/tree/main/insta_reels_publishing_api_sample)
- [Meta's Facebook Page Reels collection](https://www.postman.com/meta/facebook/documentation/r56bjfd/facebook-api)
