import { NextResponse } from "next/server";
import { getDashboardSession } from "@/lib/dashboardAuth";

export async function GET() {
  const validated = await getDashboardSession();
  if (!validated) return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  return NextResponse.json({ session: validated.session }, { headers: { "Cache-Control": "no-store" } });
}
