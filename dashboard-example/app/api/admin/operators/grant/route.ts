import { NextRequest, NextResponse } from "next/server";
import { getDashboardSession } from "@/lib/dashboardAuth";
import { internalRequest } from "@/lib/internalRequest";

export async function POST(request: NextRequest) {
  const validated = await getDashboardSession("DASHBOARD_SECURITY_ADMIN");
  if (!validated) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  const body = await request.json().catch(() => null) as Record<string, unknown> | null;
  const csrfToken = request.headers.get("x-csrf-token") ?? "";
  if (!body || !csrfToken) return NextResponse.json({ error: "invalid_request" }, { status: 400 });
  try {
    return NextResponse.json(await internalRequest("/internal/phase9a/operators/grant", { ...body, csrfToken },
      validated.identity, "DASHBOARD_SECURITY_ADMIN"));
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "internal_error" }, { status: 409 });
  }
}
