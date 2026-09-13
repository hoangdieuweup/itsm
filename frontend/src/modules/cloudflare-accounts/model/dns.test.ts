import { describe, expect, it } from "vitest";
import { DNS_TYPES, DNS_TYPE_COLORS, isDnsType } from "./dns";

describe("dns model", () => {
  it("has a badge colour for every selectable record type", () => {
    for (const type of DNS_TYPES) {
      expect(DNS_TYPE_COLORS[type]).toBeTruthy();
    }
  });

  it("narrows only record types the form can select", () => {
    expect(isDnsType("HTTPS")).toBe(true);
    expect(isDnsType("PTR")).toBe(false);
  });
});
