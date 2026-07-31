import "server-only";

import { NextRequest, NextResponse } from "next/server";
import type { ValidatedSession } from "./dashboardAuth";
import { internalRequest } from "./internalRequest";

function statusFor(code: string): number {
  if (code === "unauthenticated") return 401;
  if (code === "forbidden") return 403;
  if (code === "not_found") return 404;
  if (code === "rate_limited") return 429;
  if (["version_conflict", "request_identity_conflict", "not_configured", "delivery_failed", "review_required"].includes(code)) return 409;
  if (code === "capability_unavailable") return 503;
  return code === "invalid_request" ? 400 : 500;
}

export async function phase9bRead(validated: ValidatedSession | null, route: string,
                                  payload: Record<string, unknown> = {}) {
  if (!validated) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  try {
    const data = await internalRequest(route, payload, validated.identity);
    return NextResponse.json(data, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const code = error instanceof Error ? error.message : "internal_error";
    return NextResponse.json({ error: code }, { status: statusFor(code) });
  }
}

export async function phase9bWrite(validated: ValidatedSession | null, request: NextRequest,
                                   route: string, permission: string,
                                   allowedKeys: readonly string[], additions: Record<string, unknown> = {}) {
  if (!validated) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  const body = await request.json().catch(() => null) as Record<string, unknown> | null;
  const csrfToken = request.headers.get("x-csrf-token") ?? "";
  if (!body || !csrfToken || Object.keys(body).some(key => !allowedKeys.includes(key))) {
    return NextResponse.json({ error: "invalid_request" }, { status: 400 });
  }
  try {
    const data = await internalRequest(route, { ...body, ...additions, csrfToken }, validated.identity, permission);
    return NextResponse.json(data, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const code = error instanceof Error ? error.message : "internal_error";
    return NextResponse.json({ error: code }, { status: statusFor(code) });
  }
}
