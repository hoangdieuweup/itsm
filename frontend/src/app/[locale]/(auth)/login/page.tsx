import { getTranslations, setRequestLocale } from "next-intl/server";
import { redirect } from "next/navigation";
import { LoginForm, fetchAuthSession } from "@/modules/auth";
import { ROUTES } from "@/shared/constants/routes";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "common.meta" });

  return {
    title: t("loginTitle"),
  };
}

export default async function LoginPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  if (session.status === "authenticated") {
    redirect(`/${locale}${ROUTES.dashboard}`);
  }

  return <LoginForm />;
}
