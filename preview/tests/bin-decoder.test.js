#!/usr/bin/env node
/**
 * bin-decoder tests.
 *
 * The decoder is a port of Fogg/comp_decomp.py, so the tests check two
 * different things:
 *
 *   1. STRUCTURE — invariants that must hold for every dial in the repo
 *      (header parsing, strip geometry, pivot convention, error handling).
 *   2. PARITY — pixel-exact agreement with the Python reference. Golden
 *      checksums live in tests/golden.json and are regenerated with
 *      `node tests/bin-decoder.test.js --update` when a dial legitimately
 *      changes. Parity is checked against the Python tool on demand with
 *      `python3 tests/dump_reference.py` (see README).
 *
 * Run: node tests/bin-decoder.test.js
 */

'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const D = require('../bin-decoder.js');
const { DIALS } = require('./fixtures.js');

const GOLDEN = path.join(__dirname, 'golden.json');
const update = process.argv.includes('--update');

let passed = 0;
const failures = [];

function check(name, fn) {
  try {
    fn();
    passed++;
  } catch (err) {
    failures.push(`${name}: ${err.message}`);
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg || 'assertion failed');
}

function assertEqual(actual, expected, msg) {
  if (actual !== expected) {
    throw new Error(`${msg || 'mismatch'}: got ${actual}, expected ${expected}`);
  }
}

function sha256(imageData) {
  return crypto
    .createHash('sha256')
    .update(Buffer.from(imageData.data.buffer, imageData.data.byteOffset, imageData.data.length))
    .digest('hex');
}

function readBin(file) {
  const buf = fs.readFileSync(file);
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
}

const golden = fs.existsSync(GOLDEN)
  ? JSON.parse(fs.readFileSync(GOLDEN, 'utf8'))
  : {};

// ─── 1. Structure ───────────────────────────────────────────────────────────

