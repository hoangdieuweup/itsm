import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Waypoints } from "lucide-react";
import { describe, expect, it, vi } from "vitest";
import { Drawer } from "./drawer";

describe("Drawer", () => {
  it("renders the title, icon badge, and children with correct dialog ARIA wiring", () => {
    render(
      <Drawer icon={Waypoints} title="Tunnels" onClose={vi.fn()} closeLabel="Close">
        <p>Panel body</p>
      </Drawer>,
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const heading = screen.getByRole("heading", { name: "Tunnels" });
    expect(dialog).toHaveAttribute("aria-labelledby", heading.id);
    expect(screen.getByText("Panel body")).toBeInTheDocument();
  });

  it("calls onClose when the header close button is clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Drawer icon={Waypoints} title="Tunnels" onClose={onClose} closeLabel="Close">
        <p>Panel body</p>
      </Drawer>,
    );

    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when Escape is pressed", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Drawer icon={Waypoints} title="Tunnels" onClose={onClose} closeLabel="Close">
        <p>Panel body</p>
      </Drawer>,
    );

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the backdrop is clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { container } = render(
      <Drawer icon={Waypoints} title="Tunnels" onClose={onClose} closeLabel="Close">
        <p>Panel body</p>
      </Drawer>,
    );

    const backdrop = container.querySelector('[aria-hidden="true"]');
    expect(backdrop).not.toBeNull();
    await user.click(backdrop as Element);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
