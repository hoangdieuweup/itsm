# Layers and Modules — detail

## Full directory tree
```
src/
├── app/
│   ├── layout.tsx
│   ├── providers.tsx
│   ├── orders/
│   │   ├── page.tsx
│   │   ├── loading.tsx
│   │   └── error.tsx
│   └── profile/
│       └── page.tsx
├── modules/
│   └── orders/
│       ├── api/
│       │   ├── fetchers.ts     # validates via model/schema.ts's zod schema, never a type assertion
│       │   ├── query-keys.ts
│       │   └── use-orders.ts
│       ├── model/
│       │   └── schema.ts       # zod schema + the type as z.infer of it — one definition, not two
│       ├── ui/
│       │   ├── order-list.tsx
│       │   ├── order-list-item.tsx
│       │   └── order-status-badge.tsx
│       ├── hooks/
│       │   └── use-mark-order-shipped.ts
│       └── index.ts
├── entities/
│   └── user/
│       ├── model/
│       │   └── schema.ts       # `userSchema` / `User` — single source of truth
│       ├── api/
│       │   ├── fetchers.ts
│       │   └── use-current-user.ts
│       ├── ui/
│       │   └── user-avatar.tsx
│       └── index.ts
├── shared/
│   ├── ui/                     # shadcn primitives + composed blocks
│   ├── lib/                    # api-client.ts, query-client.ts, motion.tsx, utils.ts
│   ├── constants/
│   ├── types/
│   └── hooks/
└── core/                       # QueryClientProvider, ThemeProvider, env
```

## Worked example: two modules need "User"
`orders` needs to show "created by &lt;user&gt;", `profile` shows that same user's own page. Both need the exact same `User` shape and an avatar component. This is the textbook case for `entities/` — and the exact mistake a baseline agent makes by default: it puts `User` inside a `users`/`profile` module, then has `orders` import from it directly, creating a module-to-module dependency that breaks the moment either module is refactored.

```ts
// entities/user/model/schema.ts
import { z } from "zod";

export const userSchema = z.object({
  id: z.string(),
  name: z.string(),
  email: z.string().email(),
  avatarUrl: z.string().url().nullable().optional(),
});
export type User = z.infer<typeof userSchema>;
```
The type is derived from the schema, not written separately — a fetcher validates against `userSchema` (`.parse()`) instead of asserting a shape it never actually checked. See `references/layer-examples.md` for the fetcher and the full module built around this.

```tsx
// entities/user/ui/user-avatar.tsx
import { Avatar, AvatarFallback, AvatarImage } from "@/shared/ui/avatar";
import type { User } from "@/entities/user/model/schema";

export function UserAvatar({ user, className }: { user: User; className?: string }) {
  // ...
}
```

```ts
// entities/user/index.ts — curated public API
export { userSchema, type User } from "./model/schema";
export { UserAvatar } from "./ui/user-avatar";
export { useCurrentUser } from "./api/use-current-user";
```

Now `modules/orders` imports the entity through its public API, never reaching into its internals:
```ts
// modules/orders/model/schema.ts
import { z } from "zod";
import { userSchema } from "@/entities/user";

export const orderStatusSchema = z.enum(["pending", "shipped", "delivered"]);
export type OrderStatus = z.infer<typeof orderStatusSchema>;

export const orderSchema = z.object({
  id: z.string(),
  orderNumber: z.string(),
  status: orderStatusSchema,
  createdBy: userSchema,
  totalAmount: z.number(),
});
export type Order = z.infer<typeof orderSchema>;
```
`orderSchema.createdBy` composes `entities/user`'s own `userSchema` rather than redeclaring the shape — the same reuse rule as the type used to follow, now one level down at the schema that produces the type.

```tsx
// modules/orders/ui/order-list-item.tsx
import { UserAvatar } from "@/entities/user";
// NOT: import { UserAvatar } from "@/modules/profile/ui/user-avatar"  — cross-module import, forbidden
```

If `profile` is itself a module, it also imports `User`/`UserAvatar` from `@/entities/user` — never from `@/modules/orders` or vice versa.

## Naming conventions
| Item | Convention | Example |
|---|---|---|
| Folders/files | kebab-case | `order-status-badge.tsx` |
| Components | PascalCase export | `export function OrderStatusBadge` |
| Hooks | camelCase, `use-` prefixed file | `use-orders.ts` → `useOrders` |
| Types/interfaces | PascalCase | `Order`, `OrderStatus` |
| Query key factory | `<domain>Keys` | `ordersKeys`, `userKeys` |

## When a module grows past this
If a module's `ui/` folder gets large, split by sub-feature inside it (`ui/list/`, `ui/detail/`) — don't reach for a new top-level layer. Layers describe architecture, not folder depth.

The same applies at file level: no file over ~500-600 lines, no function/component over cyclomatic complexity 15 (ESLint's `complexity` rule catches the second one). A single file crossing that line means it holds more than one concept — split it into a folder (see `enforcement-and-conventions.md#keeping-files-and-functions-small`), never flatten the module structure to avoid making a new folder.

## `modules/` vs `features/`
Some codebases (Bulletproof React, most community Next.js examples) call this top-level folder `features/` instead of `modules/`. Same concept — pick one name per project and stay consistent. This skill's examples use `modules/` since that maps directly to the "manage by module" framing most large-system architectures use.
