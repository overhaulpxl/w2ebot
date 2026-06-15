// app/api/admin/boss-spawn/route.ts
//
// Proxy aman untuk POST /api/boss/spawn.

import { botPost } from "@/lib/botApi";
import { NextResponse } from "next/server";

export async function POST() {
  // TODO: cek session admin di sini sebelum lanjut.
  try {
    const data = await botPost("/api/boss/spawn", {});
    return NextResponse.json(data);
  } catch (e: any) {
    // Bot balikin 409 kalau boss sudah aktif; teruskan pesannya.
    const status = /already active/i.test(e.message) ? 409 : 400;
    return NextResponse.json({ error: e.message }, { status });
  }
}
