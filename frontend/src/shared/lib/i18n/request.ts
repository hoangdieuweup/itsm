import { getRequestConfig } from "next-intl/server";
import { hasLocale } from "next-intl";
import { routing } from "./routing";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested)
    ? requested
    : routing.defaultLocale;

  const [common, auth] = await Promise.all([
    import(`../../../../locales/${locale}/common.json`),
    import(`../../../../locales/${locale}/modules/auth.json`),
  ]);

  return {
    locale,
    messages: {
      common: common.default,
      auth: auth.default,
    },
  };
});
