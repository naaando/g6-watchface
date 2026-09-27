#!/usr/bin/env node
/**
 * Cross-check bin-decoder.js against the Python reference decoder.
 *
 * The golden checksums in tests/golden.json are produced by bin-decoder.js
 * itself, so they only catch regressions. This script compares against an
 * oracle that was written independently (Fogg/comp_decomp.py), which is the
 * only thing that can catch a systematic misreading of the format.
 *
 * Usage:
 *   python3 tests/dump_reference.py <dial.bin> /tmp/ref.json
 *   node    tests/compare-with-reference.js <dial.bin> /tmp/ref.json
 *
 * Or run the whole corpus, which regenerates every reference first:
 *   node tests/compare-with-reference.js --all
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const D = require('../bin-decoder.js');
const { DIALS } = require('./fixtures.js');

const all = process.argv.includes('--all');
const args = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const dumpScript = path.join(__dirname, 'dump_reference.py');

function sha256(imageData) {
  return require('crypto')
    .createHash('sha256')
    .update(Buffer.from(imageData.data.buffer, imageData.data.byteOffset, imageData.data.length))
    .digest('hex');
}

function readBin(file) {
  const buf = fs.readFileSync(file);
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
}

function compare(label, file, refPath) {
  const ref = JSON.parse(fs.readFileSync(refPath, 'utf8'));
  const dial = D.decodeDial(readBin(file), { name: label });

  const problems = [];
  if (dial.errors.length) {
    problems.push(`decoder reported errors: ${JSON.stringify(dial.errors)}`);
  }

  const seen = new Set();
  for (const block of dial.blocks) {
    const want = ref[block.name];
    if (!want) {
      problems.push(`${block.name} is not in the reference dump`);
      continue;
    }
    if (seen.has(block.name)) continue;
    seen.add(block.name);

    if (block.width !== want.w) {
      problems.push(`${block.name} width ${block.width} != ${want.w}`);
    }
    if (block.height !== want.h) {
      problems.push(`${block.name} height ${block.height} != ${want.h}`);
    }
    if (block.frames !== want.parts) {
      problems.push(`${block.name} frames ${block.frames} != ${want.parts}`);
    }
    if (block.strip.width !== want.w || block.strip.height !== want.h * want.parts) {
      problems.push(
        `${block.name} strip ${block.strip.width}x${block.strip.height} != ` +
          `${want.w}x${want.h * want.parts} (must be height*frames, vertical)`
      );
    }

    const got = sha256(block.strip);
    if (got !== want.sha) {
      // Narrow it down: a partial mismatch is almost always a frame boundary
      // problem, so report per-frame whether the damage is confined to some
      // frames or spread across all of them.
      const perFrame = [];
      const perFrameBytes = block.width * block.height * 4;
      for (let f = 0; f < block.frames; f++) {
        const slice = block.strip.data.subarray(f * perFrameBytes, (f + 1) * perFrameBytes);
        perFrame.push(sha256({ data: slice }));
      }
      const bad = perFrame.filter((s, i) => s !== want.sha).length;
      problems.push(
        `${block.name} pixels differ from the reference ` +
          `(${bad} of ${block.frames} frames wrong)`
      );
    }
  }

  for (const name of Object.keys(ref)) {
    if (!seen.has(name)) problems.push(`${name} is in the reference but was not decoded`);
  }

  const status = problems.length ? 'FAIL' : 'ok  ';
  console.log(`${status} ${label.padEnd(16)} ${Object.keys(ref).length} blocks compared`);
  for (const p of problems) console.log(`       ${p}`);
  return problems.length === 0;
}

let ok = true;

if (all) {
  for (const [label, file] of DIALS) {
    if (!fs.existsSync(file)) {
      console.log(`SKIP ${label}: fixture missing`);
      continue;
    }
    const refPath = path.join(require('os').tmpdir(), `ref_${label}.json`);
    execFileSync('python3', [dumpScript, file, refPath], { stdio: 'inherit' });
    ok = compare(label, file, refPath) && ok;
  }
} else {
  if (args.length < 2) {
    console.error('usage: node tests/compare-with-reference.js <dial.bin> <ref.json>');
    console.error('   or: node tests/compare-with-reference.js --all');
    process.exit(2);
  }
  ok = compare(path.basename(args[0]), args[0], args[1]);
}

process.exit(ok ? 0 : 1);