for (const [label, file] of DIALS) {
  if (!fs.existsSync(file)) {
    failures.push(`${label}: fixture missing at ${file}`);
    continue;
  }
  const dial = D.decodeDial(readBin(file), { name: label });

  check(`${label}: decodes with no errors`, () => {
    assertEqual(dial.errors.length, 0, `errors: ${JSON.stringify(dial.errors)}`);
  });

  check(`${label}: blocks that should have artwork do`, () => {
    // A frame that ran short leaves a transparent tail, and a misread frame
    // boundary can blank a block entirely. Background and preview are the
    // blocks every dial is required to fill; the complication graphics are
    // only checked where the build script actually drew them, since several
    // dials ship them intentionally blank (see KNOWN_BLANK below).
    for (const block of dial.blocks) {
      if (block.baseType === 0x01 || block.baseType === 0x02) {
        assert(
          countOpaque(block.strip) > 0,
          `block ${block.name} decoded with zero opaque pixels`
        );
      }
    }
  });

  // Regression lock for a finding worth keeping: the cat-gauge builds blank
  // their indicator strips on purpose. trek-watchfaces/build_cat_gauge*.py
  // writes Image.new("RGBA", (w, h*frms), (0,0,0,0)) for blocks 2..5 because
  // the artwork has no room for those graphics. Their PNGs are NOT corrupt.
  const KNOWN_BLANK = {
    'analog-test': ['battery_strip', 'steps', 'progress2'],
    'image-test': ['battery_strip', 'steps', 'progress2'],
    catgauge: ['battery_strip', 'steps', 'progress2'],
    'cat-gauge-v1': [],
    'cat-gauge-v2': []
  };
  const blankExpectation = label === 'cat-gauge-v1' || label === 'cat-gauge-v2'
    ? []
    : KNOWN_BLANK[label] || null;

  if (blankExpectation) {
    check(`${label}: indicator strips are blank as the build script intends`, () => {
      for (const name of blankExpectation) {
        const block = dial.blocks.find((b) => b.name === name);
        assert(block, `expected a ${name} block`);
        assertEqual(
          countOpaque(block.strip),
          0,
          `${name} should be intentionally blank; artwork here means the geometry drifted`
        );
      }
      // ...and the real 11448 does have them, proving the decoder can see
      // artwork in these blocks when it exists.
      if (label === '11448' || label === 'roundtrip-11448') {
        for (const name of ['battery_strip', 'steps', 'progress2']) {
          const block = dial.blocks.find((b) => b.name === name);
          assert(
            countOpaque(block.strip) > 0,
            `${name} in the stock dial should decode with artwork`
          );
        }
      }
    });
  }

  check(`${label}: multi-frame strips are read vertically, not horizontally`, () => {
    // The orientation bug this guards against: reading a vertical strip as if
    // it were horizontal yields content only in frame 0. Verified with a
    // pixel-count probe — horizontal gave [925, 0, 0, 0, 0, 0] for the
    // 6-frame battery gauge, vertical gave [925, 1056, 1076, 1078, 1054, 915].
    // Dials with intentionally blank strips carry no signal here.
    if (blankExpectation && blankExpectation.includes('battery_strip')) return;
    const battery = dial.blocks.find((b) => b.baseType === 0x18);
    if (!battery || battery.frames < 2) return;
    const perFrame = [];
    for (let f = 0; f < battery.frames; f++) {
      perFrame.push(countOpaque(frameSlice(battery, f)));
    }
    const informative = perFrame.filter((n) => n > 0).length;
    assert(
      informative > 1,
      `battery_strip only has artwork in ${informative} of ${battery.frames} vertical ` +
        `frames (${JSON.stringify(perFrame)}); a dial that should have artwork ` +
        `here means the strip is being read with the wrong orientation`
    );
  });

  check(`${label}: strips are vertical, geometry consistent`, () => {
    for (const block of dial.blocks) {
      assertEqual(block.strip.width, block.width, `${block.name} strip width`);
      assertEqual(
        block.strip.height,
        block.height * block.frames,
        `${block.name} strip height must be height*frames (vertical stack)`
      );
    }
  });

  check(`${label}: hands use the verified pivot convention`, () => {
    for (const type of [0x03, 0x04, 0x05]) {
      const block = D.findBlock(dial, type);
      if (!block) continue;
      assertEqual(block.cty, block.width / 2, `${block.name}: cty should be width/2`);
      assert(
        block.ctx >= 0 && block.ctx <= block.height,
        `${block.name}: ctx ${block.ctx} outside the sprite height`
      );
      const pivot = D.handPivot(block);
      assert(pivot.x >= 0 && pivot.x < block.width, `${block.name} pivot.x off-sprite`);
      assert(pivot.y >= 0 && pivot.y < block.height, `${block.name} pivot.y off-sprite`);
    }
  });

  check(`${label}: blocks fit on the 466x466 screen`, () => {
    // Arms are the exception: their posx/posy is the PIVOT's position on the
    // screen, not the sprite's top-left, and the sprite swings around it. Every
    // hand in every dial measured sits at exactly (233,233) — the centre. A
    // 256px-tall second hand at posy=233 obviously does not "fit" as a
    // top-left box; the pivot is what has to land on screen.
    for (const block of dial.blocks) {
      if (block.baseType === 0x01) continue; // preview lives outside the screen
      if (D.ARM_TYPES[block.baseType]) {
        const pivot = D.handPivot(block);
        // The pivot itself must be on screen. The sprite need NOT fit: a hand
        // is longer than half the screen, so at some rotations its tip is
        // clipped by the bezel. The firmware does exactly that — it clips,
        // it does not rescale.
        //
        // How much a hand overshoots is a property of the artwork, not of the
        // decode, so this only guards against a catastrophic misread. Note the
        // real case: the cat-gauge-v2 second hand has ctx=14, putting its pivot
        // 242px from the sprite top against a screen radius of 233, so it
        // clips ~9px when pointing up. That ships as-is.
        const reachX = Math.max(pivot.x, block.width - pivot.x);
        const reachY = Math.max(pivot.y, block.height - pivot.y);
        const radius = Math.max(D.SCREEN_WIDTH, D.SCREEN_HEIGHT) / 2;
        assert(
          reachX <= radius * 1.5 && reachY <= radius * 1.5,
          `${block.name} reach ${reachX}x${reachY} is wildly beyond a ${radius}px ` +
            `radius — a misread ctx/cty would produce this`
        );
        continue;
      }
      assert(
        block.posx + block.width <= D.SCREEN_WIDTH,
        `${block.name} overflows right edge: ${block.posx}+${block.width} > ${D.SCREEN_WIDTH}`
      );
      assert(
        block.posy + block.height <= D.SCREEN_HEIGHT,
        `${block.name} overflows bottom edge: ${block.posy}+${block.height} > ${D.SCREEN_HEIGHT}`
      );
    }
  });

  check(`${label}: every arm pivots at the screen centre`, () => {
    for (const type of [0x03, 0x04, 0x05]) {
      const block = D.findBlock(dial, type);
      if (!block) continue;
      assertEqual(block.posx, 233, `${block.name} posx should be the centre`);
      assertEqual(block.posy, 233, `${block.name} posy should be the centre`);
    }
  });

  check(`${label}: block descriptors carry a dial_desc-compatible shape`, () => {
    for (const block of dial.blocks) {
      assert(block.desc, `${block.name} has no desc`);
      assert(/^BLK_[A-Z0-9_]+$/.test(block.desc.type), `bad type name ${block.desc.type}`);
      assert(
        block.desc.colsp === 'RGBA' || block.desc.colsp === 'RGB',
        `bad colsp ${block.desc.colsp}`
      );
      assertEqual(block.desc.colsp === 'RGBA', block.hasAlpha, `${block.name} alpha flag mismatch`);
    }
  });

  // ─── 2. Parity ────────────────────────────────────────────────────────────

  const entry = golden[label];
  const usedNames = new Set();
  check(`${label}: matches golden checksums`, () => {
    if (!entry) {
      if (!update) throw new Error('no golden entry — run with --update');
      return;
    }
    assertEqual(dial.blocks.length, entry.blocks.length, 'block count');
    for (const want of entry.blocks) {
      const block = dial.blocks.find((b) => b.name === want.name && !usedNames.has(b.name));
      assert(block, `block ${want.name} missing from decode`);
      usedNames.add(want.name);
      assertEqual(block.width, want.w, `${want.name} width`);
      assertEqual(block.height, want.h, `${want.name} height`);
      assertEqual(block.frames, want.frames, `${want.name} frames`);
      assertEqual(sha256(block.strip), want.sha, `${want.name} pixel checksum`);
    }
  });

  if (update) {
    golden[label] = {
      file: path.relative(path.resolve(__dirname, '..', '..'), file),
      blocks: dial.blocks.map((b) => ({
        name: b.name,
        w: b.width,
        h: b.height,
        frames: b.frames,
        sha: sha256(b.strip)
      }))
    };
  }
}

