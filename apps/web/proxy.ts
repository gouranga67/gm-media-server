import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

export function proxy(request: NextRequest) {
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
    if (!requestLogin || requestLogin !== expectedLogin) {
      return new NextResponse(
        "GM Studio is available only through its private Tailscale Serve address.",
        {
          status: 401,
          headers: { "cache-control": "no-store" },
        },
      );
    }
  }

  return NextResponse.next();
}
