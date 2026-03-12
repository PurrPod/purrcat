export default [
  {
    ignores: ['.next/**', 'node_modules/**', '**/*.ts', '**/*.tsx'],
  },
  {
    files: ['**/*.{js,cjs,mjs,jsx}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
    },
    rules: {},
  },
]
