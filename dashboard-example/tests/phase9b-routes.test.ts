import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("Phase 9B API contract", () => {
  const routes = ["dashboard/overview", "dashboard/supply", "dashboard/flows", "dashboard/liabilities",
    "dashboard/marketplace", "dashboard/casino-options", "dashboard/giveaway", "dashboard/crypto-mining",
    "dashboard/recovery", "notifications/routes", "controls/pause", "controls/resume", "recovery/resolve"];
  it("has explicit routes without an arbitrary forwarding proxy", () => {
    for (const route of routes) expect(existsSync(resolve(`app/api/economy/${route}/route.ts`)), route).toBe(true);
    expect(existsSync(resolve("app/api/economy/[...path]/route.ts"))).toBe(false);
  });
  it("shares the server session guard", () => {
    const protectedRoutes = [...routes,
      "notifications/routes/[category]", "notifications/routes/[category]/test"];
    for (const route of protectedRoutes) {
      expect(readFileSync(resolve(`app/api/economy/${route}/route.ts`), "utf8"), route)
        .toContain("getDashboardSession");
    }
    const helper = readFileSync(resolve("lib/phase9bApi.ts"), "utf8");
    expect(helper).toContain("ValidatedSession");
    expect(helper).toContain("internalRequest");
  });
});
