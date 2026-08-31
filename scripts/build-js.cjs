// No bundler: publish the installed Chart.js browser distribution for Django staticfiles.
const { copyFileSync, mkdirSync } = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const source = path.join(root, "node_modules", "chart.js");
const destination = path.join(root, "static", "vendor", "chartjs");
mkdirSync(destination, { recursive: true });
for (const filename of ["chart.umd.min.js", "chart.umd.min.js.map"]) {
  copyFileSync(
    path.join(source, "dist", filename),
    path.join(destination, filename),
  );
}
copyFileSync(
  path.join(source, "LICENSE.md"),
  path.join(destination, "LICENSE.md"),
);
console.log("Chart.js browser assets copied to static/vendor/chartjs.");
