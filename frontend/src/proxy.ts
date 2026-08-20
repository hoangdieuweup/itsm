import createMiddleware from "next-intl/middleware";
import { routing } from "@/shared/lib/i18n/routing";

export default createMiddleware(routing);

export const config = {
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
