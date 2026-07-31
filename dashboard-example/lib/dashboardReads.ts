import "server-only";

import { internalRequest, type InternalIdentity } from "./internalRequest";

const READ_MAP: Record<string, string> = {
  "/api/server": "server",
  "/api/radar": "radar",
  "/api/channels": "channels",
  "/api/announce-config": "announce-config",
  "/api/leaderboard": "leaderboard",
  "/api/market": "market",
  "/api/treasury": "treasury",
  "/api/boss": "boss",
  "/api/economy/stats": "economy/stats",
  "/api/economy/v1-supply": "economy/supply",
  "/api/economy/v1-marketplace": "economy/marketplace",
  "/api/economy/v1-casino": "economy/casino",
  "/api/economy/v1-crypto": "economy/crypto",
  "/api/economy/v1-mining": "economy/mining",
  "/api/economy/v1-phase8": "economy/phase8",
  "/api/marriages": "marriages",
  "/api/stats/summary": "stats/summary",
  "/api/bot/stats": "bot/stats",
  "/api/economy/level-distribution": "economy/level-distribution",
};

export function resolveDashboardRead(path: string): { resource: string; query: Record<string, string>; params: Record<string, string> } {
  const url = new URL(path, "https://dashboard.invalid");
  const query = Object.fromEntries(url.searchParams.entries());
  if (url.pathname.startsWith("/api/user/")) {
    const id = url.pathname.slice("/api/user/".length);
    if (!/^\d+$/.test(id)) throw new Error("invalid_request");
    return { resource: "user", query: {}, params: { id } };
  }
  if (url.pathname.startsWith("/api/economy/v1-profile/")) {
    const id = url.pathname.slice("/api/economy/v1-profile/".length);
    if (!/^\d+$/.test(id)) throw new Error("invalid_request");
    return { resource: "economy/profile", query: {}, params: { id } };
  }
  const resource = READ_MAP[url.pathname];
  if (!resource) throw new Error("invalid_request");
  if (resource !== "leaderboard" && Object.keys(query).length) throw new Error("invalid_request");
  if (resource === "leaderboard" && Object.keys(query).some((key) => !["sort", "limit"].includes(key))) {
    throw new Error("invalid_request");
  }
  return { resource, query, params: {} };
}

export async function dashboardRead<T>(path: string, identity: InternalIdentity): Promise<T> {
  const { resource, query, params } = resolveDashboardRead(path);
  return internalRequest<T>(`/internal/phase9a/read/${resource}`, { query, params }, identity);
}
