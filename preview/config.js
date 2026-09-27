// Watchface configuration derived from dial_desc.json
// All positions, dimensions, and rotation centers come from the BIN descriptor.

const WATCHFACE_CONFIG = {
  width: 466,
  height: 466,
  layers: {
    background: {
      // Block type from dial_desc.json. The `src` filename is free to change:
      // the preview is meant to swap art without touching the descriptor.
      block: 'BLK_BACKGROUND',
      src: 'assets/cat-background.png',
      width: 466,
      height: 466,
      posx: 0,
      posy: 0,
      ctx: 0,
      cty: 0,
      frames: 1,
      frameWidth: 466,
      frameHeight: 466
    },
    battery: {
      block: 'BLK_BATTERY_STRIP',
      src: 'assets/battery_strip.png',
      width: 110,
      height: 110,
      posx: 178,
      posy: 78,
      ctx: 0,
      cty: 0,
      frames: 6,
      frameWidth: 110,
      frameHeight: 110
    },
    steps: {
      block: 'BLK_STEPS',
      src: 'assets/steps.png',
      width: 12,
      height: 18,
      posx: 234,
      posy: 304,
      ctx: 0,
      cty: 0,
      frames: 10,
      frameWidth: 12,
      frameHeight: 18
    },
    progress: {
      block: 'BLK_PROGRESS2',
      src: 'assets/progress2.png',
      width: 110,
      height: 110,
      posx: 178,
      posy: 271,
      ctx: 0,
      cty: 0,
      frames: 11,
      frameWidth: 110,
      frameHeight: 110
    },
    hour: {
      block: 'BLK_ARM_HOUR',
      src: 'assets/arm_hour.png',
      width: 18,
      height: 132,
      posx: 233,
      posy: 233,
      ctx: 2,
      cty: 9,
      frames: 1,
      frameWidth: 18,
      frameHeight: 132
    },
    minute: {
      block: 'BLK_ARM_MINUTE',
      src: 'assets/arm_minute.png',
      width: 16,
      height: 182,
      posx: 233,
      posy: 233,
      ctx: 2,
      cty: 8,
      frames: 1,
      frameWidth: 16,
      frameHeight: 182
    },
    second: {
      block: 'BLK_ARM_SECOND',
      src: 'assets/arm_second.png',
      width: 28,
      height: 256,
      posx: 233,
      posy: 233,
      ctx: 44,
      cty: 14,
      frames: 1,
      frameWidth: 28,
      frameHeight: 256
    },
    // Decorative looping animation. Not present in dial_desc.json — this is an
    // optional block type (0x17) the firmware supports but the current dial
    // does not use. src is a vertical strip: frames stacked top to bottom.
    // ctx = 10 selects time-based looping per the format guide.
    anim: {
      block: 'BLK_ANIMPART',
      optional: true,
      src: 'assets/animpart.png',
      width: 150,
      height: 150,
      posx: 158,
      posy: 158,
      ctx: 10,
      cty: 0,
      frames: 8,
      frameWidth: 150,
      frameHeight: 150,
      frameMs: 130
    }
  }
};

// ─── Dial selection ────────────────────────────────────────────────────────
//
// Dials that share this descriptor's geometry exactly (same block types, same
// sizes, same positions, same ctx/cty) only differ in their artwork, so
// switching between them is a matter of pointing `src` at a different set of
// PNGs. Nothing about the layout changes.
//
// Select one with a query string, e.g. index.html?dial=11448
//
// A dial whose geometry differs does NOT belong here — it needs its own config
// with its own dial_desc.json, because the descriptor is what the compiler
// packs and the validator checks against.

const DIAL_ASSET_SETS = {
  'cat-gauge-analog-test': {
    label: 'cat-gauge-analog-test (current build)',
    src: {}
  },
  '11448': {
    label: '0.0_AM05_G6_11448 (stock Trek 1 dial)',
    src: {
      background: 'assets/dials/11448/background.png',
      battery: 'assets/dials/11448/battery_strip.png',
      steps: 'assets/dials/11448/steps.png',
      progress: 'assets/dials/11448/progress2.png',
      hour: 'assets/dials/11448/arm_hour.png',
      minute: 'assets/dials/11448/arm_minute.png',
      second: 'assets/dials/11448/arm_second.png'
    }
  }
};

// Pick the dial from ?dial=<id>, defaulting to the current build.
const requestedDial =
  (typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).get('dial')) ||
  'cat-gauge-analog-test';

const knownDials = Object.keys(DIAL_ASSET_SETS);
const dial = DIAL_ASSET_SETS[requestedDial];

if (dial) {
  Object.keys(dial.src).forEach(function(name) {
    if (WATCHFACE_CONFIG.layers[name]) {
      WATCHFACE_CONFIG.layers[name].src = dial.src[name];
    }
  });
  WATCHFACE_CONFIG.dial = requestedDial;
  WATCHFACE_CONFIG.dialLabel = dial.label;
} else {
  // Don't silently render a different dial than the one asked for — a typo in
  // the query string would otherwise look like it worked.
  WATCHFACE_CONFIG.dialError =
    'Unknown dial "' + requestedDial + '". Available: ' + knownDials.join(', ');
  WATCHFACE_CONFIG.dial = null;
  WATCHFACE_CONFIG.dialLabel = 'Unknown dial "' + requestedDial + '"';
  console.error(WATCHFACE_CONFIG.dialError);
}

// Expose for both classic script and module environments
if (typeof window !== 'undefined') {
  window.WATCHFACE_CONFIG = WATCHFACE_CONFIG;
  window.DIAL_ASSET_SETS = DIAL_ASSET_SETS;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { WATCHFACE_CONFIG, DIAL_ASSET_SETS };
}
