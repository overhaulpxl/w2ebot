import "server-only";

import { requireDashboardSession } from "./dashboardAuth";
import { internalRequest } from "./internalRequest";

export type IntegerString = `${number}`;
export type Freshness = "FRESH" | "STALE" | "UNAVAILABLE";

export interface DashboardEnvelope<T = unknown> {
  schemaVersion: string;
  guildId: string;
  asOf: string;
  sourceAsOf: string;
  freshness: Freshness;
  warnings: string[];
  data: T;
}

export const PHASE9B_READS = {
  overview: "/internal/phase9b/dashboard/overview",
  supply: "/internal/phase9b/dashboard/supply",
  flows: "/internal/phase9b/dashboard/flows",
  liabilities: "/internal/phase9b/dashboard/liabilities",
  marketplace: "/internal/phase9b/dashboard/marketplace",
  "casino-options": "/internal/phase9b/dashboard/casino-options",
  giveaway: "/internal/phase9b/dashboard/giveaway",
  "crypto-mining": "/internal/phase9b/dashboard/crypto-mining",
  recovery: "/internal/phase9b/dashboard/recovery",
  notifications: "/internal/phase9b/notifications/routes/list",
} as const;

export type Phase9BRead = keyof typeof PHASE9B_READS;

export async function loadEconomyDashboard<T = unknown>(
  resource: Phase9BRead,
  payload: Record<string, unknown> = {},
): Promise<T> {
  const validated = await requireDashboardSession();
  return internalRequest<T>(PHASE9B_READS[resource], payload, validated.identity);
}
