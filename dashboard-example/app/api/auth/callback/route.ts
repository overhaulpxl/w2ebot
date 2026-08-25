import { createHash, timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { hashSessionToken, internalRequest, randomOpaqueToken, sha256 } from "@/lib/internalRequest";
import { SESSION_COOKIE } from "@/lib/dashboardAuth";

const STATE_COOKIE = "__Host-w2e_oauth_state";
const PKCE_COOKIE = "__Host-w2e_oauth_pkce";

function same(a: string, b: string) {
  const left = Buffer.from(a); const right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
}

export async function GET(request: NextRequest) {
  const publicUrl = process.env.DASHBOARD_PUBLIC_URL ?? "";
  try {
    const code = request.nextUrl.searchParams.get("code") ?? "";
    const state = request.nextUrl.searchParams.get("state") ?? "";
    const cookieState = request.cookies.get(STATE_COOKIE)?.value ?? "";
    const verifier = request.cookies.get(PKCE_COOKIE)?.value ?? "";
    if (!code || !state || !cookieState || !verifier || !same(state, cookieState)) throw new Error("unauthenticated_state_mismatch");
    const body = new URLSearchParams({
      client_id: process.env.DASHBOARD_DISCORD_CLIENT_ID ?? "",
      client_secret: process.env.DASHBOARD_DISCORD_CLIENT_SECRET ?? "",
      grant_type: "authorization_code",
      code,
      redirect_uri: `${publicUrl}/api/auth/callback`,
      code_verifier: verifier,
    });
    const tokenResponse = await fetch("https://discord.com/api/v10/oauth2/token", {
      method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body, cache: "no-store",
    });
    if (!tokenResponse.ok) throw new Error("unauthenticated_discord_token");
    const token = await tokenResponse.json() as { access_token?: string };
    const identityResponse = await fetch("https://discord.com/api/v10/users/@me", {
      headers: { Authorization: `Bearer ${token.access_token ?? ""}` }, cache: "no-store",
    });
    if (!identityResponse.ok) throw new Error("unauthenticated_discord_identity");
    const identity = await identityResponse.json() as { id?: string };
    if (!identity.id || !/^\d+$/.test(identity.id)) throw new Error("unauthenticated_bad_identity");
    const rawSession = randomOpaqueToken();
    const tokenHash = hashSessionToken(rawSession);
    const challenge = createHash("sha256").update(verifier).digest("base64url");
    const ipSource = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
    const ipKey = process.env.DASHBOARD_IP_HASH_KEY ?? "";
    if (Buffer.byteLength(ipKey, "utf8") < 32) throw new Error("capability_unavailable");
    const ipHash = createHash("sha256").update(`${ipKey}:${ipSource}`).digest("hex");
    await internalRequest(
      "/internal/phase9a/session/establish",
      { tokenHash, stateHash: sha256(state), pkceChallenge: challenge, ipHash },
      { actorId: identity.id, guildId: process.env.ALLOWED_SERVER_ID ?? "", sessionTokenHash: tokenHash, sessionVersion: 0 },
    );
    const response = NextResponse.redirect(new URL("/", publicUrl));
    response.cookies.set(SESSION_COOKIE, rawSession, {
      httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: 8 * 60 * 60,
    });
    response.cookies.set(STATE_COOKIE, "", { path: "/", maxAge: 0 });
    response.cookies.set(PKCE_COOKIE, "", { path: "/", maxAge: 0 });
    return response;
  } catch (e) {
    console.error("CALLBACK ROUTE ERROR:", e);
    const target = publicUrl.startsWith("https://") ? new URL("/login?error=unauthenticated", publicUrl) : new URL("https://invalid.local/login");
    const response = NextResponse.redirect(target);
    response.cookies.set(STATE_COOKIE, "", { path: "/", maxAge: 0 });
    response.cookies.set(PKCE_COOKIE, "", { path: "/", maxAge: 0 });
    return response;
  }
}
