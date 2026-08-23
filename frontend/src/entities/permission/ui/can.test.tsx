import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PermissionProvider } from "../model/permission-context";
import { Can } from "./can";

function renderWithPermissions(permissions: string[], ui: React.ReactNode) {
  return render(
    <PermissionProvider permissions={permissions as never}>{ui}</PermissionProvider>,
  );
}

describe("Can", () => {
  it("renders children when the permission is granted", () => {
    renderWithPermissions(["user.read"], (
      <Can I="read" a="user">
        <span>Visible</span>
      </Can>
    ));
    expect(screen.getByText("Visible")).toBeInTheDocument();
  });

  it("renders nothing by default when the permission is missing", () => {
    renderWithPermissions([], (
      <Can I="read" a="user">
        <span>Visible</span>
      </Can>
    ));
    expect(screen.queryByText("Visible")).not.toBeInTheDocument();
  });

  it("renders the fallback when the permission is missing and a fallback is given", () => {
    renderWithPermissions([], (
      <Can I="read" a="user" fallback={<span>No access</span>}>
        <span>Visible</span>
      </Can>
    ));
    expect(screen.queryByText("Visible")).not.toBeInTheDocument();
    expect(screen.getByText("No access")).toBeInTheDocument();
  });

  it("supports the render-prop pattern for disable-instead-of-hide UI", () => {
    renderWithPermissions([], (
      <Can I="delete" a="user">
        {({ isAllowed }) => <button disabled={!isAllowed}>Delete</button>}
      </Can>
    ));
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
  });

  it("does not require an exact resource/action match from a different permission", () => {
    renderWithPermissions(["role.create"], (
      <Can I="read" a="user">
        <span>Visible</span>
      </Can>
    ));
    expect(screen.queryByText("Visible")).not.toBeInTheDocument();
  });
});
