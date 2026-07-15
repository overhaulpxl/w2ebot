import { NextRequest, NextResponse } from "next/server";
import { getDashboardSession } from "@/lib/dashboardAuth";
import { internalRequest } from "@/lib/internalRequest";

export async function GET(request: NextRequest) {
  const validated = await getDashboardSession("OPERATOR_AUDIT_READ");
  if (!validated) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  try {
    const limit = Math.max(1, Math.min(Number(request.nextUrl.searchParams.get("limit") ?? "100"), 100));
    const data = await internalRequest("/internal/phase9b/audit/list", { limit },
      validated.identity, "OPERATOR_AUDIT_READ");
    return NextResponse.json(data, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "internal_error" }, { status: 403 });
  }
}
