"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  publishingStatus,
  socialAccounts,
  postingDrafts,
  postingDraft,
  createPostingDraft,
  savePostingDraft,
  suggestPostCaptions,
  publishDraft,
  checkPost,
  cancelPost,
  resolveUnpublishedPost,
  postState,
  livePostLink,
  type PostingDraft,
  type SocialAccount,
  type PublishingStatus,
  type PostRecord,
} from "@/lib/publishing-api";

const control =
  "min-h-11 rounded-md border border-[#D7D9D3] bg-white px-3 py-2 text-sm text-[#173F5F] disabled:opacity-50";
const primary =
  "min-h-11 rounded-md border border-[#173F5F] bg-[#173F5F] px-3 py-2 text-sm font-bold text-white disabled:opacity-50";
const errorMessage = (value: unknown) =>
  value instanceof Error
    ? value.message
    : "The posting request could not complete.";

export function PostStatusList({
  posts,
  onChanged,
}: {
  readonly posts: readonly PostRecord[];
  readonly onChanged: () => Promise<void>;
}) {
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState<string>();
  async function action(post: PostRecord, cancel: boolean) {
    if (busy) return;
    setBusy(post.id);
    setError(undefined);
    try {
      if (cancel) await cancelPost(post.id);
      else await checkPost(post.id);
      await onChanged();
    } catch (value) {
      setError(errorMessage(value));
    } finally {
      setBusy(undefined);
    }
  }
  async function resolve(post: PostRecord) {
    if (busy) return;
    setBusy(post.id);
    setError(undefined);
    try {
      await resolveUnpublishedPost(post.id);
      await onChanged();
    } catch (value) {
      setError(errorMessage(value));
    } finally {
      setBusy(undefined);
    }
  }
  return (
    <div className="space-y-3">
      {error ? (
        <p role="alert" className="text-sm text-[#A23B2A]">
          {error}
        </p>
      ) : null}
      {posts.map((post) => (
        <article key={post.id} className="rounded border border-[#D7D9D3] p-3">
          <p className="text-sm font-bold text-[#173F5F]">
            {post.platform === "instagram" ? "Instagram" : "Facebook"} ·{" "}
            {post.account_name}
          </p>
          <p className="mt-1 text-sm" role="status">
            {postState(post)}
          </p>
          <p className="mt-1 text-xs text-[#666862]">
            Posting time: {new Date(post.publish_at).toLocaleString()}
          </p>
          {post.error ? (
            <p className="mt-2 text-sm text-[#A23B2A]">{post.error}</p>
          ) : null}
          {livePostLink(post.permalink) ? (
            <a
              className={`${control} mt-2 inline-block underline`}
              href={livePostLink(post.permalink)}
              target="_blank"
              rel="noreferrer"
            >
              View live post
            </a>
          ) : post.status === "published" ? (
            <p className="mt-2 text-xs">
              Meta confirmed publication. The live link is not available yet;
              check the account.
            </p>
          ) : null}
          <div className="mt-2 flex flex-wrap gap-2">
            {post.status === "unknown" ? (
              <button
                className={control}
                disabled={!!busy}
                type="button"
                onClick={() => void resolve(post)}
              >
                I checked the account: this was not posted
              </button>
            ) : null}
            {post.status === "queued" ? (
              <button
                className={control}
                disabled={!!busy}
                onClick={() => void action(post, true)}
                type="button"
              >
                Cancel queued post
              </button>
            ) : null}
            {["unknown", "processing", "publishing"].includes(post.status) &&
            post.remote_container_id ? (
              <button
                className={control}
                disabled={!!busy}
                onClick={() => void action(post, false)}
                type="button"
              >
                Check remote status
              </button>
            ) : null}
          </div>
        </article>
      ))}
    </div>
  );
}

