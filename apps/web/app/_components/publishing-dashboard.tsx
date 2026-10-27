"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { StudioNav } from "./studio-nav";
import { PostStatusList } from "./publishing-panel";
import {
  publishingStatus,
  socialAccounts,
  postingDrafts,
  connectMeta,
  disconnectMeta,
  type PublishingStatus,
  type SocialAccount,
  type PostingDraft,
} from "@/lib/publishing-api";
const control =
  "min-h-11 rounded-md border border-[#D7D9D3] bg-white px-4 py-2 text-sm font-bold text-[#173F5F] disabled:opacity-50";
export function PublishingDashboard() {
  const [status, setStatus] = useState<PublishingStatus>();
  const [accounts, setAccounts] = useState<readonly SocialAccount[]>([]);
  const [drafts, setDrafts] = useState<readonly PostingDraft[]>([]);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  async function refresh() {
    const [config, connections, history] = await Promise.all([
      publishingStatus(),
      socialAccounts(),
      postingDrafts(),
    ]);
    setStatus(config);
    setAccounts(connections);
    setDrafts(history);
  }
  useEffect(() => {
    let cancelled = false;
    void Promise.all([publishingStatus(), socialAccounts(), postingDrafts()])
      .then(([config, connections, history]) => {
        if (!cancelled) {
          setStatus(config);
          setAccounts(connections);
          setDrafts(history);
        }
      })
      .catch((e) => {
        if (!cancelled)
          setError(
            e instanceof Error ? e.message : "Publishing could not load.",
          );
      });
    return () => {
      cancelled = true;
    };
  }, []);
  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Publishing request failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-5 pb-20">
      <StudioNav current="/publishing" />
      <header>
        <p className="font-mono text-xs uppercase text-[#53646F]">
          Delivery & publishing
        </p>
        <h1 className="mt-2 text-2xl font-bold text-[#173F5F]">
          Publish from your studio
        </h1>
        <p className="mt-2 text-sm text-[#53646F]">
          Connect accounts, prepare captions and track approved posts. Only a
          Post now or scheduled-post approval starts publishing.
        </p>
      </header>
      {error ? (
        <p
          className="rounded border border-[#A23B2A] p-3 text-sm text-[#A23B2A]"
          role="alert"
        >
          {error}
        </p>
      ) : null}
      <section className="space-y-4 rounded-md border border-[#D7D9D3] bg-white p-5">
        <h2 className="text-lg font-bold text-[#173F5F]">Connected accounts</h2>
        {!status ? (
          <p role="status">Loading account settings…</p>
        ) : !status.configured ? (
          <div className="space-y-3 text-sm">
            <p>
              Meta setup is required on the server before connecting your
              accounts.
            </p>
            <p>Run this in the server terminal:</p>
            <code className="block break-words rounded bg-[#F1F5F7] p-3">
              python3 scripts/configure-meta-publishing.py
            </code>
            <p>
              Use a Meta developer app with Facebook Login for Business and
              publishing access to your Facebook Page and linked professional
              Instagram account. The setup guide is in{" "}
              <code>docs/meta-publishing-setup.md</code>.
            </p>
          </div>
        ) : (
          <>
            <p className="text-sm text-[#53646F]">
              Connect through Meta. Account tokens stay encrypted on the server.
            </p>
            <button
              className={control}
              disabled={busy}
              type="button"
              onClick={() =>
                void run(async () => {
                  const result = await connectMeta();
                  const url = new URL(result.url);
                  if (
                    url.protocol !== "https:" ||
                    url.hostname !== "www.facebook.com"
                  )
                    throw new Error("Unexpected Meta sign-in destination.");
                  window.location.assign(url.href);
                })
              }
            >
              Connect or reconnect Meta
            </button>
            <p className="break-words text-xs text-[#53646F]">
              Registered redirect: {status.redirect_uri}
            </p>
          </>
        )}
        <ul className="space-y-3">
          {accounts.map((account) => (
            <li
              key={account.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded border border-[#D7D9D3] p-3"
            >
              <div>
                <p className="text-sm font-bold text-[#173F5F]">
                  {account.platform === "instagram" ? "Instagram" : "Facebook"}{" "}
                  · {account.display_name}
                </p>
                <p className="mt-1 text-xs">
                  {!account.active
                    ? "Disconnected"
                    : account.token_expires_at &&
                        Date.parse(account.token_expires_at) <= Date.now()
                      ? "Reconnect required"
                      : "Connected"}
                  {account.token_expires_at
                    ? ` · reconnect before ${new Date(account.token_expires_at).toLocaleDateString()}`
                    : ""}
                </p>
              </div>
              {account.active ? (
                <button
                  className={control}
                  disabled={busy}
                  type="button"
                  onClick={() =>
                    void run(async () => {
                      await disconnectMeta(account.id);
                      await refresh();
                    })
                  }
                >
                  Disconnect {account.display_name}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-bold text-[#173F5F]">
            Posting drafts & history
          </h2>
          <button
            className={control}
            disabled={busy}
            type="button"
            onClick={() => void run(refresh)}
          >
            Refresh
          </button>
        </div>
        {!drafts.length ? (
          <div className="rounded-md border border-[#D7D9D3] bg-white p-5 text-sm">
            <p>
              No posting drafts yet. Open a finished export and choose Prepare a
              post.
            </p>
            <Link
              className="mt-3 inline-block min-h-11 py-2 font-bold text-[#173F5F] underline"
              href="/jobs"
            >
              Open your edits
            </Link>
          </div>
        ) : (
          drafts.map((draft) => (
            <article
              className="space-y-3 rounded-md border border-[#D7D9D3] bg-white p-5"
              key={draft.id}
            >
              <Link
                className="font-bold text-[#173F5F] underline"
                href={`/jobs/${encodeURIComponent(draft.job_id)}`}
              >
                {draft.project_name} · version {draft.version}
              </Link>
              <p className="whitespace-pre-wrap break-words text-sm">
                {draft.caption || "Caption not selected"}
              </p>
              {draft.posts.length ? (
                <PostStatusList posts={draft.posts} onChanged={refresh} />
              ) : (
                <p className="text-xs text-[#53646F]">
                  Draft only · nothing published
                </p>
              )}
            </article>
          ))
        )}
      </section>
    </main>
  );
}
