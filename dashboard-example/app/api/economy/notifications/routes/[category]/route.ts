import { NextRequest } from "next/server";
import { getDashboardSession } from "@/lib/dashboardAuth";
import { phase9bRead, phase9bWrite } from "@/lib/phase9bApi";
export async function GET(_: NextRequest, context: { params: Promise<{ category: string }> }) { const { category } = await context.params; return phase9bRead(await getDashboardSession(), "/internal/phase9b/notifications/routes/details", { category: category.toUpperCase() }); }
export async function POST(request: NextRequest, context: { params: Promise<{ category: string }> }) { const { category } = await context.params; return phase9bWrite(await getDashboardSession("NOTIFICATION_ROUTING_CONTROL"), request, "/internal/phase9b/notifications/routes/update", "NOTIFICATION_ROUTING_CONTROL", ["requestId","enabled","channelId","roleMentionId","eventTypes","expectedVersion"], { category: category.toUpperCase() }); }
