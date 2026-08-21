# i18n and Error Messages

## Check for i18n before writing any user-facing string
Before writing a toast, an error message, a validation string — anything a user reads — check whether the project has an i18n system already:
- `next-intl`, `i18next`, or `react-i18next` in `package.json`
- a `messages/` or `locales/` directory
- a `middleware.ts` handling locale routing, or an `[locale]` segment under `app/`

**None of these present** → the project has no i18n yet. Write plain strings as normal; don't introduce an i18n system nobody asked for.

**Any of these present** → i18n is live. Every user-facing string — especially API error messages — goes through it. Don't mix a raw string in one component with `t(...)` in the next; pick one and stay consistent with what's already there.

## Backend error codes are the translation key, not the message
A backend following the `ApiResponse`/`ErrorPayload` convention (see `fastapi-modular-scaffold`'s `references/api-contract.md`) returns a stable, non-localized `error.code` (e.g. `identity_not_found`) alongside an English `error.message`. When i18n is present, **`code`** is what gets looked up and shown — `message` is the non-localized fallback, not the string a user reads:

```ts
// shared/lib/handle-api-error.ts
"use client";

import { useTranslations } from "next-intl";
import { ApiRequestError } from "@/shared/lib/api-client";

export function useApiErrorMessage() {
  const t = useTranslations("errors");

  return (error: unknown): string => {
    if (error instanceof ApiRequestError && t.has(error.code)) {
      return t(error.code);
    }
    if (error instanceof ApiRequestError) {
      return error.message;
    }
    return t("unknown");
  };
}
```
```json
// messages/en.json
{
  "errors": {
    "identity_not_found": "We couldn't find that user.",
    "unknown": "Something went wrong."
  }
}
```

Falling back to `error.message` when a key is missing means a new backend error code doesn't break the UI while translators catch up — it shows the English default until the key is added, not a raw key string or a crash.

## Toasts go through the same resolution, not just error boundaries

A mutation's `onError` showing a toast is exactly as much "a user-facing string derived from an API
response" as an error boundary is — easy to forget because a toast call sites feels like a one-liner,
not a rendering path. Route it through the same `useApiErrorMessage()`, not `error.message` inline:

```ts
onError: (error) => toast.error(getErrorMessage(error)), // getErrorMessage = useApiErrorMessage()
```

A success toast is a plain static string the mutation author writes (`"Order shipped"`), not derived
from `error.code` — it goes through the ordinary i18n check above (`t("shipped_successfully")` if i18n
exists, a plain string if it doesn't), the same as any other UI copy. The two cases use different
mechanisms (`error.code` lookup vs. a static translation key) because they answer different questions —
"what did the server say went wrong" vs. "what do we want to tell the user happened" — but both are
still user-facing strings this file's rule applies to. See `references/layer-examples.md`'s
`use-mark-order-shipped.ts` for both in one hook.

## Without i18n
No i18n system in the project → render `error.message` directly, there's no key to look up yet. Don't build a translation layer speculatively; add it when the project actually adds i18n, and switch error handling over to `error.code` at that point.

## Where this lives
`useApiErrorMessage` (or the equivalent for the project's i18n library) belongs in `shared/lib/` — it's generic infrastructure, not owned by any one module, per the same rule as everything else in `shared/`.
