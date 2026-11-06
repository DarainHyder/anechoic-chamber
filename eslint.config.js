import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["**/node_modules/", "**/dist/", "**/.next/", ".venv/", "coverage/"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
);
