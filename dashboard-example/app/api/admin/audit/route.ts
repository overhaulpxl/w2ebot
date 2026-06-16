// app/api/admin/audit/route.ts
//
// Proxy aman untuk GET /api/audit (token-gated). Token disuntik di server;
// browser cukup panggil /api/admin/audit.

import { botGetToken } from "@/lib/botApi";
import { NextResponse } from "next/server";

export async function GET() {
  // TODO: cek session admin di sini sebelum lanjut.
  try {
    const data = await botGetToken("/api/audit?limit=100");
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
}
