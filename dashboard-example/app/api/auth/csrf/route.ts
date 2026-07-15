import { NextRequest, NextResponse } from "next/server";
import { getDashboardSession } from "@/lib/dashboardAuth";
import { internalRequest } from "@/lib/internalRequest";

export async function GET(request: NextRequest) {
  const validated = await getDashboardSession();
  if (!validated) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  const method = request.nextUrl.searchParams.get("method") ?? "";
  const route = request.nextUrl.searchParams.get("route") ?? "";
  const requestId = request.nextUrl.searchParams.get("requestId") ?? "";
  if (!method || !route.startsWith("/") || !requestId) return NextResponse.json({ error: "invalid_request" }, { status: 400 });
  try {
    const result = await internalRequest("/internal/phase9a/csrf/issue", {
      method, canonicalRoute: route, requestId,
    }, validated.identity);
    return NextResponse.json(result, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "internal_error" }, { status: 403 });
  }
}
