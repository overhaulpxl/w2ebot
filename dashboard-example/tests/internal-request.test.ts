import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("signed internal request contract", () => {
  const source = readFileSync(resolve("lib/internalRequest.ts"), "utf8");
  it("binds canonical request attributes", () => {
    for (const field of ["W2E-P9A", "permissionClass", "sessionTokenHash", "sessionVersion", "X-W2E-Payload-Hash"]) {
      expect(source).toContain(field);
    }
  });
  it("does not use the legacy dashboard token", () => expect(source).not.toContain("DASHBOARD_TOKEN"));
  it("does not depend on locale-aware key ordering", () => expect(source).not.toContain("localeCompare"));
});
