module.exports = function (config) {
  config.set({
    frameworks: ['jasmine'],
    plugins: [require('karma-jasmine'), require('karma-chrome-launcher')],
    reporters: ['progress'],
    customLaunchers: { ChromeHeadlessNoSandbox: {
      base: 'ChromeHeadless', flags: ['--no-sandbox', '--disable-dev-shm-usage']
    }},
    browsers: ['ChromeHeadlessNoSandbox'], singleRun: true, restartOnFileChange: true
  });
};
