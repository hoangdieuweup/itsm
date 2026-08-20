#!/usr/bin/env node
// Scaffolds a module or entity following nextjs-modular-architecture's layout.
// Usage: node create-module.mjs <kebab-case-name> [--type=module|entity] [--root=src]

import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";

const args = process.argv.slice(2);
const name = args.find((a) => !a.startsWith("--"));
const type = (args.find((a) => a.startsWith("--type="))?.split("=")[1]) ?? "module";
const root = (args.find((a) => a.startsWith("--root="))?.split("=")[1]) ?? "src";

if (!name || !/^[a-z][a-z0-9-]*$/.test(name)) {
  console.error("Usage: node create-module.mjs <kebab-case-name> [--type=module|entity] [--root=src]");
  process.exit(1);
}
if (!["module", "entity"].includes(type)) {
  console.error('--type must be "module" or "entity"');
  process.exit(1);
}

const layerDir = type === "module" ? "modules" : "entities";
const base = join(root, layerDir, name);

const pascal = name.replace(/(^|-)([a-z])/g, (_, __, c) => c.toUpperCase());
const camel = pascal.charAt(0).toLowerCase() + pascal.slice(1);
const keysName = `${camel}Keys`;
const schemaName = `${camel}Schema`;

function write(relPath, content) {
  const full = join(base, relPath);
  mkdirSync(dirname(full), { recursive: true });
  if (existsSync(full)) {
    console.error(`skip (exists): ${full}`);
    return;
  }
  writeFileSync(full, content);
  console.log(`created ${full}`);
}

write(
  "model/schema.ts",
  `import { z } from "zod";

// TODO: replace with this entity's real fields. The type below is derived from this
// schema (z.infer), not written separately — see references/layer-examples.md.
export const ${schemaName} = z.object({
  id: z.string(),
});
export type ${pascal} = z.infer<typeof ${schemaName}>;

export const ${camel}ListSchema = z.array(${schemaName});
`
);

write(
  "api/query-keys.ts",
  `export const ${keysName} = {
  all: ["${name}"] as const,
  lists: () => [...${keysName}.all, "list"] as const,
  list: (filters?: Record<string, unknown>) => [...${keysName}.lists(), filters] as const,
  detail: (id: string) => [...${keysName}.all, "detail", id] as const,
};
`
);

write(
  "api/fetchers.ts",
  `import { apiFetch } from "@/shared/lib/api-client";
import { ${camel}ListSchema, type ${pascal} } from "../model/schema";

export async function fetch${pascal}List(): Promise<${pascal}[]> {
  const data = await apiFetch<unknown>("/api/${name}"); // TODO: real endpoint path
  return ${camel}ListSchema.parse(data);
}
`
);

write(
  `api/use-${name}.ts`,
  `"use client";

import { useQuery } from "@tanstack/react-query";
import { fetch${pascal}List } from "./fetchers";
import { ${keysName} } from "./query-keys";

export function use${pascal}List() {
  return useQuery({
    queryKey: ${keysName}.list(),
    queryFn: fetch${pascal}List,
  });
}
`
);

write(
  `ui/${name}-placeholder.tsx`,
  `export function ${pascal}Placeholder() {
  return <div>TODO: ${pascal} UI</div>;
}
`
);

if (type === "module") {
  write("hooks/.gitkeep", "");
}

write(
  "index.ts",
  `export { ${schemaName}, type ${pascal} } from "./model/schema";
export { ${keysName} } from "./api/query-keys";
export { use${pascal}List } from "./api/use-${name}";
export { ${pascal}Placeholder } from "./ui/${name}-placeholder";
`
);

console.log(`\n${type} "${name}" scaffolded at ${base}`);
if (type === "module") {
  console.log("Remember: this module may only import from entities/ and shared/, never another module.");
}
