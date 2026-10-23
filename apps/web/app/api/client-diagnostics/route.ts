import { appendFile, readFile } from "node:fs/promises";
import { NextResponse } from "next/server";

export const runtime = "nodejs";

const LOG_PATH = "/tmp/gm-client-diagnostics.jsonl";
const MAX_STRING_LENGTH = 2_000;
const MAX_EVENTS_RETURNED = 100;

function safeString(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  return value.slice(0, MAX_STRING_LENGTH);
}

function safeNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function safeNumberArray(value: unknown): number[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.slice(0, 20).map(safeNumber).filter((item): item is number => item !== undefined);
}

function safeStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.slice(0, 20).map(safeString).filter((item): item is string => item !== undefined);
}

function safeViewport(value: unknown): Record<string, number | null> | undefined {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return undefined;
  const source = value as Record<string, unknown>;
  const result: Record<string, number | null> = {};
  for (const key of [
    "innerWidth",
    "innerHeight",
    "clientWidth",
    "clientHeight",
    "bodyWidth",
    "bodyHeight",
    "shellWidth",
    "shellHeight",
    "shellTop",
    "shellBottom",
    "visualWidth",
    "visualHeight",
    "visualOffsetTop",
    "visualOffsetLeft",
    "scrollY",
    "scrollHeight",
    "bodyTop",
  ]) {
    const item = source[key];
    result[key] = item === null ? null : (safeNumber(item) ?? null);
  }
  return result;
}

export async function POST(request: Request) {
  const contentLength = Number(request.headers.get("content-length") ?? "0");
  if (contentLength > 32_768) {
    return NextResponse.json({ error: "diagnostic payload is too large" }, { status: 413 });
  }

  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  if (body === null) {
    return NextResponse.json({ error: "invalid diagnostic payload" }, { status: 400 });
  }

  const entry = {
    receivedAt: new Date().toISOString(),
    event: safeString(body.event) ?? "unknown",
    message: safeString(body.message),
    stack: safeString(body.stack),
    href: safeString(body.href),
    userAgent: safeString(body.userAgent),
    visibility: safeString(body.visibility),
    viewport: safeViewport(body.viewport),
    fileCount: safeNumber(body.fileCount),
    fileTypes: safeStringArray(body.fileTypes),
    fileSizes: safeNumberArray(body.fileSizes),
  };

  await appendFile(LOG_PATH, `${JSON.stringify(entry)}\n`, { encoding: "utf8", mode: 0o600 });
  return new Response(null, { status: 204 });
}

export async function GET() {
  try {
    const lines = (await readFile(LOG_PATH, "utf8")).trim().split("\n").filter(Boolean);
    const events = lines.slice(-MAX_EVENTS_RETURNED).map((line) => JSON.parse(line) as unknown);
    return NextResponse.json({ events });
  } catch (error) {
    const code = error instanceof Error && "code" in error ? error.code : undefined;
    if (code === "ENOENT") return NextResponse.json({ events: [] });
    throw error;
  }
}
