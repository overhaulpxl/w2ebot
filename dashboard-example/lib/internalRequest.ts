import "server-only";

import { createHash, createHmac, randomBytes, randomUUID } from "node:crypto";

const BOT_API_URL = process.env.BOT_API_URL ?? "http://localhost:8081";
const KEY_ID = process.env.DASHBOARD_INTERNAL_KEY_ID ?? "";
const SIGNING_KEY = process.env.DASHBOARD_INTERNAL_SIGNING_KEY ?? "";
const SESSION_HASH_KEY = process.env.DASHBOARD_SESSION_HASH_KEY ?? "";
const GUILD_ID = process.env.ALLOWED_SERVER_ID ?? "";

export interface InternalIdentity {
  actorId: string;
  guildId: string;
  sessionTokenHash: string;
  sessionVersion: number;
}

function normalize(value: unknown): unknown {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) throw new Error("invalid_request");
    return value;
  }
  if (Array.isArray(value)) return value.map(normalize);
  if (typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
        .map(([key, item]) => [key, normalize(item)]),
    );
  }
  throw new Error("invalid_request");
}

export function canonicalJson(value: unknown): string {
  return JSON.stringify(normalize(value));
}

export function sha256(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

export function hashSessionToken(rawToken: string): string {
  if (Buffer.byteLength(SESSION_HASH_KEY, "utf8") < 32) throw new Error("capability_unavailable");
  return createHmac("sha256", SESSION_HASH_KEY).update(rawToken, "utf8").digest("hex");
}

export function randomOpaqueToken(): string {
  return randomBytes(32).toString("base64url");
}

export async function internalRequest<T>(
  route: string,
  payload: Record<string, unknown>,
  identity?: InternalIdentity,
  permissionClass = "DASHBOARD_VIEW",
): Promise<T> {
  if (!KEY_ID || Buffer.byteLength(SIGNING_KEY, "utf8") < 32 || !/^\d+$/.test(GUILD_ID)) {
    throw new Error("capability_unavailable");
  }
  const now = Math.floor(Date.now() / 1000);
  const requestId = typeof payload.requestId === "string" && payload.requestId
    ? payload.requestId
    : randomUUID();
  const nonce = randomOpaqueToken();
  const body = canonicalJson(payload);
  const actorId = identity?.actorId ?? "0";
  const guildId = identity?.guildId ?? GUILD_ID;
  const sessionHash = identity?.sessionTokenHash ?? "";
  const sessionVersion = identity?.sessionVersion ?? 0;
  const digest = sha256(body);
  const signingText = [
    "W2E-P9A", KEY_ID, "POST", route, guildId, actorId, permissionClass, requestId,
    String(now), String(now + 30), nonce, digest, sessionHash, String(sessionVersion),
  ].join("\n");
  const signature = createHmac("sha256", SIGNING_KEY).update(signingText, "utf8").digest("hex");
  const response = await fetch(`${BOT_API_URL}${route}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-W2E-Key-Id": KEY_ID,
      "X-W2E-Method": "POST",
      "X-W2E-Route": route,
      "X-W2E-Guild-Id": guildId,
      "X-W2E-Actor-Id": actorId,
      "X-W2E-Permission": permissionClass,
      "X-W2E-Request-Id": requestId,
      "X-W2E-Issued-At": String(now),
      "X-W2E-Expires-At": String(now + 30),
      "X-W2E-Nonce": nonce,
      "X-W2E-Payload-Hash": digest,
      "X-W2E-Session-Hash": sessionHash,
      "X-W2E-Session-Version": String(sessionVersion),
      "X-W2E-Signature": signature,
    },
    body,
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({ error: "internal_error" }));
  if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : "internal_error");
  return data as T;
}
