import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("dashboard route isolation", () => {
  it("removes unsafe legacy proxies", () => {
    for (const route of ["coins", "xp", "give-item", "reset-all-players", "boss-spawn", "announce"]) {
      expect(existsSync(resolve(`app/api/admin/${route}/route.ts`))).toBe(false);
    }
  });
  it("validates session in the signed read proxy", () => {
    expect(readFileSync(resolve("app/api/dashboard/read/[...resource]/route.ts"), "utf8"))
      .toContain("getDashboardSession");
  });
});
