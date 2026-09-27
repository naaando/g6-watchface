/**
 * Dial renderer — turns a decoded dial into watchface pixels.
 *
 * The counterpart to bin-decoder.js: given the descriptor that
 * `decodeDial` produces, this paints a 466x466 frame and reports which
 * controls that particular dial needs. No assets, no config file, no
 * per-dial special cases. Load any .bin, get a watchface.
 *
 * ─── What the firmware actually does ───────────────────────────────────────
 *
 * Blocks paint in descriptor order (Fogg/docs/DIAL_FORMAT_GUIDE.md
 * section F), which in practice is background, then gauges and digits,
 * then hour hand, minute hand, second hand, then the centre cap. A hand
 * block is not frame-selected at all — the firmware rotates the single
 * sprite around the pivot computed by `handPivot`. Everything else is a
 * vertical strip and the firmware picks one frame.
 *
 * ─── Frame selection ───────────────────────────────────────────────────────
 *
 * Which frame a strip shows depends on the block's semantics, not just
 * its frame count. See `frameForBlock` for the table; the two that are
 * easy to get wrong are the battery strip, whose six frames cover
 * uneven percentage ranges, and the four digit blocks, which split a
 * value into high and low halves.
 *
 * ─── Reuse ─────────────────────────────────────────────────────────────────
 *
 * Exported for CommonJS and as a browser global, like bin-decoder.js.
 * The rendering functions take a 2D context rather than creating one,
 * so this works against an offscreen canvas in Node (with a polyfill) or
 * the visible canvas in the page.
 */

