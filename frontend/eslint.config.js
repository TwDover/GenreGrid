// Flat ESLint config for the Vue 3 + TypeScript frontend.
//
// Scope mirrors the backend ruff gate: catch real mistakes (unused symbols,
// unreachable code, misused Vue directives) without imposing a stylistic
// reformat. Two deliberate calibration choices:
//   * Type-aware linting is OFF — `vue-tsc --noEmit` already runs the full
//     type-check in CI, so ESLint stays fast and lint-only.
//   * `no-undef` is OFF — TypeScript resolves identifiers far more accurately
//     than ESLint's scope analysis (which false-flags browser/Node globals);
//     the type-check is the real guard against undefined names.
// The gate fails on errors; a few `any`s remain as warnings to burn down later.
import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import pluginVue from 'eslint-plugin-vue'

export default tseslint.config(
  {
    ignores: ['dist/**', 'dist-electron/**', 'release/**', 'node_modules/**', '*.config.*'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  // `essential` = correctness rules only (no opinionated formatting/style rules).
  ...pluginVue.configs['flat/essential'],
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: { parser: tseslint.parser },
    },
  },
  {
    rules: {
      'no-undef': 'off',            // TypeScript/vue-tsc handles identifier resolution
      'no-console': 'off',          // intentional in-app debug HUD + audio diagnostics
      'no-empty': ['error', { allowEmptyCatch: true }],  // localStorage guards swallow on purpose
      '@typescript-eslint/no-explicit-any': 'warn',  // a handful of Tone.js interop casts
      '@typescript-eslint/no-unused-vars': ['error', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
        caughtErrorsIgnorePattern: '^_',
      }],
    },
  },
)
