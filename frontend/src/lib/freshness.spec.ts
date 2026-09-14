import { describe, expect, it } from "vitest";
import type { Dashboard } from "./api";
import { isCurrent } from "./freshness";

const brief = { generated_at: "2026-09-14T06:58:00Z", expires_at: "2026-09-14T07:03:00Z", timezone: "America/Los_Angeles" } as Dashboard;
describe("freshness", () => {
  it("expires at the principal's midnight even inside the TTL", () => {
    expect(isCurrent(brief, new Date("2026-09-14T06:59:00Z"))).toBe(true);
    expect(isCurrent(brief, new Date("2026-09-14T07:00:00Z"))).toBe(false);
  });
  it("does not accept missing, expired or malformed expiry", () => {
    expect(isCurrent(null)).toBe(false);
    expect(isCurrent({ ...brief, expires_at: undefined })).toBe(false);
    expect(isCurrent({ ...brief, expires_at: "bad" })).toBe(false);
    expect(isCurrent({ ...brief, generated_at: "bad" }, new Date("2026-09-14T06:59:00Z"))).toBe(false);
    expect(isCurrent(brief, new Date("2026-09-14T07:04:00Z"))).toBe(false);
  });
});
