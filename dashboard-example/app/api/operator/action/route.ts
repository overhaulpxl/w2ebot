import { NextResponse } from "next/server";
import { internalRequest } from "@/lib/internalRequest";
import { getDashboardSession } from "@/lib/dashboardAuth";

export async function POST(req: Request) {
  const session = await getDashboardSession("DASHBOARD_SECURITY_ADMIN");
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  try {
    const payload = await req.json();
    const action = payload.action; 
    if (!action || !['mint', 'remove', 'wipe', 'spawn_boss', 'grant_item', 'cancel_listing', 'terminate_casino', 'crypto_tick', 'cancel_giveaway'].includes(action)) {
      return NextResponse.json({ error: "Invalid action" }, { status: 400 });
    }
    
    let category = "economy";
    if (action === 'wipe') category = "security";
    if (action === 'spawn_boss' || action === 'grant_item') category = "rpg";
    if (action === 'cancel_listing') category = "market";
    if (action === 'terminate_casino') category = "casino";
    if (action === 'crypto_tick') category = "crypto";
    if (action === 'cancel_giveaway') category = "giveaway";
    
    // Normalize endpoint name
    let endpointAction = action;
    if (action === 'cancel_listing') endpointAction = 'cancel';
    if (action === 'terminate_casino') endpointAction = 'terminate';
    if (action === 'crypto_tick') endpointAction = 'tick';
    if (action === 'cancel_giveaway') endpointAction = 'cancel';
    
    const endpoint = `/internal/phase9c/operator/${category}/${endpointAction}`;
    const result = await internalRequest(endpoint, payload, session.identity as any);
    return NextResponse.json(result);
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: error.status || 500 });
  }
}
