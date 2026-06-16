// app/api/admin/birthday/route.ts
//
// Proxy aman untuk POST /api/user/{id}/birthday.

import { botPost } from "@/lib/botApi";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  // TODO: cek session admin

  let payload: { userId?: string; date?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  const { userId, date } = payload;
  if (!userId || !/^\d+$/.test(userId)) {
    return NextResponse.json({ error: "userId tidak valid" }, { status: 400 });
  }

  if (date && (date.length !== 5 || date[2] !== "-")) {
    return NextResponse.json({ error: "Format tanggal harus DD-MM" }, { status: 400 });
  }

  try {
    const data = await botPost(`/api/user/${userId}/birthday`, { date: date ?? "" });
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
}
