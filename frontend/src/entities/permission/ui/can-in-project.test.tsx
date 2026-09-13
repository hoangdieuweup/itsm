import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { PermissionProvider } from "../model/permission-context";
import { ProjectPermissionProvider } from "../model/project-permission-context";
import { CanInProject } from "./can-in-project";

vi.mock("@/shared/lib/api-client", () => ({
  apiFetch: vi.fn(() =>
    Promise.resolve({ projectId: "b3f1c2e4-1111-4444-8888-000000000000", permissions: ["environment.update"] }),
  ),
}));

function renderWithProviders(ui: React.ReactNode, globalPermissions: string[] = []) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <PermissionProvider permissions={globalPermissions as never}>
        <ProjectPermissionProvider projectId="b3f1c2e4-1111-4444-8888-000000000000">{ui}</ProjectPermissionProvider>
      </PermissionProvider>
    </QueryClientProvider>,
  );
}

describe("CanInProject", () => {
  it("falls back to the global set while the project query is pending", () => {
    renderWithProviders(
      <CanInProject I="update" a="project">
        <div>visible</div>
      </CanInProject>,
      ["project.update"],
    );
    expect(screen.getByText("visible")).toBeInTheDocument();
  });

  it("renders children once the project-scoped permission resolves", async () => {
    renderWithProviders(
      <CanInProject I="update" a="environment">
        <div>editor-only</div>
      </CanInProject>,
    );
    await waitFor(() => expect(screen.getByText("editor-only")).toBeInTheDocument());
  });

  it("renders fallback when neither global nor project set grants it", async () => {
    renderWithProviders(
      <CanInProject I="delete" a="project" fallback={<div>denied</div>}>
        <div>hidden</div>
      </CanInProject>,
    );
    await waitFor(() => expect(screen.getByText("denied")).toBeInTheDocument());
  });
});
