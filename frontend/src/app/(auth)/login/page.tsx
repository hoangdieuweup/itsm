import type { Metadata } from "next";
import { LoginForm } from "@/modules/auth";

export const metadata: Metadata = {
  title: "Sign in — ITSM",
};

export default function LoginPage() {
  return <LoginForm />;
}