export function PublishingPanel({
  exportId,
  version,
}: {
  readonly exportId: string;
  readonly version: number;
}) {
  const [opened, setOpened] = useState(false);
  const [status, setStatus] = useState<PublishingStatus>();
  const [accounts, setAccounts] = useState<readonly SocialAccount[]>([]);
  const [draft, setDraft] = useState<PostingDraft>();
  const [caption, setCaption] = useState("");
  const [selected, setSelected] = useState<readonly string[]>([]);
  const [allowAi, setAllowAi] = useState(false);
  const [schedule, setSchedule] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [pollError, setPollError] = useState<string>();
  const createNonce = useRef<string | undefined>(undefined);
  const captionNonce = useRef<string | undefined>(undefined);
  const publishNonce = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!opened) return;
    let cancelled = false;
    void Promise.all([
      publishingStatus(),
      socialAccounts(),
      postingDrafts(exportId),
    ])
      .then(([settings, connections, drafts]) => {
        if (cancelled) return;
        setStatus(settings);
        setAccounts(connections);
        if (drafts[0]) {
          setDraft(drafts[0]);
          setCaption(drafts[0].caption);
        }
      })
      .catch((value) => {
        if (!cancelled) setError(errorMessage(value));
      });
    return () => {
      cancelled = true;
    };
  }, [opened, exportId]);
  const waiting =
    draft?.caption_request?.status === "pending" ||
    draft?.caption_request?.status === "generating" ||
    draft?.posts.some((p) =>
      ["queued", "uploading", "processing", "publishing"].includes(p.status),
    );
  useEffect(() => {
    if (!opened || !draft || !waiting) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const value = await postingDraft(draft!.id);
        if (!cancelled) {
          setDraft(value);
          setPollError(undefined);
          timer = setTimeout(() => void poll(), 4000);
        }
      } catch {
        if (!cancelled) {
          setPollError(
            "Posting status could not refresh. Your last known status is shown; do not submit another post.",
          );
          timer = setTimeout(() => void poll(), 8000);
        }
      }
    }
    timer = setTimeout(() => void poll(), 4000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [opened, draft?.id, waiting]);
  async function ensureDraft() {
    if (draft) return draft;
    createNonce.current ??= crypto.randomUUID();
    const value = await createPostingDraft(createNonce.current, exportId);
    setDraft(value);
    return value;
  }
  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    setNotice(undefined);
    try {
      await action();
    } catch (value) {
      setError(errorMessage(value));
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    let value = await ensureDraft();
    if (caption !== value.caption)
      value = await savePostingDraft(value, caption);
    setDraft(value);
    return value;
  }
  const locked = Boolean(draft?.posts.length);
  const connected = accounts.filter(
    (a) =>
      a.active &&
      (!a.token_expires_at || Date.parse(a.token_expires_at) > Date.now()),
  );
  async function reload() {
    if (draft) setDraft(await postingDraft(draft.id));
  }
  return (
    <section
      aria-label="Publish approved reel"
      className="rounded-md border border-[#BFD2DE] bg-white p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-bold text-[#173F5F]">Publish this reel</h2>
          <p className="mt-1 text-xs text-[#666862]">
            Approved export · version {version}
          </p>
        </div>
        <button
          className={control}
          onClick={() => setOpened(!opened)}
          type="button"
          aria-expanded={opened}
        >
          {opened ? "Close posting panel" : "Prepare a post"}
        </button>
      </div>
      {opened ? (
        <div className="mt-4 space-y-4">
          <p className="text-sm text-[#53646F]">
            Choose the exact caption and accounts before posting. Approving an
            edit alone never publishes it.
          </p>
          {error ? (
            <p role="alert" className="text-sm text-[#A23B2A]">
              {error}
            </p>
          ) : null}
          {pollError ? (
            <p role="alert" className="text-sm text-[#A23B2A]">
              {pollError}
            </p>
          ) : null}
          {notice ? (
            <p role="status" className="text-sm text-[#215B43]">
              {notice}
            </p>
          ) : null}
          {!status ? (
            <p role="status">Loading publishing settings…</p>
          ) : !status.configured ? (
            <p className="text-sm">
              Connect Meta before posting.{" "}
              <Link
                className="font-bold underline text-[#173F5F]"
                href="/publishing"
              >
                Open publishing setup
              </Link>
              . You can still prepare and save a caption here.
            </p>
          ) : null}
          {!locked ? (
            <>
              <video
                aria-label={`Approved final export version ${version}`}
                className="mx-auto max-h-96 w-full max-w-sm rounded bg-black"
                controls
                playsInline
                preload="none"
                src={`/api/media/publishing/exports/${encodeURIComponent(exportId)}/video`}
              />
              <label className="block text-sm font-bold text-[#173F5F]">
                Post caption
                <textarea
                  className={`${control} mt-2 min-h-32 w-full`}
                  maxLength={2200}
                  disabled={busy || !status}
                  value={caption}
                  onChange={(e) => setCaption(e.currentTarget.value)}
                  placeholder="Write your post caption, or generate options below."
                />
              </label>
              <p className="text-xs text-[#666862]">
                {caption.length}/2200 characters · this does not change the
                on-screen subtitles.
              </p>
              <div className="space-y-2">
                <label className="flex min-h-11 items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={allowAi}
                    disabled={busy || !status}
                    onChange={(e) => setAllowAi(e.currentTarget.checked)}
                  />
                  Allow AI-written caption options for this draft
                </label>
                <button
                  className={control}
                  type="button"
                  disabled={
                    busy ||
                    !allowAi ||
                    ["pending", "generating"].includes(
                      draft?.caption_request?.status ?? "",
                    )
                  }
                  onClick={() =>
                    void run(async () => {
                      const value = await save();
                      captionNonce.current ??= crypto.randomUUID();
                      const request = await suggestPostCaptions(
                        value.id,
                        captionNonce.current,
                      );
                      captionNonce.current = undefined;
                      setDraft({ ...value, caption_request: request });
                    })
                  }
                >
                  Generate 3 caption options
                </button>
                <p className="text-xs text-[#666862]">
                  One small AI request using stored speech and the brief.
                  Selecting, editing and posting use no further AI calls.
                </p>
              </div>
              {draft?.caption_request ? (
                <div className="space-y-2" aria-label="Caption options">
                  {["pending", "generating"].includes(
                    draft.caption_request.status,
                  ) ? (
                    <p role="status">
                      Preparing caption options… Your video stays unchanged.
                    </p>
                  ) : null}
                  {draft.caption_request.error ? (
                    <p role="alert">{draft.caption_request.error}</p>
                  ) : null}
                  {draft.caption_request.options.map((option, index) => (
                    <button
                      key={index}
                      className={`${control} w-full text-left`}
                      type="button"
                      disabled={busy || !status}
                      onClick={() => setCaption(option.text)}
                    >
                      <strong className="block">{option.label}</strong>
                      <span className="mt-1 block whitespace-pre-wrap">
                        {option.text}
                      </span>
                    </button>
                  ))}
                  {draft.caption_request.status === "ready" ? (
                    <p className="text-xs text-[#666862]">
                      {draft.caption_request.total_tokens.toLocaleString()}{" "}
                      measured caption tokens. Check all wording before posting.
                    </p>
                  ) : null}
                </div>
              ) : null}
              <fieldset disabled={busy || !status} className="space-y-2">
                <legend className="mb-2 text-sm font-bold text-[#173F5F]">
                  Post to
                </legend>
                {connected.map((account) => (
                  <label
                    key={account.id}
                    className="flex min-h-11 items-center gap-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={selected.includes(account.id)}
                      onChange={(e) => {
                        setSelected((ids) =>
                          e.target.checked
                            ? [...ids, account.id]
                            : ids.filter((id) => id !== account.id),
                        );
                        publishNonce.current = undefined;
                      }}
                    />
                    {account.platform === "instagram"
                      ? "Instagram"
                      : "Facebook"}{" "}
                    · {account.display_name}
                  </label>
                ))}
                {!connected.length ? (
                  <p className="text-sm">
                    No connected publishing accounts.{" "}
                    <Link className="underline" href="/publishing">
                      Connect an account
                    </Link>
                    .
                  </p>
                ) : null}
              </fieldset>
              <label className="block text-sm">
                Optional posting time · your device timezone
                <input
                  className={`${control} mt-2 w-full`}
                  type="datetime-local"
                  disabled={busy || !status}
                  value={schedule}
                  onChange={(e) => {
                    setSchedule(e.currentTarget.value);
                    publishNonce.current = undefined;
                  }}
                />
              </label>
              <p className="text-xs text-[#666862]">
                {schedule
                  ? `Will queue for ${new Date(schedule).toLocaleString()}. The server must be online; late posts run when it returns.`
                  : "Leave blank to publish now."}
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  className={control}
                  disabled={busy || !status}
                  type="button"
                  onClick={() =>
                    void run(async () => {
                      await save();
                      setNotice(
                        "Posting draft saved. Nothing has been published.",
                      );
                    })
                  }
                >
                  Save posting draft
                </button>
                <button
                  className={primary}
                  disabled={busy || !status?.configured || !selected.length}
                  type="button"
                  onClick={() =>
                    void run(async () => {
                      const value = await save();
                      publishNonce.current ??= crypto.randomUUID();
                      setDraft(
                        await publishDraft(
                          value,
                          publishNonce.current,
                          selected,
                          schedule
                            ? new Date(schedule).toISOString()
                            : undefined,
                        ),
                      );
                      setNotice(
                        "Posting approved. The server will handle upload and processing.",
                      );
                    })
                  }
                >
                  {busy
                    ? "Working…"
                    : schedule
                      ? "Approve scheduled post"
                      : "Post now"}
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="whitespace-pre-wrap text-sm">
                {draft?.caption || "No post caption"}
              </p>
              <p className="text-xs text-[#666862]">
                This caption and export are frozen for these posting records.
              </p>
              <PostStatusList posts={draft!.posts} onChanged={reload} />
              <button
                className={control}
                type="button"
                disabled={busy || !status}
                onClick={() =>
                  void run(async () => {
                    await reload();
                  })
                }
              >
                Refresh posting status
              </button>
              {draft!.posts.every((post) =>
                ["published", "failed", "cancelled"].includes(post.status),
              ) ? (
                <button
                  className={control}
                  disabled={busy || !status}
                  type="button"
                  onClick={() => {
                    createNonce.current = undefined;
                    captionNonce.current = undefined;
                    publishNonce.current = undefined;
                    setDraft(undefined);
                    setSelected([]);
                    setSchedule("");
                    setError(undefined);
                    setPollError(undefined);
                    setNotice(
                      "Preparing a separate posting draft. Existing posting records stay in history.",
                    );
                  }}
                >
                  Prepare another posting draft
                </button>
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </section>
  );
}
