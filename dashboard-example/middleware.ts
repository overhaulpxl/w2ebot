import { NextRequest, NextResponse } from "next/server";
const PUBLIC_PATHS = new Set(["/login", "/api/auth/login", "/api/auth/callback"]);
const SESSION_COOKIE = "__Host-w2e_admin_session";

export function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname;
  if (PUBLIC_PATHS.has(path)) return NextResponse.next();
  if (!request.cookies.get(SESSION_COOKIE)?.value) {
    if (path.startsWith("/api/")) {
      return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
    }
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
