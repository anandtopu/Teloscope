import js from "@eslint/js";
import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";

export default [
    js.configs.recommended,
    {
        files: ["**/*.ts", "**/*.tsx"],
        languageOptions: {
            parser: tsParser,
            parserOptions: {
                ecmaVersion: 2022,
                sourceType: "module",
                ecmaFeatures: { jsx: true }
            },
            globals: {
                console: "readonly",
                process: "readonly",
                window: "readonly",
                document: "readonly",
                setTimeout: "readonly",
                clearTimeout: "readonly"
            }
        },
        plugins: {
            "@typescript-eslint": tsPlugin
        },
        rules: {
            "no-unused-vars": "off",
            "@typescript-eslint/no-unused-vars": "warn",
            "no-undef": "off"
        }
    }
];
