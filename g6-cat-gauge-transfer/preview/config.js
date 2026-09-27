// Watchface configuration derived from dial_desc.json
// All positions, dimensions, and rotation centers come from the BIN descriptor.

const WATCHFACE_CONFIG = {
  width: 466,
  height: 466,
  layers: {
    background: {
      src: 'assets/background.png',
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
