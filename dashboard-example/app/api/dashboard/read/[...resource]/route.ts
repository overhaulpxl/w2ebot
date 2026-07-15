import { NextRequest, NextResponse } from "next/server";
import { getDashboardSession } from "@/lib/dashboardAuth";
import { dashboardRead } from "@/lib/dashboardReads";

export async function GET(request: NextRequest, context: { params: Promise<{ resource: string[] }> }) {
  const validated = await getDashboardSession();
  if (!validated) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  const resource = (await context.params).resource.join("/");
  const query = request.nextUrl.search;
  try {
    const result = await dashboardRead(`/api/${resource}${query}`, validated.identity);
    return NextResponse.json(result, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const code = error instanceof Error ? error.message : "internal_error";
    return NextResponse.json({ error: code }, { status: code === "invalid_request" ? 400 : 403 });
  }
}
