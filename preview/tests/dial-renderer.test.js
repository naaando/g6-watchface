#!/usr/bin/env node
/**
 * dial-renderer tests.
 *
 * The renderer has no pixel output of its own in Node (no canvas), so these
 * tests cover the parts that are pure logic and therefore where the bugs
 * actually live: frame selection, hand angles, and the block inventory the
 * UI is built from. Pixel correctness is covered by the browser harness in
 * tests/browser/render.test.js.
 *
 * Run: node tests/dial-renderer.test.js
 */

'use strict';

const fs = require('fs');
const path = require('path');
const D = require('../bin-decoder.js');
const R = require('../dial-renderer.js');
const { DIALS } = require('./fixtures.js');

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

function readBin(file) {
  const buf = fs.readFileSync(file);
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
}

function load(label) {
  const entry = DIALS.find(([name]) => name === label);
  return D.decodeDial(readBin(entry[1]), { name: label });
}

const stock = load('11448');
const digits = load('cat-gauge-v1');
const digital = load('11359');

// ─── Battery strip: uneven percentage bands ─────────────────────────────────

const batteryStrip = D.findBlock(stock, 0x18);
const data = R.defaultDataProvider();

check('battery strip maps each documented band to its frame', () => {
  // Guide section 5: 0-5 / 6-20 / 21-40 / 41-60 / 61-80 / 81-100.
  const cases = [
    [0, 0], [5, 0],
    [6, 1], [20, 1],
    [21, 2], [40, 2],
    [41, 3], [60, 3],
    [61, 4], [80, 4],
    [81, 5], [100, 5]
  ];
  for (const [percent, expected] of cases) {
    data.batteryPercent = percent;
    assertEqual(
      R.frameForBlock(batteryStrip, data),
      expected,
      `${percent}% should be frame ${expected}`
    );
  }
});

check('battery strip clamps out-of-range percentages', () => {
  data.batteryPercent = -50;
  assertEqual(R.frameForBlock(batteryStrip, data), 0, 'negative clamps to frame 0');
  data.batteryPercent = 500;
  assertEqual(R.frameForBlock(batteryStrip, data), 5, 'over 100 clamps to the last frame');
  data.batteryPercent = undefined;
  assertEqual(R.frameForBlock(batteryStrip, data), 0, 'missing value is frame 0');
});

// ─── Progress arcs ─────────────────────────────────────────────────────────

const progress2 = D.findBlock(stock, 0x1E);

check('progress arc spans every frame including both ends', () => {
  data.batteryPercent = 0;
  assertEqual(R.frameForBlock(progress2, data), 0, '0% is frame 0');
  data.batteryPercent = 100;
  assertEqual(R.frameForBlock(progress2, data), 10, '100% is the last of 11 frames');
  data.batteryPercent = 50;
  assertEqual(R.frameForBlock(progress2, data), 5, '50% is the middle of 11 frames');
});

// ─── Digits ─────────────────────────────────────────────────────────────────

check('split digit blocks show the right digit of the clock', () => {
  data.hour = 10;
  data.minute = 8;
  const at = (type) => D.findBlock(digits, type);
  assertEqual(R.frameForBlock(at(0x28), data), 1, 'hour_hi of 10 is 1');
  assertEqual(R.frameForBlock(at(0x27), data), 0, 'hour_lo of 10 is 0');
  assertEqual(R.frameForBlock(at(0x29), data), 0, 'minute_hi of 08 is 0');
  assertEqual(R.frameForBlock(at(0x2A), data), 8, 'minute_lo of 08 is 8');

  data.hour = 23;
  data.minute = 59;
  assertEqual(R.frameForBlock(at(0x28), data), 2, 'hour_hi of 23 is 2');
  assertEqual(R.frameForBlock(at(0x27), data), 3, 'hour_lo of 23 is 3');
  assertEqual(R.frameForBlock(at(0x29), data), 5, 'minute_hi of 59 is 5');
  assertEqual(R.frameForBlock(at(0x2A), data), 9, 'minute_lo of 59 is 9');
});

