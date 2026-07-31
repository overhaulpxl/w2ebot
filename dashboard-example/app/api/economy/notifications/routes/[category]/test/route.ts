import { NextRequest } from "next/server";
import { getDashboardSession } from "@/lib/dashboardAuth";
import { phase9bWrite } from "@/lib/phase9bApi";
export async function POST(request: NextRequest, context: { params: Promise<{ category: string }> }) { const { category } = await context.params; return phase9bWrite(await getDashboardSession("NOTIFICATION_ROUTING_CONTROL"), request, "/internal/phase9b/notifications/routes/test", "NOTIFICATION_ROUTING_CONTROL", ["requestId","message"], { category: category.toUpperCase() }); }
