import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("response security headers", () => {
  const source = readFileSync(resolve("next.config.js"), "utf8");
  it("sets CSP, frame, MIME, referrer, and cache headers", () => {
    for (const header of ["Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy", "Cache-Control"]) {
      expect(source).toContain(header);
    }
  });
});
