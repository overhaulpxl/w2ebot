import { NextRequest } from "next/server";
import { getDashboardSession } from "@/lib/dashboardAuth";
import { phase9bRead } from "@/lib/phase9bApi";
export async function GET(request: NextRequest) { const session = await getDashboardSession(); if (!session) return Response.json({ error: "unauthenticated" }, { status: 401 }); const value = request.nextUrl.searchParams.get("windowDays") ?? "7"; if (!new Set(["7","30"]).has(value)) return Response.json({ error: "invalid_request" }, { status: 400 }); return phase9bRead(session, "/internal/phase9b/dashboard/flows", { windowDays: Number(value) }); }
