import fs from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';
import sharp from 'sharp';
import Chafa from 'chafa-wasm';

function readArgs(argv) {
  const args = {};
  for (let index = 2; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith('--')) continue;
    const key = token.slice(2);
    args[key] = argv[index + 1] && !argv[index + 1].startsWith('--')
      ? argv[++index]
      : true;
  }
  return args;
}

function numberArg(args, name, fallback) {
  const value = Number(args[name]);
  return Number.isFinite(value) ? value : fallback;
}

function isSubjectPixel(red, green, blue) {
  const luminance = (red + green + blue) / 3;
  const darkOutline = luminance < 95;
  const pinkFill = red > 190 && red - green > 10 && red - blue > 8 && green > 90;
  return darkOutline || pinkFill;
}

function classifyCrop(data, info) {
  const mask = new Uint8Array(info.width * info.height);
  let minX = info.width;
  let minY = info.height;
  let maxX = -1;
  let maxY = -1;

  for (let y = 0; y < info.height; y += 1) {
    for (let x = 0; x < info.width; x += 1) {
      const offset = (y * info.width + x) * info.channels;
      const red = data[offset];
      const green = data[offset + 1];
      const blue = data[offset + 2];
      if (!isSubjectPixel(red, green, blue)) continue;
      mask[y * info.width + x] = 1;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }
  }

  if (maxX < 0) throw new Error('No subject pixels found in the selected crop');

  const padding = 12;
  const left = Math.max(0, minX - padding);
  const top = Math.max(0, minY - padding);
  const right = Math.min(info.width - 1, maxX + padding);
  const bottom = Math.min(info.height - 1, maxY + padding);
  const width = right - left + 1;
  const height = bottom - top + 1;
  const rgba = Buffer.alloc(width * height * 4);

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const source = (y + top) * info.width + (x + left);
      const target = (y * width + x) * 4;
      rgba[target] = 255;
      rgba[target + 1] = 255;
      rgba[target + 2] = 255;
      rgba[target + 3] = mask[source] ? 255 : 0;
    }
  }

  return { rgba, width, height, bbox: { left, top, right, bottom } };
}

function matrixToCodepoints(matrix) {
  return matrix.map((row) => row.map(([codepoint]) => (codepoint === 0 ? 32 : codepoint)));
}

async function main() {
  const args = readArgs(process.argv);
  if (!args.input || !args.output) {
    throw new Error('Usage: node image_to_matrix.mjs --input image.png --output matrix.json');
  }

  const source = sharp(args.input);
  const metadata = await source.metadata();
  const left = Math.max(0, Math.floor(numberArg(args, 'crop-left', metadata.width * 0.25)));
  const top = Math.max(0, Math.floor(numberArg(args, 'crop-top', metadata.height * 0.08)));
  const width = Math.min(
    metadata.width - left,
    Math.max(1, Math.floor(numberArg(args, 'crop-width', metadata.width * 0.5))),
  );
  const height = Math.min(
    metadata.height - top,
    Math.max(1, Math.floor(numberArg(args, 'crop-height', metadata.height * 0.76))),
  );
  const raw = await source
    .extract({ left, top, width, height })
    .removeAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  const prepared = classifyCrop(raw.data, raw.info);
  const preparedPng = await sharp(prepared.rgba, {
    raw: { width: prepared.width, height: prepared.height, channels: 4 },
  }).png().toBuffer();
  const imageBuffer = preparedPng.buffer.slice(
    preparedPng.byteOffset,
    preparedPng.byteOffset + preparedPng.byteLength,
  );

  const chafa = await Chafa();
  const imageToMatrix = promisify(chafa.imageToMatrix);
  const imageToHtml = promisify(chafa.imageToHtml);
  const config = {
    format: chafa.ChafaPixelMode.CHAFA_PIXEL_MODE_SYMBOLS.value,
    width: Math.max(1, Math.floor(numberArg(args, 'width', 18))),
    height: Math.max(1, Math.floor(numberArg(args, 'height', 16))),
    fontRatio: 0.5,
    colors: chafa.ChafaCanvasMode.CHAFA_CANVAS_MODE_TRUECOLOR.value,
    colorExtractor: chafa.ChafaColorExtractor.CHAFA_COLOR_EXTRACTOR_AVERAGE.value,
    colorSpace: chafa.ChafaColorSpace.CHAFA_COLOR_SPACE_RGB.value,
    symbols: 'block+border+space-wide-inverted',
    fill: 'none',
    fg: 0xffffff,
    bg: 0x000000,
    fgOnly: false,
    dither: chafa.ChafaDitherMode.CHAFA_DITHER_MODE_NONE.value,
    ditherGrainWidth: 4,
    ditherGrainHeight: 4,
    ditherIntensity: 1.0,
    preprocess: false,
    threshold: 0.5,
    optimize: 5,
    work: 5,
  };
  const [matrixResult, htmlResult] = await Promise.all([
    imageToMatrix(imageBuffer, config),
    imageToHtml(imageBuffer, config),
  ]);
  const matrix = matrixToCodepoints(matrixResult.matrix);
  const result = {
    source: path.basename(args.input),
    converter: 'chafa-wasm',
    converterVersion: '0.3.3',
    crop: { left, top, width, height },
    subjectBounds: prepared.bbox,
    output: { width: config.width, height: config.height },
    matrix,
    htmlPreview: htmlResult.html,
  };
  await fs.mkdir(path.dirname(args.output), { recursive: true });
  await fs.writeFile(args.output, `${JSON.stringify(result, null, 2)}\n`, 'utf8');
  process.stdout.write(JSON.stringify({
    output: args.output,
    crop: result.crop,
    subjectBounds: result.subjectBounds,
    outputSize: result.output,
    rows: matrix.map((row) => row.map((codepoint) => String.fromCodePoint(codepoint)).join('')),
  }, null, 2));
}

main().catch((error) => {
  console.error(error.stack || error.message || error);
  process.exitCode = 1;
});
