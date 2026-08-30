import { NextResponse } from "next/server";
import { phase9bMutation } from "@/lib/phase9bMutations";

export async function POST(req: Request) {
  try {
    const payload = await req.json();
    const action = payload.action; // mint, remove, wipe
    if (!action || !['mint', 'remove', 'wipe'].includes(action)) {
      return NextResponse.json({ error: "Invalid action" }, { status: 400 });
    }
    const endpoint = `/internal/phase9c/operator/${action === 'wipe' ? 'security' : 'economy'}/${action}`;
    const result = await phase9bMutation(endpoint, payload);
    return NextResponse.json(result);
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: error.status || 500 });
  }
}