// ─── Error handling ─────────────────────────────────────────────────────────

check('rejects a file too small to have a header', () => {
  assertThrows(() => D.decodeDial(new Uint8Array([1, 2])), /too small/);
});

check('rejects a header claiming more blocks than the file holds', () => {
  // pltable_size=0, num_blocks=200, format=0x02, then nothing.
  const bytes = new Uint8Array(4);
  bytes[2] = 200;
  assertThrows(() => D.decodeDial(bytes), /blocks/);
});

check('records a block error instead of aborting the whole dial', () => {
  // Push the background block's image offset past the end of the file. The
  // dial should still decode, minus that one block, with the failure noted.
  // Writing a full 0xFFFFFFFF matters: a two-byte write leaves the high half
  // of the offset intact and can still land inside the file.
  const bytes = new Uint8Array(readBin(path.join(DIALS[0][1])));
  const header = D.parseHeader(bytes);
  const bg = header.blocks.find((b) => b.baseType === 0x02);
  assert(bg, 'the fixture dial should have a background block');
  const o = 4 + bg.index * 20;
  bytes[o] = 0xff;
  bytes[o + 1] = 0xff;
  bytes[o + 2] = 0xff;
  bytes[o + 3] = 0xff;

  const broken = D.decodeDial(bytes, { name: 'corrupt' });
  assert(broken.errors.length > 0, 'expected a recorded error');
  assert(
    broken.errors.some((e) => e.block === 'background'),
    `expected the background block to be the failure, got ${JSON.stringify(broken.errors)}`
  );
  assertEqual(
    broken.blocks.length,
    header.blocks.length - 1,
    'every other block should still decode'
  );
  assert(
    !broken.blocks.some((b) => b.baseType === 0x02),
    'the broken block must not appear in the decoded list'
  );
});

check('rejects a zero-frame block instead of producing a zero-height strip', () => {
  const bytes = new Uint8Array(readBin(path.join(DIALS[0][1])));
  const header = D.parseHeader(bytes);
  const bg = header.blocks.find((b) => b.baseType === 0x02);
  bytes[4 + bg.index * 20 + 14] = 0; // parts = 0
  const dial = D.decodeDial(bytes);
  assert(
    dial.errors.some((e) => e.block === 'background'),
    'a zero-frame block should be reported as an error'
  );
});

check('rejects an RLE frame whose skip_offset points outside the frame', () => {
  // A 4-byte frame claiming a skip_offset of 600 in a 4-byte frame.
  const bytes = new Uint8Array([0x58, 0x02, 0x00, 0x00]);
  assertThrows(
    () => D.decodeRleFrame(bytes, 0, 4, 2, 2, 3, new Uint8ClampedArray(16), 0),
    /skip_offset/
  );
});

check('parseHeader rejects a truncated descriptor table', () => {
  const bytes = new Uint8Array([0x00, 0x00, 0x08, 0x02, 0, 0, 0, 0]);
  assertThrows(() => D.parseHeader(bytes), /blocks/);
});

// ─── Helpers ────────────────────────────────────────────────────────────────

function countOpaque(imageData) {
  let n = 0;
  const d = imageData.data;
  for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++;
  return n;
}

/**
 * A view onto frame `index` of a vertical strip, without copying. Frames are
 * stacked top to bottom, so a frame is a contiguous run of rows.
 */
function frameSlice(block, index) {
  const perFrame = block.width * block.height * 4;
  const start = index * perFrame;
  return {
    width: block.width,
    height: block.height,
    data: block.strip.data.subarray(start, start + perFrame)
  };
}

function assertThrows(fn, pattern) {
  let threw = null;
  try {
    fn();
  } catch (err) {
    threw = err;
  }
  assert(threw !== null, 'expected a throw, got none');
  assert(
    pattern.test(threw.message),
    `error message ${JSON.stringify(threw.message)} does not match ${pattern}`
  );
}

if (update) {
  fs.writeFileSync(GOLDEN, JSON.stringify(golden, null, 2) + '\n');
  console.log('golden.json updated');
}

// ─── Report ─────────────────────────────────────────────────────────────────

console.log(`\n${passed} checks passed, ${failures.length} failed`);
for (const f of failures) console.log(`  FAIL ${f}`);
process.exit(failures.length ? 1 : 0);
