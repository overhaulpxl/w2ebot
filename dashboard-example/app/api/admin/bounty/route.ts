// app/api/admin/bounty/route.ts
//
// Proxy aman untuk POST /api/user/{id}/bounty.

import { botPost } from "@/lib/botApi";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  // TODO: cek session admin

  let payload: { userId?: string; amount?: number };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  const { userId, amount } = payload;
  if (!userId || !/^\d+$/.test(userId)) {
    return NextResponse.json({ error: "userId tidak valid" }, { status: 400 });
  }

  if (typeof amount !== "number" || !Number.isInteger(amount) || amount < 0) {
    return NextResponse.json({ error: "amount harus integer >= 0" }, { status: 400 });
  }

  try {
    const data = await botPost(`/api/user/${userId}/bounty`, { amount });
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
}
