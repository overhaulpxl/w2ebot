// app/api/admin/xp/route.ts
//
// Proxy aman untuk POST /api/user/{id}/xp (tambah XP).

import { botPost } from "@/lib/botApi";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  // TODO: cek session admin di sini sebelum lanjut.
  let payload: { userId?: string; delta?: number };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const { userId, delta } = payload;
  if (!userId || !/^\d+$/.test(userId)) {
    return NextResponse.json({ error: "userId tidak valid" }, { status: 400 });
  }
  if (typeof delta !== "number" || delta === 0) {
    return NextResponse.json({ error: "delta harus angka bukan nol" }, { status: 400 });
  }
  try {
    const data = await botPost(`/api/user/${userId}/xp`, { delta });
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
}
