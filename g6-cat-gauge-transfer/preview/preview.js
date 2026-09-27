/**
 * G6 Watchface Canvas Compositor
 * Composes watchface layers onto a 466x466 canvas.
 * All positions and dimensions come from WATCHFACE_CONFIG.
 */
(function(global) {
  'use strict';

  const CONFIG = global.WATCHFACE_CONFIG;

  if (!CONFIG) {
    console.error('WATCHFACE_CONFIG not found — config.js must be loaded first');
    return;
  }

  /**
   * Load an image from a source URL.
   * @param {string} src - Image source path
   * * @returns {Promise<HTMLImageElement>}
   */
  function loadImage(src) {
    return new Promise(function(resolve, reject) {
      const img = new Image();
      img.onload = function() { resolve(img); };
      img.onerror = function() {
        reject(new Error('Failed to load image: ' + src));
      };
      img.src = src;
    });
  }

  /**
   * Draw a single frame from a sprite sheet.
   * @param {CanvasRenderingContext2D} ctx
   * @param {HTMLImageElement} image - Sprite sheet image
   * @param {object} block - Layer config block
   * @param {number} frameIndex - Frame index to draw
   */
  function drawSpriteFrame(ctx, image, block, frameIndex) {
    const fw = block.frameWidth;
    const fh = block.frameHeight;
    const sx = frameIndex * fw;
    const sy = 0;
    ctx.drawImage(image, sx, sy, fw, fh, block.posx, block.posy, block.width, block.height);
  }

  /**
   * Draw a single frame from a VERTICAL strip.
   *
   * BLK_ANIMPART assets are packed as a vertical strip (one frame per
   * `frameHeight` row band) by make-anim-strip.py, which mirrors what the
   * firmware's Animation Slicer produces. Indicator blocks like battery and
   * steps use horizontal strips instead — see drawSpriteFrame.
   *
   * @param {CanvasRenderingContext2D} ctx
   * @param {HTMLImageElement} image - Vertical strip image
   * @param {object} block - Layer config block
   * @param {number} frameIndex - Frame index to draw
   */
  function drawAnimFrame(ctx, image, block, frameIndex) {
    const fw = block.frameWidth;
    const fh = block.frameHeight;
    const sx = 0;
    const sy = frameIndex * fh;
    ctx.drawImage(image, sx, sy, fw, fh, block.posx, block.posy, block.width, block.height);
  }

  /**
   * Draw the BLK_ANIMPART looping animation, if the layer is enabled.
   * @param {CanvasRenderingContext2D} ctx
   * @param {object} images - Map of loaded images
   * @param {number} frameIndex - Current animation frame
   * @param {boolean} enabled
   */
  function drawAnimation(ctx, images, frameIndex, enabled) {
    if (!enabled) return;
    const anim = CONFIG.layers.anim;
    if (!anim || !images.anim) return;
    const idx = ((frameIndex % anim.frames) + anim.frames) % anim.frames;
    drawAnimFrame(ctx, images.anim, anim, idx);
  }

  /**
   * Draw static layers: background and indicators (battery, steps, progress).
   * @param {CanvasRenderingContext2D} ctx
   * @param {object} images - Map of loaded images
   * @param {object} state - Watchface state
   */
  function drawStaticLayers(ctx, images, state) {
    // Background
    const bg = CONFIG.layers.background;
    if (images.background) {
      ctx.drawImage(images.background, bg.posx, bg.posy, bg.width, bg.height);
    }

    // Battery indicator (6 frames: 0-5)
    const battery = CONFIG.layers.battery;
    if (images.battery && state.battery !== undefined && state.battery !== null) {
      const batteryIdx = Math.max(0, Math.min(state.battery, battery.frames - 1));
      drawSpriteFrame(ctx, images.battery, battery, batteryIdx);
    }

    // Steps indicator (10 frames: 0-9)
    const steps = CONFIG.layers.steps;
    if (images.steps && state.steps !== undefined && state.steps !== null) {
      const stepsIdx = Math.max(0, Math.min(state.steps, steps.frames - 1));
      drawSpriteFrame(ctx, images.steps, steps, stepsIdx);
    }

    // Progress indicator (11 frames: 0-10)
    const progress = CONFIG.layers.progress;
    if (images.progress && state.progress !== undefined && state.progress !== null) {
      const progressIdx = Math.max(0, Math.min(state.progress, progress.frames - 1));
      drawSpriteFrame(ctx, images.progress, progress, progressIdx);
    }
  }

  /**
   * Resolve the pixel-space rotation pivot of an arm sprite.
   *
   * The `ctx` / `cty` fields in dial_desc.json do NOT mean what their names
   * suggest, and the prose in DIAL_FORMAT_GUIDE.md section E is wrong about
   * them. Verified against the extracted sprites of this dial:
   *
   *   block             width  height  ctx  cty   -> real pivot (x, y)
   *   BLK_ARM_HOUR        18    132     2    9      (9, 130)   cty = 18/2
   *   BLK_ARM_MINUTE      16    182     2    8      (8, 180)   cty = 16/2
   *   BLK_ARM_SECOND      28    256    44   14      (14, 212)  cty = 28/2
   *
   * So: `cty` is the horizontal center of the sprite, and `ctx` is the
   * distance from the BOTTOM edge to the pivot (i.e. pivot Y = height - ctx).
   *
   * Cross-checked against the pixel data: the second hand's visible hub spans
   * rows 198..220 (center 209) and the computed pivot is y=212; its long tip
   * runs up to y=35 with a 40px tail below the pivot. The hour and minute
   * sprites are fully opaque above their computed pivots (y 0..129 and
   * y 1..179), meaning they point straight up at angle 0.
   *
   * @param {object} block - Layer config block with width, height, ctx, cty
   * @returns {{x: number, y: number}} Pivot in image pixel coordinates
   */
  function getHandPivot(block) {
    return {
      x: block.cty,
      y: block.height - block.ctx
    };
  }

  /**
   * Draw a hand (hour, minute, or second) at the correct center with rotation.
   * @param {CanvasRenderingContext2D} ctx
   * @param {HTMLImageElement} image - Hand sprite image
   * @param {object} block - Layer config block with posx, posy, ctx, cty
   * @param {number} angle - Rotation angle in degrees (clockwise, 0 = 12 o'clock)
   */
  function drawHand(ctx, image, block, angle) {
    const pivot = getHandPivot(block);
    ctx.save();
    ctx.translate(block.posx, block.posy);
    ctx.rotate(angle * Math.PI / 180);
    // Offset the sprite so its pivot lands on the origin, which now sits at
    // posx/posy (the screen center for all three hands).
    ctx.drawImage(image, -pivot.x, -pivot.y);
    ctx.restore();
  }

  /**
   * Render a complete watchface frame.
   * @param {CanvasRenderingContext2D} ctx
   * @param {object} images - Map of loaded images keyed by layer name
   * @param {object} state - { hour, minute, second, battery, steps, progress }
   */
  function renderWatchface(ctx, images, state) {
    const w = CONFIG.width;
    const h = CONFIG.height;

    // Clear canvas
    ctx.clearRect(0, 0, w, h);

    // Draw static layers first (background + indicators)
    drawStaticLayers(ctx, images, state);

    // Calculate hand angles (clockwise, 0 = 12 o'clock)
    const hourAngle = ((state.hour % 12) * 30) + (state.minute * 0.5);
    const minuteAngle = (state.minute * 6) + (state.second * 0.1);
    const secondAngle = state.second * 6;

    // Draw hands in order: hour, minute, second
    const hourBlock = CONFIG.layers.hour;
    if (images.hour) {
      drawHand(ctx, images.hour, hourBlock, hourAngle);
    }

    const minuteBlock = CONFIG.layers.minute;
    if (images.minute) {
      drawHand(ctx, images.minute, minuteBlock, minuteAngle);
    }

    const secondBlock = CONFIG.layers.second;
    if (images.second) {
      drawHand(ctx, images.second, secondBlock, secondAngle);
    }

    // BLK_ANIMPART looping animation (optional block, decorative)
    drawAnimation(
      ctx,
      images,
      state.animFrame || 0,
      state.animEnabled !== false
    );

    // Digital concept overlay (simulated — not part of the actual BIN)
    if (state.digitalMode) {
      drawDigitalConcept(ctx, state);
    }
  }

  // ─── State Management ───────────────────────────────────────────────────────

  let _state = createDefaultState();
  let _renderCallback = null;
  let _clockTimerId = null;

  /**
   * Create a fresh default watchface state.
   * @returns {{hour: number, minute: number, second: number, battery: number, steps: number, progress: number, digitalMode: boolean}}
   */
  function createDefaultState() {
    return {
      hour: 10,
      minute: 8,
      second: 30,
      battery: 4,
      steps: 5,
      progress: 6,
      digitalMode: false,
      animFrame: 0,
      // Off by default: the current background is a still image, so the
      // BLK_ANIMPART overlay would just sit on top of it. Tick the
      // "Animation" checkbox to enable it.
      animEnabled: false
    };
  }

  /**
   * Get a shallow copy of the current state.
   * @returns {object}
   */
  function getState() {
    return Object.assign({}, _state);
  }

  /**
   * Merge partial state into current state and trigger re-render.
   * @param {object} partial
   */
  function setState(partial) {
    Object.assign(_state, partial);
    if (_renderCallback) {
      _renderCallback(_state);
    }
  }

  /**
   * Register a callback that fires whenever state changes.
   * @param {function(object): void} cb
   */
  function setRenderCallback(cb) {
    _renderCallback = cb;
  }

  /**
   * Start a real-time clock that updates state from local time every second.
   * @returns {number} Timer ID
   */
  function startClock() {
    stopClock();
    _clockTimerId = setInterval(function() {
      const now = new Date();
      setState({
        hour: now.getHours(),
        minute: now.getMinutes(),
        second: now.getSeconds()
      });
    }, 1000);
    return _clockTimerId;
  }

  /**
   * Stop the real-time clock timer.
   */
  function stopClock() {
    if (_clockTimerId !== null) {
      clearInterval(_clockTimerId);
      _clockTimerId = null;
    }
  }

  // ─── Animation Loop ────────────────────────────────────────────────────────

  let _animTimerId = null;

  /**
   * Start the BLK_ANIMPART playback loop.
   * Frame timing comes from the layer's `frameMs` (100ms = 10fps).
   * @returns {number} Timer ID
   */
  function startAnimation() {
    stopAnimation();
    const anim = CONFIG.layers.anim;
    if (!anim) return null;
    const ms = anim.frameMs || 100;
    _animTimerId = setInterval(function() {
      setState({ animFrame: (_state.animFrame + 1) % anim.frames });
    }, ms);
    return _animTimerId;
  }

  /**
   * Stop the animation playback loop.
   */
  function stopAnimation() {
    if (_animTimerId !== null) {
      clearInterval(_animTimerId);
      _animTimerId = null;
    }
  }

  // ─── Digital Concept Overlay ───────────────────────────────────────────────

  /**
   * Draw a simulated digital time overlay.
   * This is a conceptual preview of a digital layer — NOT part of the actual BIN.
   * @param {CanvasRenderingContext2D} ctx
   * @param {object} state - Watchface state
   */
  function drawDigitalConcept(ctx, state) {
    const w = CONFIG.width;
    const h = CONFIG.height;

    // Semi-transparent background for the digital overlay
    ctx.save();
    ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    ctx.fillRect(0, 0, w, h);

    // Digital time text
    const timeStr = String(state.hour).padStart(2, '0') + ':' +
                    String(state.minute).padStart(2, '0');

    ctx.fillStyle = '#00ff88';
    ctx.font = 'bold 80px monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(timeStr, w / 2, h / 2 - 30);

    // Seconds
    ctx.fillStyle = '#00cc66';
    ctx.font = 'bold 40px monospace';
    ctx.fillText(String(state.second).padStart(2, '0'), w / 2, h / 2 + 40);

    // Clear "CONCEPT" label
    ctx.fillStyle = '#ffaa00';
    ctx.font = 'bold 14px sans-serif';
    ctx.fillText('DIGITAL CONCEPT — SIMULATED', w / 2, h / 2 + 90);

    ctx.restore();
  }

  /**
   * Toggle the digital concept overlay.
   * @param {boolean} enabled
   */
  function toggleDigitalConcept(enabled) {
    setState({ digitalMode: enabled });
  }

  /**
   * Toggle the reference image display.
   * @param {boolean} enabled
   */
  function toggleReference(enabled) {
    const refContainer = document.getElementById('reference-container');
    if (refContainer) {
      refContainer.style.display = enabled ? 'flex' : 'none';
    }
  }

  /**
   * Export the current canvas as a PNG download.
   * @returns {HTMLAnchorElement} Anchor element with blob: href
   */
  function exportPng() {
    const canvas = document.getElementById('watchface-canvas');
    if (!canvas) {
      throw new Error('Canvas element #watchface-canvas not found');
    }

    // Convert canvas to blob
    const dataUrl = canvas.toDataURL('image/png');
    const blob = dataURLToBlob(dataUrl);
    const blobUrl = URL.createObjectURL(blob);

    // Create and return anchor element
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = 'g6-watchface-preview.png';
    return link;
  }

  /**
   * Convert a data URL to a Blob.
   * @param {string} dataUrl
   * @returns {Blob}
   */
  function dataURLToBlob(dataUrl) {
    const parts = dataUrl.split(',');
    const mime = parts[0].match(/:(.*?);/)[1];
    const binary = atob(parts[1]);
    const array = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      array[i] = binary.charCodeAt(i);
    }
    return new Blob([array], { type: mime });
  }

  // Expose all functions globally for classic script usage
  global.loadImage = loadImage;
  global.drawStaticLayers = drawStaticLayers;
  global.drawHand = drawHand;
  global.getHandPivot = getHandPivot;
  global.renderWatchface = renderWatchface;
  global.createDefaultState = createDefaultState;
  global.getState = getState;
  global.setState = setState;
  global.setRenderCallback = setRenderCallback;
  global.startClock = startClock;
  global.stopClock = stopClock;
  global.startAnimation = startAnimation;
  global.stopAnimation = stopAnimation;
  global.drawAnimFrame = drawAnimFrame;
  global.drawAnimation = drawAnimation;
  global.drawDigitalConcept = drawDigitalConcept;
  global.toggleDigitalConcept = toggleDigitalConcept;
  global.toggleReference = toggleReference;
  global.exportPng = exportPng;

  // Also export for module environments
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      loadImage, drawStaticLayers, drawHand, getHandPivot, renderWatchface,
      createDefaultState, getState, setState, setRenderCallback,
      startClock, stopClock,
      startAnimation, stopAnimation, drawAnimFrame, drawAnimation,
      drawDigitalConcept, toggleDigitalConcept, toggleReference, exportPng
    };
  }

})(typeof window !== 'undefined' ? window : this);
