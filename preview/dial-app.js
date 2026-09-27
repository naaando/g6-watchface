/**
 * DialApp — the reusable half of the preview.
 *
 * Everything the page does, minus the markup. Give it a canvas and it will
 * load a dial from a .bin, keep a clock running, animate BLK_ANIMPART,
 * re-render on demand, and export a PNG. It builds no DOM of its own, so it
 * can be driven by index.html, embedded in another app, or run headless
 * with a fake canvas in tests.
 *
 * ─── Usage ─────────────────────────────────────────────────────────────────
 *
 *   const app = new G6DialApp({ canvas: document.querySelector('canvas') });
 *   await app.loadBinFile(file);          // from an <input type="file">
 *   app.subscribe((state) => render(state));
 *   app.startClock();
 *
 * The decoder and renderer are passed in rather than reached for as
 * globals, which is what makes this importable:
 *
 *   const app = new G6DialApp({
 *     canvas,
 *     decoder: require('./bin-decoder.js'),
 *     renderer: require('./dial-renderer.js')
 *   });
 *
 * ─── Data ──────────────────────────────────────────────────────────────────
 *
 * A dial is driven by a data object: the clock plus whatever complications
 * it actually has. `setData` accepts a partial object and merges it, so a UI
 * can nudge one value without restating the rest. Values the loaded dial has
 * no block for are kept anyway — loading a different dial later should not
 * lose the battery level the user set.
 */

