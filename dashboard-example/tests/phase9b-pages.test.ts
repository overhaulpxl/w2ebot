import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("Phase 9B pages", () => {
  const pages = ["economy", "economy/supply", "economy/liabilities", "economy/marketplace",
    "economy/casino-options", "economy/crypto-mining", "economy/giveaway", "economy/recovery",
    "economy/notifications", "admin/audit"];
  it("creates every protected operational page", () => {
    for (const page of pages) expect(existsSync(resolve(`app/${page}/page.tsx`)), page).toBe(true);
  });
  it("uses server-side authenticated reads", () => {
    const source = readFileSync(resolve("lib/economyDashboard.ts"), "utf8");
    expect(source).toContain("requireDashboardSession");
    expect(source).toContain("internalRequest");
  });
});