(function (global, factory) {
  'use strict';
  var api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.G6DialRenderer = api;
  }
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  var SCREEN = 466;
  var DEG = Math.PI / 180;

  /** Base type -> semantic role. Derived from the guide's block type table. */
  var ROLE = {
    prev: 'preview',
    background: 'background',
    arm_hour: 'arm_hour',
    arm_minute: 'arm_minute',
    arm_second: 'arm_second',
    year: 'digits:year',
    month: 'digits:month',
    day: 'digits:day',
    hours: 'digits:hours',
    minutes: 'digits:minutes',
    seconds: 'digits:seconds',
    ampm: 'toggle:ampm',
    weekd: 'weekday',
    steps: 'digits:steps',
    pulse: 'digits:pulse',
    calor: 'digits:calor',
    dist: 'digits:dist',
    battery: 'digits:battery',
    connect: 'toggle:connect',
    bigyo: 'center_cap',
    animpart: 'animation',
    battery_strip: 'battery_strip',
    weather: 'weather',
    temp: 'digits:temp',
    progress2: 'progress:progress2',
    progress1: 'progress:progress1',
    label: 'label',
    hour_lo: 'digit:hour_lo',
    hour_hi: 'digit:hour_hi',
    minute_hi: 'digit:minute_hi',
    minute_lo: 'digit:minute_lo'
  };

  /**
   * The six battery-strip frames cover uneven percentage ranges. Verified
   * against the decoded 11448 artwork, which shows a gauge needle sweeping
   * across six positions.
   */
  var BATTERY_STRIP_BANDS = [5, 20, 40, 60, 80, 100];

  /**
   * Block types that read the clock and therefore need no control of their
   * own — the time state drives them.
   */
  var CLOCK_DRIVEN = {
    arm_hour: true,
    arm_minute: true,
    arm_second: true,
    'digits:hours': true,
    'digits:minutes': true,
    'digits:seconds': true,
    'digits:year': true,
    'digits:month': true,
    'digits:day': true,
    weekday: true,
    'toggle:ampm': true
  };

  /**
   * The value a role reads out of the state, given the dial's own data
   * provider. A dial can override the current time (and the 11359 dial
   * does not need to), which is what makes one real-time clock and one
   * screenshot usable for every dial.
   */
  function defaultDataProvider() {
    var now = new Date();
    return {
      date: now,
      hour: now.getHours(),
      minute: now.getMinutes(),
      second: now.getSeconds(),
      weekday: now.getDay(),
      batteryPercent: null,
      steps: null,
      pulse: null,
      calories: null,
      distanceKm: null,
      temperatureC: null,
      connected: null,
      weatherCode: null
    };
  }

  /**
   * Which frame of `block` to show for the current data.
   *
   * @param {object} block a decoded block
   * @param {object} data the object from a data provider
   * @param {{animationFrame?: number}} [extra] internal: animation cursor
   * @returns {number} frame index, clamped into range
   */
  function frameForBlock(block, data, extra) {
    var frames = block.frames;
    var role = ROLE[block.name] || '';
    var index;

    if (role === 'battery_strip') {
      // Uneven bands, not a plain percentage division.
      var pct = clampNumber(data.batteryPercent, 0, 100);
      index = 0;
      for (var b = 0; b < BATTERY_STRIP_BANDS.length; b++) {
        if (pct <= BATTERY_STRIP_BANDS[b]) {
          index = b;
          break;
        }
        index = b + 1;
      }
    } else if (role === 'progress:progress1' || role === 'progress:progress2') {
      // Eleven frames for a 0-100% arc, so frame 10 is the full ring.
      index = Math.round((clampNumber(data.batteryPercent, 0, 100) / 100) * (frames - 1));
    } else if (role === 'weekday') {
      index = clampNumber(data.weekday, 0, 6);
    } else if (role === 'toggle:ampm') {
      index = data.hour < 12 ? 0 : 1;
    } else if (role === 'toggle:connect') {
      index = data.connected ? 1 : 0;
    } else if (role === 'weather') {
      index = clampNumber(data.weatherCode, 0, frames - 1);
    } else if (role === 'animation') {
      index = (extra && extra.animationFrame) || 0;
    } else if (role.indexOf('digit:') === 0) {
      // Single-position digit blocks are named for where they sit on screen,
      // not for the value they show, so the role suffix drives the lookup.
      index = splitDigit(role.slice('digit:'.length), data);
    } else if (role.indexOf('digits:') === 0) {
      // 'digits:' is seven characters; slicing by its length is what keeps
      // this from silently looking up ':steps' and returning frame 0.
      index = valueForRole(role.slice('digits:'.length), data, block);
    } else {
      index = 0;
    }

    return clampIndex(index, frames);
  }

  /**
   * The digit a single-digit block should show. Blocks are named for the
   * position they occupy, not the value: hour_hi is the tens digit of the
   * hour, minute_lo the ones digit of the minute.
   */
  function splitDigit(name, data) {    var hour = clampNumber(data.hour, 0, 23);
    var minute = clampNumber(data.minute, 0, 59);
    switch (name) {
      case 'hour_hi':
        return Math.floor(hour / 10);
      case 'hour_lo':
        return hour % 10;
      case 'minute_hi':
        return Math.floor(minute / 10);
      case 'minute_lo':
        return minute % 10;
      default:
        return 0;
    }
  }

  /**
   * Map a `digits:<field>` role onto a number whose last digit selects the
   * frame. Two-digit fields keep only their ones digit because the guide
   * specifies ten frames, 0-9.
   */
  function valueForRole(field, data, block) {
    var value;
    switch (field) {
      case 'year':
        value = data.date instanceof Date ? data.date.getFullYear() : new Date().getFullYear();
        return value % 10;
      case 'month': {
        // Frame count decides the mapping, per the guide: twelve frames are
        // month NAMES (JAN..DEC) so the month indexes directly, ten frames
        // are DIGITS so only the ones digit is used. The 11359 dial ships a
        // 12-frame month block; the guide's 10-frame case is the fallback.
        var month = data.date instanceof Date ? data.date.getMonth() : 0;
        return block.frames >= 12 ? month : (month + 1) % 10;
      }
      case 'day':
        value = data.date instanceof Date ? data.date.getDate() : 1;
        return value % 10;
      case 'hours':
        return clampNumber(data.hour, 0, 23) % 10;
      case 'minutes':
        return clampNumber(data.minute, 0, 59) % 10;
      case 'seconds':
        return clampNumber(data.second, 0, 59) % 10;
      case 'steps':
        value = clampNumber(data.steps, 0, 99999);
        return value % 10;
      case 'pulse':
        value = clampNumber(data.pulse, 0, 999);
        return value % 10;
      case 'calor':
        value = clampNumber(data.calories, 0, 9999);
        return value % 10;
      case 'dist':
        value = clampNumber(data.distanceKm, 0, 99);
        return value % 10;
      case 'battery':
        value = clampNumber(data.batteryPercent, 0, 100);
        return value % 10;
      case 'temp':
        value = clampNumber(data.temperatureC, -50, 99);
        return value < 0 ? 0 : value % 10;
      default:
        return 0;
    }
  }

  // ─── Drawing ──────────────────────────────────────────────────────────────

  /**
   * Put one block's pixels onto the canvas.
   *
   * Strips are sliced vertically: frame `i` occupies rows
   * `i*height` through `(i+1)*height`. Reading them horizontally is the
   * single easiest mistake here — it yields artwork only in frame 0, which
   * for a battery gauge looks plausible enough to ship.
   */
  function drawBlock(ctx, block, frameIndex) {
    var source = block.canvas || block.strip;
    var sy = clampIndex(frameIndex, block.frames) * block.height;
    // The background is authored at exactly the screen size and pinned to the
    // origin, but honour the descriptor anyway in case a dial does not.
    ctx.drawImage(source, 0, sy, block.width, block.height,
      block.posx, block.posy, block.width, block.height);
    ctx.drawImage(source, 0, sy, block.width, block.height,
      block.posx, block.posy, block.width, block.height);
  }

  /**
   * Rotate one hand around its pivot and place it on the screen.
   *
   * The sprite is authored pointing at 12 o'clock, so the rotation applied is
   * the angle measured from vertical, clockwise. `handPivot` returns the
   * pivot in sprite pixels; the block's posx/posy is where that pivot lands
   * on the screen.
   *
   * @param {CanvasRenderingContext2D} ctx
   * @param {object} block an arm block
   * @param {number} degrees clockwise from 12 o'clock
   * @param {{pivot: {x: number, y: number}}} helper from bin-decoder.js
   */
  function drawHand(ctx, block, degrees, helper) {
    var pivot = helper.handPivot(block);
    var source = block.canvas || block.strip;
    ctx.save();
    ctx.translate(block.posx, block.posy);
    ctx.rotate(degrees * DEG);
    // The sprite's own pivot is not at its top-left, so back the origin out
    // to it before drawing, otherwise the hand orbits the wrong point.
    ctx.drawImage(source, 0, 0, block.width, block.height,
      -pivot.x, -pivot.y, block.width, block.height);
    ctx.restore();
  }

  /**
   * The angle an analog hand points at, in degrees clockwise from 12.
   * The second hand is continuous, the minute hand steps per minute, and the
   * hour hand moves with the minutes so it does not visibly tick over.
   */
  function handAngle(which, data) {
    var hour = clampNumber(data.hour, 0, 23) % 12;
    var minute = clampNumber(data.minute, 0, 59);
    var second = clampNumber(data.second, 0, 59);
    switch (which) {
      case 'arm_hour':
        return (hour + minute / 60) * 30;
      case 'arm_minute':
        return (minute + second / 60) * 6;
      case 'arm_second':
        return second * 6;
      default:
        return 0;
    }
  }

  /**
   * Turn each block's decoded ImageData into a canvas the 2D context can
   * draw. `decodeDial` produces ImageData because that is testable in Node;
   * canvas is not. This is the seam between the two.
   *
   * @param {object} dial from decodeDial
   * @param {(width, height) => HTMLCanvasElement} makeCanvas
   */
  function materialize(dial, makeCanvas) {
    for (var i = 0; i < dial.blocks.length; i++) {
      var block = dial.blocks[i];
      if (block.canvas) continue;
      var canvas = makeCanvas(block.strip.width, block.strip.height);
      var ctx = canvas.getContext('2d');
      ctx.putImageData(block.strip, 0, 0);
      block.canvas = canvas;
    }
    return dial;
  }

  /**
   * Paint a whole dial.
   *
   * @param {CanvasRenderingContext2D} ctx a 466x466 (or larger) 2D context
   * @param {object} dial from decodeDial
   * @param {object} data from a data provider
   * @param {{helper: object, animationFrame?: number, clear?: boolean}} [options]
   *        `helper` must be the bin-decoder module, for handPivot. Passing it
   *        in rather than reaching for a global keeps this importable.
   */
  function renderDial(ctx, dial, data, options) {
    var opts = options || {};
    var helper = opts.helper;
    if (!helper || !helper.handPivot) {
      throw new Error('renderDial needs the bin-decoder module as options.helper');
    }
    materialize(dial, opts.makeCanvas || defaultMakeCanvas);
    if (opts.clear !== false) {
      ctx.clearRect(0, 0, dial.width, dial.height);
    }
    var frameInfo = { animationFrame: opts.animationFrame || 0 };

    for (var i = 0; i < dial.blocks.length; i++) {
      var block = dial.blocks[i];
      var role = roleOf(block);
      if (role === 'preview') continue; // lives off-screen, in the watch menu

      if (role === 'arm_hour' || role === 'arm_minute' || role === 'arm_second') {
        drawHand(ctx, block, handAngle(role, data), helper);
      } else {
        drawBlock(ctx, block, frameForBlock(block, data, frameInfo));
      }
    }
  }

  /** Browser default. Throws in Node, which is why materialize takes one. */
  function defaultMakeCanvas(width, height) {
    if (typeof document === 'undefined') {
      throw new Error('no canvas available; pass options.makeCanvas');
    }
    var canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    return canvas;
  }

  /**
   * The role a block plays, or 'static' for anything unrecognised — which
   * still paints, just always on frame 0.
   */
  function roleOf(block) {
    return ROLE[block.name] || 'static';
  }

  /**
   * Report what controls this dial needs, so the UI can be built from the
   * dial instead of hand-maintained per dial. A dial with no battery strip
   * gets no battery slider; a dial with digit blocks gets a real clock.
   *
   * @param {object} dial
   * @returns {{hasClock: boolean, hasAnimation: boolean, blocks: Array}}
   */
  function describeDial(dial) {
    var blocks = dial.blocks.map(function (block) {
      var role = roleOf(block);
      return {
        name: block.name,
        role: role,
        description: block.description,
        width: block.width,
        height: block.height,
        posx: block.posx,
        posy: block.posy,
        frames: block.frames,
        colsp: block.hasAlpha ? 'RGBA' : 'RGB',
        clockDriven: isClockDriven(role),
        onScreen: isOnScreen(block)
      };
    });
    return {
      hasClock: blocks.some(function (b) { return b.clockDriven; }),
      hasAnimation: blocks.some(function (b) { return b.role === 'animation'; }),
      hasBatteryGauge: blocks.some(function (b) {
        return b.role === 'battery_strip' || b.role.indexOf('progress') === 0;
      }),
      blocks: blocks
    };
  }

  /**
   * Whether a role reads the clock. The two digit families are matched by
   * prefix: 'digit:hour_hi' and 'digits:hours' share a prefix but mean
   * different things, so only the exact roles plus the 'digit:' family are
   * listed here.
   */
  function isClockDriven(role) {
    return !!CLOCK_DRIVEN[role] || role.indexOf('digit:') === 0;
  }

  /** True when a block lies within the round 466x466 screen. */
  function isOnScreen(block) {
    if (block.name === 'prev') return false;
    // Arms are excluded: their posx/posy is the pivot at the centre, and the
    // sprite swings around it, so a top-left bounding box is meaningless.
    if (ROLE[block.name] === 'arm_hour' || ROLE[block.name] === 'arm_minute' ||
        ROLE[block.name] === 'arm_second') {
      return true;
    }
    return block.posx >= 0 && block.posy >= 0 &&
      block.posx + block.width <= SCREEN && block.posy + block.height <= SCREEN;
  }

  // ─── Small helpers ────────────────────────────────────────────────────────

  function clampIndex(index, frames) {
    if (!isFinite(index)) return 0;
    return Math.max(0, Math.min(frames - 1, Math.floor(index)));
  }

  function clampNumber(value, min, max) {
    if (typeof value !== 'number' || !isFinite(value)) return min;
    return Math.max(min, Math.min(max, value));
  }

  return {
    SCREEN: SCREEN,
    ROLE: ROLE,
    BATTERY_STRIP_BANDS: BATTERY_STRIP_BANDS,
    defaultDataProvider: defaultDataProvider,
    frameForBlock: frameForBlock,
    handAngle: handAngle,
    roleOf: roleOf,
    describeDial: describeDial,
    renderDial: renderDial,
    materialize: materialize,
    drawBlock: drawBlock,
    drawHand: drawHand,
    isOnScreen: isOnScreen
  };
});
