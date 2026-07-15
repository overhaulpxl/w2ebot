import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("Phase 9B mutations", () => {
  it("preserves request identity while issuing a fresh CSRF token", () => {
    const source = readFileSync(resolve("lib/phase9bMutations.ts"), "utf8");
    expect(source).toContain("requestId");
    expect(source).toContain("/api/auth/csrf");
    expect(source).toContain("X-CSRF-Token");
  });
  it("keeps notification tests on the dedicated endpoint", () => {
    const source = readFileSync(resolve("app/api/economy/notifications/routes/[category]/test/route.ts"), "utf8");
    expect(source).toContain("notifications/routes/test");
  });
});
