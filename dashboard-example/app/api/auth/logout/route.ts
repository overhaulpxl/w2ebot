import { NextRequest, NextResponse } from "next/server";
import { clearSessionCookie, getDashboardSession } from "@/lib/dashboardAuth";
import { internalRequest } from "@/lib/internalRequest";

export async function POST(request: NextRequest) {
  const validated = await getDashboardSession();
  if (!validated) { await clearSessionCookie(); return NextResponse.json({ error: "unauthenticated" }, { status: 401 }); }
  const body = await request.json().catch(() => null) as { requestId?: string } | null;
  const csrfToken = request.headers.get("x-csrf-token") ?? "";
  if (!body?.requestId || !csrfToken) return NextResponse.json({ error: "invalid_request" }, { status: 400 });
  try {
    const result = await internalRequest("/internal/phase9a/session/logout", {
      requestId: body.requestId, csrfToken,
    }, validated.identity);
    await clearSessionCookie();
    return NextResponse.json(result);
  } catch (error) {
    await clearSessionCookie();
    return NextResponse.json({ error: error instanceof Error ? error.message : "internal_error" }, { status: 403 });
  }
}