(function (global, factory) {
  'use strict';
  var api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.G6DialApp = api;
  }
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  var SCREEN = 466;

  /**
   * Default frame duration for BLK_ANIMPART, in milliseconds. The block's
   * `ctx` field selects looping versus state-triggered behaviour, but not a
   * speed, so this is the preview's choice. The firmware picks its own.
   */
  var DEFAULT_FRAME_MS = 130;

  /**
   * Stand-in complication values, used until the user moves a slider.
   *
   * They have to be plausible rather than zero: a battery strip's frame 0 is
   * its *empty, red* frame, and a 0 % battery is also what a decode failure
   * looks like. Placeholder data that reads as "broken" defeats the purpose
   * of a preview.
   */
  var PLACEHOLDERS = {
    batteryPercent: 60,
    // A `digits:steps` field is three glyphs wide, so anything past 999 is
    // truncated on the left. The placeholder stays inside the field: "000"
    // from 5000 reads as a broken complication, not as a step count.
    steps: 4820,
    pulse: 72,
    calories: 400,
    distanceKm: 3,
    temperatureC: 22,
    connected: true,
    weatherCode: 0
  };

  /**
   * @param {{
   *   canvas: HTMLCanvasElement,
   *   decoder?: object,
   *   renderer?: object,
   *   frameMs?: number,
   *   realTime?: boolean
   * }} options
   */
  function DialApp(options) {
    if (!options || !options.canvas) {
      throw new Error('DialApp needs a canvas');
    }
    this.canvas = options.canvas;
    this.ctx = this.canvas.getContext('2d');
    this.decoder = options.decoder || global.G6BinDecoder;
    this.renderer = options.renderer || global.G6DialRenderer;
    if (!this.decoder || !this.renderer) {
      throw new Error('DialApp needs the decoder and renderer modules');
    }

    this.frameMs = options.frameMs || DEFAULT_FRAME_MS;
    this.listeners = [];
    this.dial = null;
    this.description = null;
    this.error = null;

    this.data = Object.assign({}, this.renderer.defaultDataProvider(), PLACEHOLDERS);
    this.realTime = options.realTime !== false;
    this.animationFrame = 0;

    this._clockTimer = null;
    this._animationTimer = null;
    this._stoppedAt = null;
  }

  // ─── Loading ──────────────────────────────────────────────────────────────

  /**
   * Decode a .bin and make it the current dial.
   *
   * @param {ArrayBuffer|Buffer|Uint8Array} buffer
   * @param {string} [name] a label for the dial, usually the filename
   * @returns {object} the block inventory, as returned by describeDial
   * @throws if the file is not a dial at all
   */
  DialApp.prototype.loadBin = function (buffer, name) {
    var dial;
    try {
      dial = this.decoder.decodeDial(buffer, { name: name || 'dial' });
    } catch (err) {
      this.error = {
        message: err && err.message ? err.message : String(err),
        offset: err ? err.offset : undefined
      };
      this.dial = null;
      this.description = null;
      this._emit();
      throw err;
    }

    if (!dial.blocks.length) {
      this.error = {
        message: 'no blocks could be decoded' +
          (dial.errors.length ? ': ' + dial.errors.map(describeError).join('; ') : '')
      };
      this.dial = null;
      this.description = null;
      this._emit();
      throw new Error(this.error.message);
    }

    // A dial with no background renders as black-on-black, which is useless.
    if (!this.decoder.findBlock(dial, 0x02)) {
      this.error = { message: 'this dial has no background image' };
      this.dial = null;
      this.description = null;
      this._emit();
      throw new Error(this.error.message);
    }

    this.dial = dial;
    this.description = this.renderer.describeDial(dial);
    this.error = null;
    this.animationFrame = 0;
    this._stoppedAt = null;

    if (this.description.hasAnimation) this.startAnimation();
    this._emit();
    return this.description;
  };

  /**
   * Read a File or Blob chosen by the user and load it. This is the entry
   * point behind an <input type="file">, so it also reports the filename and
   * the size, which is the first thing worth showing after a load.
   */
  DialApp.prototype.loadBinFile = function (file) {
    if (!file) {
      return Promise.reject(new Error('no file chosen'));
    }
    var self = this;
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        try {
          var description = self.loadBin(reader.result, file.name);
          self.source = { name: file.name, size: file.size };
          self._emit();
          resolve(description);
        } catch (err) {
          reject(err);
        }
      };
      reader.onerror = function () {
        reject(new Error('could not read ' + file.name));
      };
      reader.readAsArrayBuffer(file);
    });
  };

  // ─── State ────────────────────────────────────────────────────────────────

  /**
   * Merge new values into the data object and re-render.
   * @param {object} patch e.g. {batteryPercent: 85}
   */
  DialApp.prototype.setData = function (patch) {
    Object.assign(this.data, patch);
    this._emit();
    return this.data;
  };

  /** Read back the whole data object, or one field. */
  DialApp.prototype.getData = function (field) {
    if (field === undefined) return Object.assign({}, this.data);
    return this.data[field];
  };

  // ─── Clock ────────────────────────────────────────────────────────────────

  /**
   * Follow the real system clock, or stop following it.
   *
   * Stopping captures the current time so the dial freezes where it was
   * rather than snapping back — otherwise turning the clock off is
   * indistinguishable from a frozen frame.
   */
  DialApp.prototype.setRealTime = function (on) {
    this.realTime = !!on;
    if (this.realTime) {
      this._stoppedAt = null;
      this._syncClock();
    } else if (!this._stoppedAt) {
      this._stoppedAt = {
        hour: this.data.hour,
        minute: this.data.minute,
        second: this.data.second
      };
    }
    this._emit();
  };

  /**
   * Refresh only the wall-clock fields, leaving every complication value
   * alone. See `clockData()` in the renderer for why this is not just
   * `defaultDataProvider()`.
   */
  DialApp.prototype._syncClock = function () {
    var clock = this.renderer.clockData
      ? this.renderer.clockData()
      : this.renderer.defaultDataProvider();
    this.data = Object.assign(this.data, clock);
  };

  /** Begin ticking. Safe to call when already running. */
  DialApp.prototype.startClock = function () {
    var self = this;
    if (this._clockTimer) return;
    // Apply the current time immediately. Waiting for the first tick leaves a
    // dead second on screen at load, which reads as a bug.
    this._syncClock();
    this._clockTimer = setInterval(function () {
      if (self.realTime) {
        self._syncClock();
        self._emit();
      }
    }, 1000);
    this._emit();
  };

  /** Stop ticking. The displayed time stays where it was. */
  DialApp.prototype.stopClock = function () {
    if (this._clockTimer) {
      clearInterval(this._clockTimer);
      this._clockTimer = null;
    }
  };

  /**
   * Set the displayed clock by hand, which also turns the real-time clock
   * off. Overwriting a dragged value on the next tick is the bug this
   * prevents.
   */
  DialApp.prototype.setTime = function (hour, minute, second) {
    this.realTime = false;
    this._stoppedAt = { hour: hour, minute: minute, second: second };
    this.data.hour = hour;
    this.data.minute = minute;
    this.data.second = second;
    this._emit();
  };

  // ─── Animation ────────────────────────────────────────────────────────────

  /** Step BLK_ANIMPART, if the loaded dial has one. */
  DialApp.prototype.startAnimation = function () {
    var self = this;
    if (this._animationTimer) return;
    if (!this.description || !this.description.hasAnimation) return;
    this._animationTimer = setInterval(function () {
      var block = self.decoder.findBlock(self.dial, 0x17);
      if (!block) return;
      self.animationFrame = (self.animationFrame + 1) % block.frames;
      self._emit();
    }, this.frameMs);
  };

  DialApp.prototype.stopAnimation = function () {
    if (this._animationTimer) {
      clearInterval(this._animationTimer);
      this._animationTimer = null;
    }
  };

  /** Show one specific animation frame. Stops the timer. */
  DialApp.prototype.setAnimationFrame = function (index) {
    this.stopAnimation();
    this.animationFrame = index;
    this._emit();
  };

  // ─── Rendering ────────────────────────────────────────────────────────────

  /**
   * Paint the current state. Called automatically on every state change, so
   * a UI does not have to call it after setData or a slider move.
   */
  DialApp.prototype.render = function () {
    if (!this.dial) {
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      return;
    }
    this.renderer.renderDial(this.ctx, this.dial, this.data, {
      helper: this.decoder,
      animationFrame: this.animationFrame
    });
  };

  /**
   * Watch a dial. The callback fires on load, on any state change, and on
   * animation frames.
   * @param {function(object): void} listener receives the app
   * @returns {function(): void} an unsubscribe function
   */
  DialApp.prototype.subscribe = function (listener) {
    var self = this;
    this.listeners.push(listener);
    listener(this);
    return function () {
      var index = self.listeners.indexOf(listener);
      if (index >= 0) self.listeners.splice(index, 1);
    };
  };

  DialApp.prototype._emit = function () {
    if (this.dial) this.render();
    for (var i = 0; i < this.listeners.length; i++) {
      this.listeners[i](this);
    }
  };

  // ─── Export ───────────────────────────────────────────────────────────────

  /**
   * A PNG of the current frame, as a data URL.
   * The canvas is the screen at 1:1, so the result is a 466x466 image.
   */
  DialApp.prototype.exportPng = function () {
    return this.canvas.toDataURL('image/png');
  };

  /** Offer the current frame as a download named after the dial. */
  DialApp.prototype.downloadPng = function (filename) {
    if (typeof document === 'undefined') return null;
    var name = filename || (this.source && this.source.name ? this.source.name : 'dial') + '.png';
    var link = document.createElement('a');
    link.href = this.exportPng();
    link.download = name.replace(/\.bin$/i, '') + '.png';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    return link.download;
  };

  /** Release timers. Call when tearing the app down. */
  DialApp.prototype.destroy = function () {
    this.stopClock();
    this.stopAnimation();
    this.listeners = [];
  };

  function describeError(err) {
    var offset = err.offset === undefined ? '' : ' at offset ' + err.offset;
    return err.block + offset + ': ' + err.message;
  }

  DialApp.SCREEN = SCREEN;
  DialApp.DEFAULT_FRAME_MS = DEFAULT_FRAME_MS;
  return DialApp;
});
