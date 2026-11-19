// Rasterize report charts with the provided bundled dependency directory.
const path = require('path');
const sharp = require(path.join(process.argv[2], 'sharp'));
sharp(process.argv[3], {density: 200}).png().toFile(process.argv[4])
  .catch(error => { console.error(error); process.exitCode = 1; });
