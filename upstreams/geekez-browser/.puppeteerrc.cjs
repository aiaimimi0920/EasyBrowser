/**
 * @type {import("puppeteer").Configuration}
 */
module.exports = {
    // Skip Puppeteer's automatic Chrome download during npm install.
    // We handle the download manually in setup.js to support mirrors in China.
    skipDownload: true,
};
