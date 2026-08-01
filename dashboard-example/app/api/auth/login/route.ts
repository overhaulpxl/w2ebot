import { createHash, randomBytes } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { internalRequest, randomOpaqueToken, sha256 } from "@/lib/internalRequest";

const STATE_COOKIE = "__Host-w2e_oauth_state";
const PKCE_COOKIE = "__Host-w2e_oauth_pkce";

export async function GET(request: NextRequest) {
  try {
    const state = randomOpaqueToken();
    const verifier = randomBytes(48).toString("base64url");
    const challenge = createHash("sha256").update(verifier).digest("base64url");
    const ipSource = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
    const ipKey = process.env.DASHBOARD_IP_HASH_KEY ?? "";
    if (Buffer.byteLength(ipKey, "utf8") < 32) throw new Error("capability_unavailable");
    const ipHash = createHash("sha256").update(`${ipKey}:${ipSource}`).digest("hex");
    await internalRequest("/internal/phase9a/oauth/start", {
      stateHash: sha256(state), pkceChallenge: challenge, ipHash, returnPath: "/",
    });
    const clientId = process.env.DASHBOARD_DISCORD_CLIENT_ID ?? "";
    const publicUrl = process.env.DASHBOARD_PUBLIC_URL ?? "";
    if (!clientId || !publicUrl.startsWith("https://")) throw new Error("capability_unavailable");
    const target = new URL("https://discord.com/oauth2/authorize");
    target.searchParams.set("client_id", clientId);
    target.searchParams.set("response_type", "code");
    target.searchParams.set("redirect_uri", `${publicUrl}/api/auth/callback`);
    target.searchParams.set("scope", "identify");
    target.searchParams.set("state", state);
    target.searchParams.set("code_challenge", challenge);
    target.searchParams.set("code_challenge_method", "S256");
    const response = NextResponse.redirect(target);
    const options = { httpOnly: true, secure: true, sameSite: "lax" as const, path: "/", maxAge: 600 };
    response.cookies.set(STATE_COOKIE, state, options);
    response.cookies.set(PKCE_COOKIE, verifier, options);
    return response;
  } catch (e) {
    console.error("LOGIN ROUTE ERROR:", e);
    return NextResponse.json({ error: "capability_unavailable" }, { status: 503 });
  }
}
