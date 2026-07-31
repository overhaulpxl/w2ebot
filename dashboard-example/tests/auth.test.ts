import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("dashboard authentication contract", () => {
  it("uses a host-only secure session cookie", () => {
    const source = readFileSync(resolve("lib/dashboardAuth.ts"), "utf8");
    expect(source).toContain("__Host-w2e_admin_session");
    expect(source).toContain("httpOnly: true");
    expect(source).toContain("secure: true");
    expect(source).toContain('sameSite: "lax"');
  });

  it("protects non-auth pages in middleware", () => {
    const source = readFileSync(resolve("middleware.ts"), "utf8");
    expect(source).toContain('NextResponse.redirect(new URL("/login"');
    expect(source).toContain("SESSION_COOKIE");
  });
});
