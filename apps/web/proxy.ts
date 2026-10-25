import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

export async function proxy(request: NextRequest) {
  const routerHost = process.env.VERCEL_URL;
  const forwardedHost = request.headers.get("x-forwarded-host");
  if (process.env.__VERCEL_DEV_RUNNING === "1" && routerHost && forwardedHost !== routerHost) {
    const target = request.nextUrl.clone();
    target.protocol = "http:";
    target.host = routerHost;
    return NextResponse.redirect(target);
  }

  if (request.nextUrl.pathname === "/api/health") {
    return NextResponse.next();
  }

  if (process.env.TAILSCALE_AUTH_REQUIRED === "true") {
    const expectedLogin = process.env.TAILSCALE_ALLOWED_LOGIN?.trim().toLowerCase();
    const requestLogin = request.headers.get("tailscale-user-login")?.trim().toLowerCase();

    if (!expectedLogin) {
      return new NextResponse("GM Studio private access is not configured.", { status: 503 });
    }
    if (!requestLogin) {
      return new NextResponse(
        "GM Studio is available only through its private Tailscale Serve address.",
        {
          status: 401,
          headers: { "cache-control": "no-store" },
        },
      );
    }

    let role = "owner";
    if (requestLogin !== expectedLogin) {
      try {
        const apiBase = process.env.API_BASE_URL ?? "http://api:8000";
        const response = await fetch(`${apiBase}/api/v1/access/authorize?login=${encodeURIComponent(requestLogin)}`, {
          headers: { "x-gm-internal-token": process.env.ACCESS_INTERNAL_SECRET ?? "" },
          cache: "no-store",
        });
        const access = response.ok ? await response.json() as { authorized?: boolean; member?: { role?: string } } : null;
        if (!access?.authorized || !access.member?.role) {
          return new NextResponse("This Tailscale identity has not been invited to GM Studio.", { status: 403, headers: { "cache-control": "no-store" } });
        }
        role = access.member.role;
      } catch {
        return new NextResponse("GM Studio access control is temporarily unavailable.", { status: 503, headers: { "cache-control": "no-store" } });
      }
    }
    if (role === "viewer" && !["GET", "HEAD", "OPTIONS"].includes(request.method.toUpperCase())) {
      return new NextResponse("Viewer access is read-only.", { status: 403, headers: { "cache-control": "no-store" } });
    }
    if (role !== "owner" && ["/access", "/operations", "/learning", "/api/media/learning/"].some((path) => request.nextUrl.pathname.startsWith(path))) {
      return new NextResponse("Owner access is required.", { status: 403, headers: { "cache-control": "no-store" } });
    }
    const authenticatedHeaders = new Headers(request.headers);
    authenticatedHeaders.set("x-gm-user-login", requestLogin);
    authenticatedHeaders.set("x-gm-user-role", role);
    return NextResponse.next({ request: { headers: authenticatedHeaders } });
  }

  return NextResponse.next();
}
