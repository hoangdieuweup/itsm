"use client";

import { Toaster as SonnerToaster } from "sonner";

export { toast } from "sonner";

/**
 * Pre-configured Sonner toast container — mounted once in AppProviders.
 * Uses `richColors` for semantic coloring and top-right positioning.
 */
export function Toaster() {
  return (
    <SonnerToaster
      position="top-right"
      richColors
      closeButton
      toastOptions={{
        duration: 4000,
        className: "text-sm",
      }}
    />
  );
}
