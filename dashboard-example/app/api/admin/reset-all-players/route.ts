// app/api/admin/reset-all-players/route.ts
//
// Proxy aman untuk POST /api/reset-all-players (reset semua pemain).

import { botPost } from "@/lib/botApi";
import { NextResponse } from "next/server";

export async function POST() {
  // TODO: cek session admin di sini sebelum lanjut.
  try {
    const data = await botPost("/api/reset-all-players", {});
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
}
