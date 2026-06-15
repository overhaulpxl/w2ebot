// app/api/admin/coins/route.ts
//
// Proxy aman untuk POST /api/user/{id}/coins.
// Token disuntik di server; browser cukup panggil /api/admin/coins.

import { botPost } from "@/lib/botApi";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  // TODO: WAJIB cek session admin kamu di sini sebelum lanjut.
  // contoh: const session = await auth(); if (!session?.isAdmin) return NextResponse.json({error:"forbidden"},{status:403});

  let payload: { userId?: string; delta?: number; set?: number };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  const { userId, delta, set } = payload;
  if (!userId || !/^\d+$/.test(userId)) {
    return NextResponse.json({ error: "userId tidak valid" }, { status: 400 });
  }

  // Kirim hanya field yang dimaksud (delta ATAU set).
  const body = typeof set === "number" ? { set } : { delta };

  try {
    const data = await botPost(`/api/user/${userId}/coins`, body);
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
}
