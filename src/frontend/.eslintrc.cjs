module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true,
  },
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    ecmaFeatures: {
      jsx: true,
    },
  },
  settings: {
    react: {
      version: "detect",
    },
  },
  plugins: ["react", "react-hooks", "react-refresh"],
  extends: [
    "eslint:recommended",
    "plugin:react/recommended",
    "plugin:react/jsx-runtime",
    "plugin:react-hooks/recommended",
  ],
  ignorePatterns: ["dist/", "node_modules/", "coverage/**", "output/**"],
  overrides: [
    {
      files: ["src/**/*.test.{js,jsx}", "src/test/**/*.{js,jsx}"],
      globals: {
        afterAll: "readonly",
        afterEach: "readonly",
        beforeAll: "readonly",
        beforeEach: "readonly",
        describe: "readonly",
        expect: "readonly",
        it: "readonly",
        vi: "readonly",
      },
    },
    {
      files: ["src/pages/**/*.{js,jsx}", "src/components/**/*.{js,jsx}", "src/contexts/**/*.{js,jsx}"],
      excludedFiles: ["src/**/*.test.{js,jsx}"],
      rules: {
        "no-restricted-imports": [
          "error",
          {
            paths: [
              {
                name: "@tanstack/react-query",
                message: "Import React Query only from feature hooks or approved wrappers.",
              },
            ],
            patterns: [
              {
                group: ["**/services/*"],
                message: "UI files must consume feature hooks/actions instead of services.",
              },
            ],
          },
        ],
      },
    },
    {
      files: ["src/**/*.{js,jsx}"],
      excludedFiles: [
        "src/main.jsx",
        "src/**/*.test.{js,jsx}",
        "src/test/**/*",
        "src/features/**/hooks/**/*.{js,jsx}",
        "src/hooks/useAppQueries.js",
        "src/hooks/useDrive.js",
        "src/hooks/useUpload.js",
      ],
      rules: {
        "no-restricted-imports": [
          "error",
          {
            paths: [
              {
                name: "@tanstack/react-query",
                message: "Import React Query only from feature hooks or approved wrappers.",
              },
            ],
          },
        ],
      },
    },
  ],
  rules: {
    "react/prop-types": "off",
    "no-unused-vars": [
      "error",
      {
        argsIgnorePattern: "^_",
        varsIgnorePattern: "^_",
      },
    ],
    "no-useless-catch": "error",
    "react-hooks/exhaustive-deps": "error",
  },
};
