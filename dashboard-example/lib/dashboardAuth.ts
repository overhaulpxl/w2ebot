import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { hashSessionToken, internalRequest, type InternalIdentity } from "./internalRequest";

export const SESSION_COOKIE = "__Host-w2e_admin_session";

export interface DashboardSession {
  sessionId: string;
  guildId: string;
  userId: string;
  permissions: string[];
  version: number;
  idleExpiresAt: string;
  absoluteExpiresAt: string;
  signingKeyId: string;
}

export interface ValidatedSession {
  session: DashboardSession;
  identity: InternalIdentity;
}

export async function getDashboardSession(requiredPermission = "DASHBOARD_VIEW"): Promise<ValidatedSession | null> {
  const cookieStore = await cookies();
  const raw = cookieStore.get(SESSION_COOKIE)?.value;
  if (!raw) return null;
  const tokenHash = hashSessionToken(raw);
  try {
    const result = await internalRequest<{ session: DashboardSession }>(
      "/internal/phase9a/session/validate",
      {},
      { actorId: "0", guildId: process.env.ALLOWED_SERVER_ID ?? "", sessionTokenHash: tokenHash, sessionVersion: 0 },
      "DASHBOARD_VIEW",
    );
    const session = result.session;
    const allowed = requiredPermission === "DASHBOARD_VIEW" || session.permissions.includes(requiredPermission);
    if (!allowed) return null;
    return {
      session,
      identity: {
        actorId: session.userId,
        guildId: session.guildId,
        sessionTokenHash: tokenHash,
        sessionVersion: session.version,
      },
    };
  } catch {
    return null;
  }
}

export async function requireDashboardSession(requiredPermission = "DASHBOARD_VIEW"): Promise<ValidatedSession> {
  const validated = await getDashboardSession(requiredPermission);
  if (!validated) redirect("/login");
  return validated;
}

export async function clearSessionCookie(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE, "", {
    httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: 0,
  });
}

export async function setSessionCookie(rawToken: string): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE, rawToken, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 8 * 60 * 60,
  });
}
