import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LogoutDialog } from "./logout-dialog";

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

describe("LogoutDialog", () => {
  it("renders nothing while closed", () => {
    render(<LogoutDialog isOpen={false} onClose={vi.fn()} onConfirm={vi.fn()} isPending={false} />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("signs out of ITSM only by default", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<LogoutDialog isOpen onClose={vi.fn()} onConfirm={onConfirm} isPending={false} />);

    expect(screen.getByRole("switch", { name: "endDxSessionLabel" })).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: "confirm" }));

    expect(onConfirm).toHaveBeenCalledWith({ endDxSession: false });
  });

  it("also ends the WeUp DX session when the switch is on", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<LogoutDialog isOpen onClose={vi.fn()} onConfirm={onConfirm} isPending={false} />);

    const toggle = screen.getByRole("switch", { name: "endDxSessionLabel" });
    await user.click(toggle);
    expect(toggle).toBeChecked();
    await user.click(screen.getByRole("button", { name: "confirm" }));

    expect(onConfirm).toHaveBeenCalledWith({ endDxSession: true });
  });

  it("describes what ending the WeUp DX session does", () => {
    render(<LogoutDialog isOpen onClose={vi.fn()} onConfirm={vi.fn()} isPending={false} />);

    expect(screen.getByRole("switch", { name: "endDxSessionLabel" })).toHaveAccessibleDescription(
      "endDxSessionHint",
    );
  });

  it("turns the switch back off when the dialog is cancelled", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { rerender } = render(
      <LogoutDialog isOpen onClose={onClose} onConfirm={vi.fn()} isPending={false} />,
    );

    await user.click(screen.getByRole("switch", { name: "endDxSessionLabel" }));
    await user.click(screen.getByRole("button", { name: "cancel" }));
    expect(onClose).toHaveBeenCalledTimes(1);

    rerender(<LogoutDialog isOpen={false} onClose={onClose} onConfirm={vi.fn()} isPending={false} />);
    rerender(<LogoutDialog isOpen onClose={onClose} onConfirm={vi.fn()} isPending={false} />);

    expect(screen.getByRole("switch", { name: "endDxSessionLabel" })).not.toBeChecked();
  });

  it("disables every action while signing out", () => {
    render(<LogoutDialog isOpen onClose={vi.fn()} onConfirm={vi.fn()} isPending />);

    expect(screen.getByRole("button", { name: "confirm" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "close" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "endDxSessionLabel" })).toHaveAttribute("aria-disabled", "true");
  });
});
