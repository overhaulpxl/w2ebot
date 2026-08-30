import { NextResponse } from "next/server";
import { internalRequest } from "@/lib/internalRequest";
import { getDashboardSession } from "@/lib/dashboardAuth";

export async function GET() {
  const session = await getDashboardSession("DASHBOARD_VIEW");
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  try {
    const data = await internalRequest("/internal/phase9c/discord/channels", {}, session.identity as any);
    return NextResponse.json(data);
  } catch (error: any) {
    console.error("Failed to fetch discord channels:", error);
    return NextResponse.json(
      { error: error.message || "Failed to fetch channels" },
      { status: error.status || 500 }
    );
  }
}
