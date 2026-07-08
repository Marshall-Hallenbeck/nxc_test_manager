import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    rules: {
      // The hydration guard pattern (setMounted(true) in a useEffect) is
      // required in Next.js SSR to prevent theme flicker. No clean alternative
      // avoids both a hydration mismatch and a setState-in-effect.
      "react-hooks/set-state-in-effect": "off",
    },
  },
]);

export default eslintConfig;
