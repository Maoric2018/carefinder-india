// Render a handful of preview frames with one bundle: node stills.mjs <outDir> <frame> [frame...]
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';
import path from 'node:path';

const [outDir, ...frames] = process.argv.slice(2);
const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts')});
const composition = await selectComposition({serveUrl, id: 'CareFinder'});
for (const fr of frames.map(Number)) {
  const output = path.join(outDir, `f${String(fr).padStart(5, '0')}.jpg`);
  await renderStill({serveUrl, composition, frame: fr, output, imageFormat: 'jpeg', jpegQuality: 80, scale: 0.5});
  console.log(output);
}
