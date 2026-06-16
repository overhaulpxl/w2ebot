// app/api/admin/persona/route.ts
//
// Proxy aman untuk POST /api/user/{id}/persona.

import { botPost } from "@/lib/botApi";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  // TODO: cek session admin

  let payload: { userId?: string; persona?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  const { userId, persona } = payload;
  if (!userId || !/^\d+$/.test(userId)) {
    return NextResponse.json({ error: "userId tidak valid" }, { status: 400 });
  }

  try {
    const data = await botPost(`/api/user/${userId}/persona`, { persona: persona ?? "" });
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
}
