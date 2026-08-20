"use client";

import { Button } from "@/shared/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/ui/card";
import { m } from "@/shared/lib/motion";

/**
 * Static placeholder — the button is disabled and does not start an OAuth
 * flow. Sub-issue #5 (SSO login) wires it up to WeUpBook DX OAuth2 + PKCE.
 */
export function LoginForm() {
  return (
    <m.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
    >
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Sign in to ITSM</CardTitle>
          <CardDescription>
            Continue with your WeUpBook DX account.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button className="w-full" disabled>
            Continue with WeUpBook DX
          </Button>
        </CardContent>
      </Card>
    </m.div>
  );
}
