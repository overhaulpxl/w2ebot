// app/api/admin/bg/route.ts
//
// Proxy aman untuk POST /api/user/{id}/bg.

import { botPost } from "@/lib/botApi";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  // TODO: cek session admin

  let payload: { userId?: string; url?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  const { userId, url } = payload;
  if (!userId || !/^\d+$/.test(userId)) {
    return NextResponse.json({ error: "userId tidak valid" }, { status: 400 });
  }

  if (url && !url.startsWith("http://") && !url.startsWith("https://")) {
    return NextResponse.json({ error: "URL harus diawali http:// atau https://" }, { status: 400 });
  }

  try {
    const data = await botPost(`/api/user/${userId}/bg`, { url: url ?? "" });
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
}
