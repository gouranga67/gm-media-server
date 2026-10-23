const apiBaseUrl = process.env.API_BASE_URL?.trim() || "http://api:8000";

export async function mediaApi(path: string, init?: RequestInit) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...init?.headers,
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`;
    throw new Error(`GM Studio API rejected the request: ${detail}`);
  }
  return body;
}
