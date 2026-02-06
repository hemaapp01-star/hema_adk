// functions/eslint.config.js
export default [
  {
    ignores: ['node_modules/**'],
    files: ['**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
    },
    rules: {
      'max-len': ['warn', { code: 100 }],
      'require-jsdoc': 'off',
      'indent': ['error', 2],
      'comma-dangle': ['error', 'always-multiline'],
      'object-curly-spacing': ['error', 'always'],
    },
  },
];