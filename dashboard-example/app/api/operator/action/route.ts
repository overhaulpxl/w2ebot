import { NextResponse } from "next/server";
import { internalRequest } from "@/lib/internalRequest";
import { getDashboardSession } from "@/lib/dashboardAuth";

export async function POST(req: Request) {
  const session = await getDashboardSession("OPERATOR_WRITE");
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  try {
    const payload = await req.json();
    const action = payload.action; // mint, remove, wipe
    if (!action || !['mint', 'remove', 'wipe'].includes(action)) {
      return NextResponse.json({ error: "Invalid action" }, { status: 400 });
    }
    const endpoint = `/internal/phase9c/operator/${action === 'wipe' ? 'security' : 'economy'}/${action}`;
    const result = await internalRequest(endpoint, session.identity as unknown as Record<string, unknown>, payload);
    return NextResponse.json(result);
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: error.status || 500 });
  }
}
