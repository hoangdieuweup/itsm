import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Shield } from "lucide-react";
import { describe, expect, it, vi } from "vitest";
import { Dialog, DialogErrorAlert } from "./dialog";

describe("Dialog", () => {
  it("renders the title, icon badge, and children with correct dialog ARIA wiring", () => {
    render(
      <Dialog icon={Shield} title="Create Role" onClose={vi.fn()} closeLabel="Cancel">
        <p>Form body</p>
      </Dialog>,
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const heading = screen.getByRole("heading", { name: "Create Role" });
    expect(dialog).toHaveAttribute("aria-labelledby", heading.id);
    expect(screen.getByText("Form body")).toBeInTheDocument();
  });

  it("calls onClose when the header close button is clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Dialog icon={Shield} title="Create Role" onClose={onClose} closeLabel="Cancel">
        <p>Form body</p>
      </Dialog>,
    );

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when Escape is pressed", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Dialog icon={Shield} title="Create Role" onClose={onClose} closeLabel="Cancel">
        <p>Form body</p>
      </Dialog>,
    );

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not close on Escape or a disabled close button when disableClose is set", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Dialog icon={Shield} title="Create Role" onClose={onClose} closeLabel="Cancel" disableClose>
        <p>Form body</p>
      </Dialog>,
    );

    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("calls onClose when the backdrop is clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Dialog icon={Shield} title="Create Role" onClose={onClose} closeLabel="Cancel">
        <p>Form body</p>
      </Dialog>,
    );

    const backdrop = document.body.querySelector('[aria-hidden="true"]');
    expect(backdrop).not.toBeNull();
    await user.click(backdrop as Element);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("DialogErrorAlert", () => {
  it("renders the message as an alert", () => {
    render(<DialogErrorAlert message="Something went wrong" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
  });
});
