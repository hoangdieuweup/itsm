import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Dashboard — ITSM",
};

export default function DashboardPage() {
  return (
    <div>
      <h1 className="text-xl font-semibold">Dashboard</h1>
      <p className="text-muted-foreground text-sm">
        Ticket and asset widgets land here in a later milestone.
      </p>
    </div>
  );
}
