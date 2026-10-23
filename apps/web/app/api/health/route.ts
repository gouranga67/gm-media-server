import { NextResponse } from "next/server";

export function GET() {
  return NextResponse.json({ service: "web-agent", status: "ok" });
}
