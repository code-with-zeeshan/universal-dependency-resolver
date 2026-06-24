module.exports = {
  moduleFileExtensions: ['js', 'vue', 'json'],
  transform: {
    '^.+\\.vue$': '@vue/vue3-jest',
    '^.+\\.js$': 'babel-jest',
  },
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  testEnvironment: 'jsdom',
  testEnvironmentOptions: {},
  testMatch: ['**/tests/unit/**/*.spec.js'],
  transformIgnorePatterns: ['/node_modules/(?!axios|filesize|semver|dayjs|chart.js|vue-chartjs|@vueuse|@heroicons|@vuelidate|vue-toastification|vue-virtual-scroller|vue3-clipboard|vue3-loading-overlay)/'],
  collectCoverageFrom: ['src/**/*.{js,vue}', '!src/main.js'],
}
