import { NextResponse } from "next/server";
import { getDashboardSession } from "@/lib/dashboardAuth";
import { internalRequest } from "@/lib/internalRequest";

export async function GET() {
  const validated = await getDashboardSession("DASHBOARD_SECURITY_ADMIN");
  if (!validated) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  try {
    return NextResponse.json(await internalRequest("/internal/phase9a/operators/list", { limit: 100 },
      validated.identity, "DASHBOARD_SECURITY_ADMIN"), { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "internal_error" }, { status: 403 });
  }
}