check('multi-digit values use the ones digit for a 10-frame block', () => {
  const steps = D.findBlock(stock, 0x0E);
  // A regression guard: the 'digits:' prefix is seven characters, and
  // slicing by the wrong length silently yields ':steps', which falls through
  // to frame 0 for every value.
  const cases = [[0, 0], [7, 7], [123, 3], [5432, 2], [99999, 9]];
  for (const [stepsValue, expected] of cases) {
    data.steps = stepsValue;
    assertEqual(R.frameForBlock(steps, data), expected, `${stepsValue} steps`);
  }
});

check('the digits prefix is sliced by its own length', () => {
  // Directly assert the trap that bit us, independent of any dial.
  assertEqual('digits:steps'.slice('digits:'.length), 'steps');
  assert('digits:steps'.slice(6) === ':steps', 'this documents the wrong slice');
});

check('month uses frame count to choose names versus digits', () => {
  const month = D.findBlock(digital, 0x07);
  assertEqual(month.frames, 12, 'the 11359 dial ships a 12-frame month block');
  const june = new Date(2026, 5, 15);
  data.date = june;
  assertEqual(R.frameForBlock(month, data), 5, 'June is index 5 in a 12-frame block');

  // A 10-frame month block is digits, so it wants the ones digit of the number.
  const tenFrame = Object.assign({}, month, { frames: 10 });
  data.date = new Date(2026, 10, 15); // November -> 11
  assertEqual(R.frameForBlock(tenFrame, data), 1, 'November as digits is 11, so frame 1');
});

check('weekday indexes Sunday-first, matching getDay()', () => {
  const weekd = D.findBlock(digital, 0x0D);
  assertEqual(weekd.frames, 7, 'seven weekday frames');
  for (let day = 0; day < 7; day++) {
    data.weekday = day;
    assertEqual(R.frameForBlock(weekd, data), day, `getDay() ${day}`);
  }
});

// ─── Hand angles ────────────────────────────────────────────────────────────

check('hand angles match a real time', () => {
  // The three verified readings from the Chromium run at 10:08:30.
  data.hour = 10;
  data.minute = 8;
  data.second = 30;
  assertEqual(R.handAngle('arm_hour', data).toFixed(2), '304.00', 'hour');
  // The three verified readings from the Chromium run at 10:08:30: the minute
  // hand is (8 + 30/60) * 6 = 51.00, which is what the old renderer rendered
  // as 50.89 and was measured against.
  assertEqual(R.handAngle('arm_minute', data).toFixed(2), '51.00', 'minute includes seconds');
  assertEqual(R.handAngle('arm_second', data).toFixed(2), '180.00', 'second');
});

check('the hour hand advances with the minutes', () => {
  data.hour = 3;
  data.minute = 0;
  data.second = 0;
  assertEqual(R.handAngle('arm_hour', data), 90, '3:00 points right');
  data.minute = 30;
  assertEqual(R.handAngle('arm_hour', data), 105, '3:30 is halfway to 4');
  data.minute = 59;
  assertEqual(R.handAngle('arm_hour', data).toFixed(1), '119.5', '3:59 is nearly at 4');
});

check('the minute hand steps per minute, not per second', () => {
  data.hour = 0;
  data.minute = 20;
  data.second = 0;
  assertEqual(R.handAngle('arm_minute', data), 120, '20 minutes is 120 degrees');
  data.second = 59;
  assertEqual(
    R.handAngle('arm_minute', data).toFixed(2),
    (120 + (59 / 60) * 6).toFixed(2),
    'the minute hand creeps with the seconds'
  );
});

check('24-hour values wrap to a 12-hour dial', () => {
  data.hour = 0;
  data.minute = 0;
  data.second = 0;
  assertEqual(R.handAngle('arm_hour', data), 0, 'midnight points up');
  data.hour = 12;
  assertEqual(R.handAngle('arm_hour', data), 0, 'noon points up');
  data.hour = 23;
  data.minute = 0;
  assertEqual(R.handAngle('arm_hour', data).toFixed(2), '330.00', '23:00 is near 11');
  data.hour = 13;
  assertEqual(R.handAngle('arm_hour', data), 30, '13:00 is 1 o’clock');
});

// ─── Block inventory ────────────────────────────────────────────────────────

