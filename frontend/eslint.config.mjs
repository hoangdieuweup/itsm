import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import boundaries from "eslint-plugin-boundaries";
import importPlugin from "eslint-plugin-import";
import eslintComments from "@eslint-community/eslint-plugin-eslint-comments";

// Enforces the layer/module rules from
// .claude/skills/nextjs-modular-architecture/references/enforcement-and-conventions.md
// as build failures instead of code-review reminders.
const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    plugins: {
      boundaries,
      import: importPlugin,
      "eslint-comments": eslintComments,
    },
    settings: {
      "boundaries/elements": [
        { type: "app", pattern: "src/app/*" },
        { type: "module", pattern: "src/modules/*", capture: ["name"] },
        { type: "entity", pattern: "src/entities/*", capture: ["name"] },
        { type: "shared", pattern: "src/shared/*" },
      ],
    },
    rules: {
      // eslint-plugin-boundaries v7 API: the rule was renamed from
      // `boundaries/element-types`, `rules` became `policies`, and both sides
      // of a policy now take an entity selector object instead of a bare string.
      "boundaries/dependencies": [
        "error",
        {
          default: "disallow",
          policies: [
            {
              from: { element: { type: "app" } },
              allow: { to: { element: { types: { anyOf: ["module", "entity", "shared"] } } } },
            },
            {
              // NOT other modules
              from: { element: { type: "module" } },
              allow: { to: { element: { types: { anyOf: ["entity", "shared"] } } } },
            },
            {
              // NOT modules
              from: { element: { type: "entity" } },
              allow: { to: { element: { type: "shared" } } },
            },
            {
              // "shared" has nothing below it in the dependency direction, but
              // (unlike "module"/"entity") its pattern has no capture group, so
              // e.g. src/shared/ui and src/shared/lib are distinct boundary
              // elements — they must be allowed to depend on each other, or
              // shared/ui/button.tsx couldn't import shared/lib/utils.
              from: { element: { type: "shared" } },
              allow: { to: { element: { type: "shared" } } },
            },
          ],
        },
      ],
      "import/no-cycle": "error",
      "eslint-comments/require-description": ["error", { ignore: [] }],
      complexity: ["error", 15],
      "max-lines": [
        "warn",
        { max: 600, skipBlankLines: true, skipComments: true },
      ],
      "@typescript-eslint/ban-ts-comment": [
        "error",
        {
          "ts-expect-error": "allow-with-description",
          "ts-ignore": true,
          minimumDescriptionLength: 10,
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
