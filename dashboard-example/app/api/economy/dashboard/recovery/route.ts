import { NextRequest } from "next/server";
import { getDashboardSession } from "@/lib/dashboardAuth";
import { phase9bRead } from "@/lib/phase9bApi";
export async function GET(request: NextRequest) { const session = await getDashboardSession(); if (!session) return Response.json({ error: "unauthenticated" }, { status: 401 }); const limit = Number(request.nextUrl.searchParams.get("limit") ?? "50"); if (!Number.isInteger(limit) || limit < 1 || limit > 100) return Response.json({ error: "invalid_request" }, { status: 400 }); return phase9bRead(session, "/internal/phase9b/dashboard/recovery", { limit }); }