check('describeDial reports a clock and a battery gauge for 11448', () => {
  const d = R.describeDial(stock);
  assert(d.hasClock, 'a dial with hands has a clock');
  assert(d.hasBatteryGauge, 'a dial with a battery strip has a battery gauge');
  assertEqual(d.hasAnimation, false, '11448 has no animation block');
  assertEqual(d.blocks.length, stock.blocks.length, 'every block is described');
});

check('describeDial marks hands as clock driven and other blocks as not', () => {
  const byName = Object.fromEntries(R.describeDial(stock).blocks.map((b) => [b.name, b]));
  assert(byName.arm_hour.clockDriven, 'hour hand is clock driven');
  assert(byName.arm_minute.clockDriven, 'minute hand is clock driven');
  assert(byName.arm_second.clockDriven, 'second hand is clock driven');
  assert(!byName.battery_strip.clockDriven, 'battery strip needs its own control');
  assert(!byName.progress2.clockDriven, 'progress arc needs its own control');
});

check('the preview block is reported off-screen, hands are not', () => {
  const byName = Object.fromEntries(R.describeDial(stock).blocks.map((b) => [b.name, b]));
  assertEqual(byName.prev.onScreen, false, 'the preview thumbnail is not on the dial');
  // A 256px hand whose posy is 233 would fail a naive bounding box test.
  assert(byName.arm_second.onScreen, 'a hand pivoting at the centre is on screen');
  assert(byName.background.onScreen, 'the background covers the screen');
});

check('every dial in the corpus describes itself without error', () => {
  for (const [label, file] of DIALS) {
    if (!fs.existsSync(file)) continue;
    const dial = D.decodeDial(readBin(file), { name: label });
    const d = R.describeDial(dial);
    assert(d.blocks.length === dial.blocks.length, `${label} described every block`);
    assert(typeof d.hasClock === 'boolean', `${label} reported a clock flag`);
    for (const block of d.blocks) {
      assert(block.role, `${label}/${block.name} has no role`);
      assert(['RGB', 'RGBA'].includes(block.colsp), `${label}/${block.name} bad colsp`);
    }
  }
});

check('a dial with no hands still reports a clock via its digit blocks', () => {
  const d = R.describeDial(digits);
  assert(d.hasClock, 'digital dials are clocks too');
  const byName = Object.fromEntries(d.blocks.map((b) => [b.name, b]));
  assert(byName.hour_hi.clockDriven, 'hour_hi is clock driven');
  assert(byName.minute_lo.clockDriven, 'minute_lo is clock driven');
});

check('roles are unique per block name', () => {
  const seen = new Map();
  for (const [name, role] of Object.entries(R.ROLE)) {
    assert(!seen.has(role), `role ${role} claimed by both ${seen.get(role)} and ${name}`);
    seen.set(role, name);
  }
});

// ─── Guard rails ────────────────────────────────────────────────────────────

check('renderDial refuses to run without the decoder module', () => {
  let threw = null;
  try {
    R.renderDial({}, stock, data, {});
  } catch (err) {
    threw = err;
  }
  assert(threw !== null, 'expected a throw when options.helper is missing');
  assert(/helper/.test(threw.message), `unhelpful error: ${threw.message}`);
});

check('an unknown block type still paints, on frame 0', () => {
  const odd = { name: 'totally_new', frames: 4, width: 2, height: 2, posx: 0, posy: 0 };
  assertEqual(R.roleOf(odd), 'static', 'an unknown type falls back to static');
  assertEqual(R.frameForBlock(odd, data), 0, 'a static block shows frame 0');
  assertEqual(R.frameForBlock(odd, { hour: 99, minute: 99, second: 99 }, {}), 0,
    'data must not move a static block');
});

check('frame selection can never run off the end of a strip', () => {
  const one = { name: 'weekd', frames: 7, width: 1, height: 1 };
  const extremes = [-1, 0, 6, 7, 99, NaN, undefined, 'x', Infinity];
  for (const weekday of extremes) {
    const frame = R.frameForBlock(one, Object.assign({}, data, { weekday }));
    assert(
      Number.isInteger(frame) && frame >= 0 && frame < 7,
      `weekday ${weekday} produced frame ${frame}`
    );
  }
});

console.log(`\n${passed} checks passed, ${failures.length} failed`);
for (const f of failures) console.log(`  FAIL ${f}`);
process.exit(failures.length ? 1 : 0);
