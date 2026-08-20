import { redirect } from "next/navigation";
import { ROUTES } from "@/shared/constants/routes";

export default function RootPage() {
  redirect(ROUTES.login);
}
