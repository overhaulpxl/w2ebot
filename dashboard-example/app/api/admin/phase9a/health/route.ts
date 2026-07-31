import { NextResponse } from "next/server";
import { getDashboardSession } from "@/lib/dashboardAuth";
import { internalRequest } from "@/lib/internalRequest";

export async function GET() {
  const validated = await getDashboardSession();
  if (!validated) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  try {
    const data = await internalRequest("/internal/phase9a/health", {}, validated.identity);
    return NextResponse.json(data, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "internal_error" }, { status: 503 });
  }
}
