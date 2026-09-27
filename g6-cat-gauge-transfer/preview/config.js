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

// Expose for both classic script and module environments
if (typeof window !== 'undefined') {
  window.WATCHFACE_CONFIG = WATCHFACE_CONFIG;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { WATCHFACE_CONFIG };
}
