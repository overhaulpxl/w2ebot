// app/api/admin/reset-cooldown/route.ts
//
// Proxy aman untuk POST /api/user/{id}/reset-cooldown.

import { botPost } from "@/lib/botApi";
import { NextResponse } from "next/server";

const TYPES = ["work", "rob", "pray", "curse", "daily", "all"];

export async function POST(req: Request) {
  // TODO: cek session admin di sini sebelum lanjut.
  let payload: { userId?: string; type?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const { userId, type } = payload;
  if (!userId || !/^\d+$/.test(userId)) {
    return NextResponse.json({ error: "userId tidak valid" }, { status: 400 });
  }
  if (!type || !TYPES.includes(type)) {
    return NextResponse.json({ error: `type harus salah satu dari: ${TYPES.join(", ")}` }, { status: 400 });
  }
  try {
    const data = await botPost(`/api/user/${userId}/reset-cooldown`, { type });
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
}
