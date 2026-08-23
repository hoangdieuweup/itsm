import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PermissionItem, Role } from "@/entities/role";
import { RoleFormDialog } from "./role-form-dialog";

const mutateCreate = vi.fn();
const mutateUpdate = vi.fn();

vi.mock("next-intl", () => ({
  useTranslations: () => {
    const t = ((key: string) => key) as ((key: string) => string) & { has: (key: string) => boolean };
    t.has = () => false;
    return t;
  },
}));

vi.mock("@/shared/lib/handle-api-error", () => ({
  useApiErrorMessage: () => (error: unknown) => String(error),
}));

const CATALOG: PermissionItem[] = [
  { id: "perm-user-read", resource: "user", action: "read", descriptionKey: "user_read" },
  { id: "perm-user-delete", resource: "user", action: "delete", descriptionKey: "user_delete" },
];

vi.mock("@/entities/role", async () => {
  const actual = await vi.importActual<typeof import("@/entities/role")>("@/entities/role");
  return {
    ...actual,
    usePermissions: () => ({ data: CATALOG }),
  };
});

vi.mock("../hooks/use-create-role", () => ({
  useCreateRole: () => ({ mutate: mutateCreate, isPending: false }),
}));

vi.mock("../hooks/use-update-role", () => ({
  useUpdateRole: () => ({ mutate: mutateUpdate, isPending: false }),
}));

beforeEach(() => {
  mutateCreate.mockReset();
  mutateUpdate.mockReset();
});

describe("RoleFormDialog", () => {
  it("renders nothing when closed", () => {
    const { container } = render(<RoleFormDialog isOpen={false} onClose={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("disables the create button until a name is entered", async () => {
    const user = userEvent.setup();
    render(<RoleFormDialog isOpen onClose={vi.fn()} />);

    expect(screen.getByRole("button", { name: "form.create" })).toBeDisabled();

    await user.type(screen.getByLabelText("form.nameLabel"), "On-call Reviewer");

    expect(screen.getByRole("button", { name: "form.create" })).toBeEnabled();
  });

  it("submits the selected permission ids when creating a role", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<RoleFormDialog isOpen onClose={onClose} />);

    await user.type(screen.getByLabelText("form.nameLabel"), "On-call Reviewer");
    await user.click(screen.getByText("user:read"));
    await user.click(screen.getByRole("button", { name: "form.create" }));

    expect(mutateCreate).toHaveBeenCalledTimes(1);
    const [payload] = mutateCreate.mock.calls[0] as [{ name: string; permissionIds: string[] }];
    expect(payload.name).toBe("On-call Reviewer");
    expect(payload.permissionIds).toEqual(["perm-user-read"]);
  });

  it("pre-fills name and permissions and calls update when editing an existing role", async () => {
    const user = userEvent.setup();
    const role: Role = {
      id: "role-1",
      name: "Existing Role",
      isSystem: false,
      permissions: [CATALOG[0]],
    };
    render(<RoleFormDialog isOpen onClose={vi.fn()} role={role} />);

    const nameInput = screen.getByLabelText("form.nameLabel") as HTMLInputElement;
    expect(nameInput.value).toBe("Existing Role");

    await user.click(screen.getByRole("button", { name: "form.save" }));

    expect(mutateUpdate).toHaveBeenCalledTimes(1);
    const [payload] = mutateUpdate.mock.calls[0] as [{ roleId: string; permissionIds: string[] }];
    expect(payload.roleId).toBe("role-1");
    expect(payload.permissionIds).toEqual(["perm-user-read"]);
  });
});
