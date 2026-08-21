import { redirect } from "next/navigation";
import { ROUTES } from "@/shared/constants/routes";

export default async function RootPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect(`/${locale}${ROUTES.dashboard}`);
}
