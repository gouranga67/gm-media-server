export type SocialAccount = {
  id: string;
  platform: "instagram" | "facebook";
  external_id: string;
  display_name: string;
  active: boolean;
  token_expires_at: string | null;
};
export type PublishingStatus = {
  configured: boolean;
  graph_version: string;
  redirect_uri: string | null;
  setup_command: string;
};
export type PostRecord = {
  id: string;
  connection_id: string;
  platform: string;
  account_name: string;
  status: string;
  publish_at: string;
  permalink: string | null;
  error: string | null;
  remote_container_id: string | null;
};
export type CaptionRequest = {
  id: string;
  status: string;
  options: readonly { label: string; text: string }[];
  error: string | null;
  total_tokens: number;
};
export type PostingDraft = {
  id: string;
  final_export_id: string;
  job_id: string;
  version: number;
  project_name: string;
  revision: number;
  caption: string;
  posts: readonly PostRecord[];
  caption_request: CaptionRequest | null;
};
async function call<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api/media/publishing/${path}`, {
    method,
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Publishing request could not complete.",
    );
  return data as T;
}
export const publishingStatus = () => call<PublishingStatus>("status");
export const socialAccounts = () =>
  call<readonly SocialAccount[]>("connections");
export const connectMeta = () => call<{ url: string }>("meta/start", "POST");
export const completeMeta = (code: string, state: string) =>
  call<{ connected: number }>("meta/complete", "POST", { code, state });
export const disconnectMeta = (id: string) =>
  call(`connections/${encodeURIComponent(id)}`, "DELETE");
export const postingDrafts = (exportId?: string) =>
  call<readonly PostingDraft[]>(
    `drafts${exportId ? `?final_export_id=${encodeURIComponent(exportId)}` : ""}`,
  );
export const postingDraft = (id: string) =>
  call<PostingDraft>(`drafts/${encodeURIComponent(id)}`);
export const createPostingDraft = (id: string, exportId: string) =>
  call<PostingDraft>("drafts", "POST", { id, final_export_id: exportId });
export const savePostingDraft = (draft: PostingDraft, caption: string) =>
  call<PostingDraft>(`drafts/${encodeURIComponent(draft.id)}`, "PATCH", {
    revision: draft.revision,
    caption,
  });
export const suggestPostCaptions = (draftId: string, id: string) =>
  call<CaptionRequest>(
    `drafts/${encodeURIComponent(draftId)}/captions`,
    "POST",
    { id, allow_ai_copy: true },
  );
export const publishDraft = (
  draft: PostingDraft,
  requestId: string,
  ids: readonly string[],
  at?: string,
) =>
  call<PostingDraft>(`drafts/${encodeURIComponent(draft.id)}/publish`, "POST", {
    request_id: requestId,
    revision: draft.revision,
    connection_ids: ids,
    publish_at: at ?? null,
  });
export const checkPost = (id: string) =>
  call(`posts/${encodeURIComponent(id)}/check`, "POST");
export const cancelPost = (id: string) =>
  call(`posts/${encodeURIComponent(id)}/cancel`, "POST");
export const resolveUnpublishedPost = (id: string) =>
  call(`posts/${encodeURIComponent(id)}/resolve-unpublished`, "POST", {
    account_checked_no_post: true,
  });
export function postState(post: PostRecord) {
  if (post.status === "queued" && Date.parse(post.publish_at) > Date.now())
    return "Scheduled";
  return (
    (
      {
        queued: "Queued",
        uploading: "Uploading",
        processing: "Meta processing",
        publishing: "Checking publication",
        published: "Published",
        failed: "Needs attention",
        unknown: "Outcome uncertain — check account",
        cancelled: "Cancelled",
      } as Record<string, string>
    )[post.status] ?? post.status
  );
}
export function livePostLink(value: string | null) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "https:" &&
      [
        "www.instagram.com",
        "instagram.com",
        "www.facebook.com",
        "facebook.com",
      ].includes(url.hostname) &&
      !url.username &&
      !url.password
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}
