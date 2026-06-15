// app/api/admin/give-item/route.ts
//
// Proxy aman untuk POST /api/user/{id}/give-item.

import { botPost } from "@/lib/botApi";
import { NextResponse } from "next/server";

const VALID_ITEMS = ["shield", "double_xp", "lucky_charm"];

export async function POST(req: Request) {
  // TODO: cek session admin di sini sebelum lanjut.

  let payload: { userId?: string; itemId?: string; qty?: number };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  const { userId, itemId, qty = 1 } = payload;
  if (!userId || !/^\d+$/.test(userId)) {
    return NextResponse.json({ error: "userId tidak valid" }, { status: 400 });
  }
  if (!itemId || !VALID_ITEMS.includes(itemId)) {
    return NextResponse.json(
      { error: `itemId harus salah satu dari: ${VALID_ITEMS.join(", ")}` },
      { status: 400 },
    );
  }

  try {
    const data = await botPost(`/api/user/${userId}/give-item`, {
      item_id: itemId,
      qty,
    });
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
}
