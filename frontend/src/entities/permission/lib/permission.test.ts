import { describe, expect, it } from "vitest";
import { AUTH_STATUS } from "@/shared/constants/auth";
import { hasPermission } from "./permission";

describe("hasPermission", () => {
  it("returns false for a null or undefined source", () => {
    expect(hasPermission(null, "user", "read")).toBe(false);
    expect(hasPermission(undefined, "user", "read")).toBe(false);
  });

  it("returns false for an unauthenticated session even with a matching permissions array", () => {
    const session = { status: "unauthenticated", permissions: ["user.read"] };
    expect(hasPermission(session, "user", "read")).toBe(false);
  });

  it("returns true for an authenticated session with the matching permission", () => {
    const session = { status: AUTH_STATUS.AUTHENTICATED, permissions: ["user.read", "role.create"] };
    expect(hasPermission(session, "user", "read")).toBe(true);
  });

  it("returns false for an authenticated session missing the permission", () => {
    const session = { status: AUTH_STATUS.AUTHENTICATED, permissions: ["role.create"] };
    expect(hasPermission(session, "user", "read")).toBe(false);
  });

  it("returns false when an authenticated session's permissions field is not an array", () => {
    const session = { status: AUTH_STATUS.AUTHENTICATED, permissions: undefined };
    expect(hasPermission(session, "user", "read")).toBe(false);
  });

  it("returns true for a plain object with a matching permissions array (no status field)", () => {
    expect(hasPermission({ permissions: ["user.read"] }, "user", "read")).toBe(true);
  });

  it("returns true for a bare array of permission strings", () => {
    expect(hasPermission(["user.read", "role.create"], "user", "read")).toBe(true);
  });

  it("returns false for a bare array missing the permission", () => {
    expect(hasPermission(["role.create"], "user", "read")).toBe(false);
  });

  it("returns false for an object with neither status nor permissions", () => {
    expect(hasPermission({}, "user", "read")).toBe(false);
  });
});
