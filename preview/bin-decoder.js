/**
 * HK89 / G6 dial BIN decoder — pure JavaScript, runs in the browser and in Node.
 *
 * Reverse engineered from the Python reference implementation in
 * Fogg/comp_decomp.py (itself ported from the hk89comp_decomp binaries).
 * This file is a straight port: no rendering, no DOM, no globals. It turns an
 * ArrayBuffer into block descriptors plus one vertical frame-strip per block,
 * which is exactly the layout the firmware expects (see
 * Fogg/docs/DIAL_FORMAT_GUIDE.md section B, "Frame-Based Vertical Strips").
 *
 * ─── File layout ───────────────────────────────────────────────────────────
 *
 *   0..1   uint16le  pltable_size — number of entries in the picture table
 *   2      uint8     num_blocks
 *   3      uint8     format type (always 0x02 in every dial seen so far)
 *   4..    block descriptors, 20 bytes each, num_blocks of them
 *   ...    picture lookup table (pltable_size entries of uint32le)
 *   ...    image data, referenced by absolute offset from each block
 *
 * ─── Block descriptor (20 bytes) ───────────────────────────────────────────
 *
 *   0..3   uint32le  image_offset  absolute offset of the block's frame data
 *   4      uint8     pic_idx       index of this block's first frame in pltable
 *   5      uint8     valami2       unknown, unused
 *   6..7   uint16le  width         pixels per frame
 *   8..9   uint16le  height        pixels per frame
 *   10..11 uint16le  pos_x         left edge on the 466x466 screen
 *   12..13 uint16le  pos_y         top edge on the 466x466 screen
 *   14     uint8     parts         frame count
 *   15     uint8     block_type    low 7 bits = type, bit 7 = has alpha
 *   16     int8      align         unused
 *   17     uint8     compression   4 or 6 = RLE, otherwise raw
 *   18     int8      cent_x        hand pivot, horizontal. See NOTE below.
 *   19     int8      cent_y        hand pivot, vertical.   See NOTE below.
 *
 * NOTE on cent_x / cent_y: despite the names, cent_x is the HORIZONTAL offset
 * of the hand's pivot from the sprite's left edge (it equals width/2 for every
 * hand in every dial measured), and cent_y is the distance UP FROM THE BOTTOM
 * edge, i.e. pivotY = height - cent_y. Fogg/docs/DIAL_FORMAT_GUIDE.md section E
 * documents this; do not "fix" it back to the obvious reading.
 *
 * ─── Pixel formats ────────────────────────────────────────────────────────
 *
 *   RGB565     2 bytes, big endian, 5/6/5 bits. No alpha.
 *   RGBA5658   3 bytes: one alpha byte, then RGB565 big endian. (Despite the
 *              name it is 3 bytes per pixel, not 4 — a "5658" packing.)
 *
 * Both are widened to 8 bits per channel by replicating the high bits
 * (r5 << 3, g6 << 2, b5 << 3), which is what comp_decomp.py does and therefore
 * what the artwork in this repo was produced with.
 *
 * ─── RLE stream ───────────────────────────────────────────────────────────
 *
 * Each frame is independently compressed and starts with a uint16le
 * `skip_offset` pointing past an unused lookup table to the command stream:
 *
 *   count == 0        one literal pixel follows
 *   count & 0x80      repeat the next pixel (count & 0x7F) times
 *   otherwise         `count` literal pixels follow
 *
 * A pixel is `bpp` bytes. Frames are delimited by the per-frame sizes stored in
 * the picture lookup table, NOT by any end marker — walking past a frame's
 * real end is a bug, not a tolerance.
 */

(function (global, factory) {
  'use strict';
  var api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.G6BinDecoder = api;
  }
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  /** Screen size every dial is authored against. */
  var SCREEN_WIDTH = 466;
  var SCREEN_HEIGHT = 466;

  /** Preview thumbnail size required by BLK_PREVI. */
  var PREVIEW_SIZE = 280;

  /**
   * Base block type (bit 7 stripped) -> short name. Mirrors BLOCK_TYPE_NAMES
   * in Fogg/comp_decomp.py.
   */
  var BLOCK_TYPE_NAMES = {
    0x00: 'unknown',
    0x01: 'prev',
    0x02: 'background',
    0x03: 'arm_hour',
    0x04: 'arm_minute',
    0x05: 'arm_second',
    0x06: 'year',
    0x07: 'month',
    0x08: 'day',
    0x09: 'hours',
    0x0A: 'minutes',
    0x0B: 'seconds',
    0x0C: 'ampm',
    0x0D: 'weekd',
    0x0E: 'steps',
    0x0F: 'pulse',
    0x10: 'calor',
    0x11: 'dist',
    0x12: 'battery',
    0x13: 'connect',
    0x16: 'bigyo',
    0x17: 'animpart',
    0x18: 'battery_strip',
    0x19: 'weather',
    0x1A: 'temp',
    0x1E: 'progress2',
    0x20: 'progress1',
    // Not in Fogg's table. Inferred: a six-frame 100x100 ring sitting beside
    // the `pulse` block on a live dial, showing a segmented heart-rate ring.
    0x21: 'pulse_ring',
    0x25: 'label',
    0x27: 'hour_lo',
    0x28: 'hour_hi',
    0x29: 'minute_hi',
    0x2A: 'minute_lo'
  };

  /** Human-readable BLK_* name for a raw type byte, alpha bit included. */
  var BLOCK_TYPE_DESCRIPTIONS = {
    0x00: 'Unknown',
    0x01: 'Preview image',
    0x02: 'Background image',
    0x03: 'Arm hour',
    0x04: 'Arm minute',
    0x05: 'Arm second',
    0x06: 'Year',
    0x07: 'Month',
    0x08: 'Day',
    0x09: 'Hours',
    0x0A: 'Minutes',
    0x0B: 'Seconds',
    0x0C: 'AM/PM',
    0x0D: 'Day of week',
    0x0E: 'Steps',
    0x0F: 'Pulse/Heart rate',
    0x10: 'Calory',
    0x11: 'Distance',
    0x12: 'Battery',
    0x13: 'Connection',
    0x16: 'Axle pawl / berry',
    0x17: 'Animation',
    0x18: 'Battery strip',
    0x19: 'Weather',
    0x1A: 'Temperature',
    0x1E: 'Progress bar 2',
    0x20: 'Progress bar 1',
    0x21: 'Pulse ring (name inferred, undocumented in Fogg)',
    0x25: 'Label',
    0x27: 'Hours low digit',
    0x28: 'Hours high digit',
    0x29: 'Minutes high digit',
    0x2A: 'Minutes low digit'
  };

  /** The three analog hands, which are rotated rather than frame-selected. */
  var ARM_TYPES = { 0x03: 'arm_hour', 0x04: 'arm_minute', 0x05: 'arm_second' };

  /** Four-byte size per frame in the picture lookup table. */
  var PLTABLE_ENTRY_SIZE = 4;
  var BLOCK_DESCRIPTOR_SIZE = 20;
  var HEADER_SIZE = 4;

  /**
   * Error carrying the byte offset where parsing gave up, so a malformed file
   * produces a message a human can act on rather than "undefined is not a
   * function" forty lines later.
   */
  function DialFormatError(message, offset) {
    var err = new Error(message);
    err.name = 'DialFormatError';
    err.offset = offset;
    return err;
  }

  // ─── Byte readers ────────────────────────────────────────────────────────
  // All reads are bounds-checked and little-endian unless stated otherwise.

  function readU8(bytes, offset) {
    if (offset < 0 || offset >= bytes.length) {
      throw DialFormatError('read past end of file at ' + offset, offset);
    }
    return bytes[offset];
  }

  function readU16LE(bytes, offset) {
    if (offset < 0 || offset + 2 > bytes.length) {
      throw DialFormatError('read past end of file at ' + offset, offset);
    }
    return bytes[offset] | (bytes[offset + 1] << 8);
  }

  function readU32LE(bytes, offset) {
    if (offset < 0 || offset + 4 > bytes.length) {
      throw DialFormatError('read past end of file at ' + offset, offset);
    }
    return (
      (bytes[offset] |
        (bytes[offset + 1] << 8) |
        (bytes[offset + 2] << 16) |
        (bytes[offset + 3] << 24)) >>> 0
    );
  }

  /** int8, for the signed align/cent_x/cent_y descriptor fields. */
  function readI8(bytes, offset) {
    var v = readU8(bytes, offset);
    return v >= 128 ? v - 256 : v;
  }

  // ─── Pixel conversion ────────────────────────────────────────────────────

  /**
   * Expand one RGB565 (big endian) or RGBA5658 pixel into RGBA bytes.
   * High bits are replicated, not shifted-and-zero-filled, to match the
   * artwork pipeline that produced this repo's PNGs.
   *
   * @param {Uint8Array} bytes
   * @param {number} offset byte offset of the pixel
   * @param {number} bpp 2 for RGB565, 3 for RGBA5658
   * @param {Uint8ClampedArray} out destination, 4 bytes
   * @param {number} outOffset destination offset
   */
  function writePixel(bytes, offset, bpp, out, outOffset) {
    var hasAlpha = bpp === 3;
    var alpha = hasAlpha ? bytes[offset] : 255;
    var hi = hasAlpha ? offset + 1 : offset;
    var value = (bytes[hi] << 8) | bytes[hi + 1];
    out[outOffset] = ((value >> 11) & 0x1f) << 3;
    out[outOffset + 1] = ((value >> 5) & 0x3f) << 2;
    out[outOffset + 2] = (value & 0x1f) << 3;
    out[outOffset + 3] = alpha;
  }

  // ─── RLE ─────────────────────────────────────────────────────────────────

  /**
   * Decode one RLE-compressed frame into `out` (RGBA, width*height*4 bytes).
   *
   * @param {Uint8Array} bytes whole file
   * @param {number} start absolute offset of this frame's data
   * @param {number} end absolute offset one past this frame's data
   * @param {number} width
   * @param {number} height
   * @param {number} bpp bytes per pixel in the stream (2 or 3)
   * @param {Uint8ClampedArray} out
   * @param {number} outOffset
   * @returns {number} how many pixels were written
   */
  function decodeRleFrame(bytes, start, end, width, height, bpp, out, outOffset) {
    if (end - start < 2) return 0;

    var skipOffset = bytes[start] | (bytes[start + 1] << 8);
    var offset = start + skipOffset;
    // A skip_offset pointing outside this frame means the descriptor is wrong,
    // not that the frame is empty. Falling through would decode neighbouring
    // frames' bytes as pixels.
    if (skipOffset < 2 || offset >= end) {
      throw DialFormatError(
        'RLE skip_offset ' + skipOffset + ' is outside the frame at ' + start,
        start
      );
    }

    var total = width * height;
    var px = 0;

    while (px < total && offset < end) {
      var count = bytes[offset];
      offset += 1;

      if (count & 0x80) {
        // Repeat run: ONE pixel follows, emitted (count & 0x7F) times.
        var repeat = count & 0x7f;
        if (offset + bpp > end) break;
        var first = outOffset + px * 4;
        writePixel(bytes, offset, bpp, out, first);
        offset += bpp;
        px += 1;
        for (var r = 1; r < repeat && px < total; r++) {
          var dst = outOffset + px * 4;
          out[dst] = out[first];
          out[dst + 1] = out[first + 1];
          out[dst + 2] = out[first + 2];
          out[dst + 3] = out[first + 3];
          px += 1;
        }
      } else if (count === 0) {
        // A single literal pixel.
        if (offset + bpp > end) break;
        writePixel(bytes, offset, bpp, out, outOffset + px * 4);
        offset += bpp;
        px += 1;
      } else {
        // Literal run: `count` pixels follow, each bpp bytes.
        for (var l = 0; l < count && px < total; l++) {
          if (offset + bpp > end) break;
          writePixel(bytes, offset, bpp, out, outOffset + px * 4);
          offset += bpp;
          px += 1;
        }
      }
    }
    return px;
  }

  /**
   * Decode an uncompressed frame. Rows are padded to a 4-byte boundary.
   * Same output contract as decodeRleFrame.
   */
  function decodeRawFrame(bytes, start, end, width, height, bpp, out, outOffset) {
    var rowBytes = width * bpp;
    var alignedRowBytes = (rowBytes + 3) & ~3;
    var padding = alignedRowBytes - rowBytes;
    var offset = start;

    for (var y = 0; y < height; y++) {
      if (offset + rowBytes > end) break;
      var rowStart = outOffset + y * width * 4;
      for (var x = 0; x < width; x++) {
        writePixel(bytes, offset, bpp, out, rowStart + x * 4);
        offset += bpp;
      }
      offset += padding;
    }
  }

  // ─── Descriptors ─────────────────────────────────────────────────────────

  /**
   * Parse the 4-byte header plus every 20-byte block descriptor.
   * @param {Uint8Array} bytes
   * @returns {{pltableSize: number, format: number, blocks: Array}}
   */
  function parseHeader(bytes) {
    if (bytes.length < HEADER_SIZE) {
      throw DialFormatError('file is too small to be a dial (' + bytes.length + ' bytes)', 0);
    }

    var pltableSize = readU16LE(bytes, 0);
    var numBlocks = readU8(bytes, 2);
    var format = readU8(bytes, 3);

    var descriptorEnd = HEADER_SIZE + numBlocks * BLOCK_DESCRIPTOR_SIZE;
    if (descriptorEnd > bytes.length) {
      throw DialFormatError(
        'header claims ' + numBlocks + ' blocks, which needs ' + descriptorEnd +
          ' bytes, but the file is ' + bytes.length,
        HEADER_SIZE
      );
    }

    var blocks = [];
    for (var i = 0; i < numBlocks; i++) {
      var o = HEADER_SIZE + i * BLOCK_DESCRIPTOR_SIZE;
      var blockType = bytes[o + 15];
      var baseType = blockType & 0x7f;
      blocks.push({
        index: i,
        imageOffset: readU32LE(bytes, o),
        picIdx: readU8(bytes, o + 4),
        width: readU16LE(bytes, o + 6),
        height: readU16LE(bytes, o + 8),
        posx: readU16LE(bytes, o + 10),
        posy: readU16LE(bytes, o + 12),
        frames: readU8(bytes, o + 14),
        type: blockType,
        baseType: baseType,
        name: BLOCK_TYPE_NAMES[baseType] || ('unknown_' + baseType),
        description: BLOCK_TYPE_DESCRIPTIONS[baseType] || 'Unknown',
        hasAlpha: (blockType & 0x80) !== 0,
        compression: readU8(bytes, o + 17),
        ctx: readI8(bytes, o + 18),
        cty: readI8(bytes, o + 19)
      });
    }

    return {
      pltableSize: pltableSize,
      pltableOffset: descriptorEnd,
      format: format,
      blocks: blocks
    };
  }

  /**
   * Read `count` consecutive uint32le frame sizes from the picture lookup
   * table, starting at entry `picIdx`.
   */
  function readFrameSizes(bytes, pltableOffset, picIdx, count) {
    var sizes = [];
    for (var i = 0; i < count; i++) {
      var o = pltableOffset + (picIdx + i) * PLTABLE_ENTRY_SIZE;
      sizes.push(readU32LE(bytes, o));
    }
    return sizes;
  }

  // ─── Public API ──────────────────────────────────────────────────────────

  /**
   * Decode a whole dial.
   *
   * Every block becomes a vertical frame strip: an ImageData of
   * `width` x (`height` * `frames`), frames stacked top to bottom, which is the
   * on-disk asset layout. `dialRenderer` slices it back out per frame.
   *
   * Blocks that fail to decode are recorded in `dial.errors` rather than
   * aborting: one corrupt indicator should not cost you the whole watchface.
   * A dial with no usable background is the exception, since without it there
   * is nothing to look at.
   *
   * @param {ArrayBuffer|Uint8Array} buffer
   * @param {{name?: string, makeImageData?: function(width, height): ImageData}} [options]
   * @returns {object} dial descriptor — see README for the shape
   */
  function decodeDial(buffer, options) {
    var opts = options || {};
    var bytes = buffer instanceof Uint8Array
      ? buffer
      : new Uint8Array(buffer);

    var header = parseHeader(bytes);
    var makeImageData = opts.makeImageData || defaultMakeImageData;

    var dial = {
      name: opts.name || 'dial',
      width: SCREEN_WIDTH,
      height: SCREEN_HEIGHT,
      format: header.format,
      pltableSize: header.pltableSize,
      blocks: [],
      errors: []
    };

    for (var i = 0; i < header.blocks.length; i++) {
      var block = header.blocks[i];
      try {
        decodeBlock(bytes, header.pltableOffset, block, makeImageData, dial);
        dial.blocks.push(block);
      } catch (err) {
        dial.errors.push({
          block: block.name,
          type: block.type,
          message: err && err.message ? err.message : String(err)
        });
      }
    }

    return dial;
  }

  /**
   * Decode one block's frames into `block.strip` (a vertical ImageData) and
   * `block.frameIndexes` (byte offsets of each frame inside that strip, so the
   * renderer can read a single frame without re-slicing).
   */
  function decodeBlock(bytes, pltableOffset, block, makeImageData, dial) {
    if (block.frames < 1) {
      throw DialFormatError('block ' + block.name + ' declares ' + block.frames + ' frames', block.index);
    }
    if (block.width < 1 || block.height < 1) {
      throw DialFormatError('block ' + block.name + ' has zero size ' + block.width + 'x' + block.height, block.index);
    }
    if (block.imageOffset === 0 || block.imageOffset >= bytes.length) {
      throw DialFormatError(
        'block ' + block.name + ' has image offset ' + block.imageOffset +
          ' outside the ' + bytes.length + '-byte file',
        block.index
      );
    }

    var frameSizes = readFrameSizes(bytes, pltableOffset, block.picIdx, block.frames);
    var stripHeight = block.height * block.frames;
    var strip = makeImageData(block.width, stripHeight);
    var out = strip.data;
    var bpp = block.hasAlpha ? 3 : 2;
    var isRle = block.compression === 4 || block.compression === 6;

    // Frames are stored back to back starting at imageOffset, each exactly as
    // long as its pltable entry says. The frame DATA region is imageOffset +
    // pltableSize*4; anything before that is the lookup table itself.
    var cursor = block.imageOffset;
    for (var f = 0; f < block.frames; f++) {
      var size = frameSizes[f];
      var start = cursor;
      var end = cursor + size;
      if (end > bytes.length) {
        throw DialFormatError(
          'block ' + block.name + ' frame ' + f + ' runs to ' + end +
            ', past the ' + bytes.length + '-byte file',
          start
        );
      }
      var dst = f * block.height * block.width * 4;
      if (isRle) {
        decodeRleFrame(bytes, start, end, block.width, block.height, bpp, out, dst);
      } else {
        decodeRawFrame(bytes, start, end, block.width, block.height, bpp, out, dst);
      }
      cursor = end;
    }

    block.strip = strip;
    // Same shape dial_desc.json uses, so the existing validator and any tooling
    // that reads a descriptor keeps working against a decoded dial.
    block.desc = {
      type: 'BLK_' + block.name.toUpperCase(),
      frms: block.frames,
      colsp: block.hasAlpha ? 'RGBA' : 'RGB',
      width: block.width,
      height: block.height,
      posx: block.posx,
      posy: block.posy,
      ctx: block.ctx,
      cty: block.cty
    };
  }

  /** Node fallback so the decoder is testable outside a browser. */
  function defaultMakeImageData(width, height) {
    if (typeof ImageData === 'function') {
      return new ImageData(width, height);
    }
    return { width: width, height: height, data: new Uint8ClampedArray(width * height * 4) };
  }

  /**
   * Look up the first block with the given base type, or null.
   * @param {object} dial
   * @param {number} baseType
   */
  function findBlock(dial, baseType) {
    for (var i = 0; i < dial.blocks.length; i++) {
      if (dial.blocks[i].baseType === baseType) return dial.blocks[i];
    }
    return null;
  }

  /**
   * The hand rotation pivot in sprite pixel coordinates.
   * See the NOTE at the top of this file: ctx is measured from the bottom.
   * @param {object} block an arm block
   * @returns {{x: number, y: number}}
   */
  function handPivot(block) {
    return { x: block.cty, y: block.height - block.ctx };
  }

  return {
    SCREEN_WIDTH: SCREEN_WIDTH,
    SCREEN_HEIGHT: SCREEN_HEIGHT,
    PREVIEW_SIZE: PREVIEW_SIZE,
    BLOCK_TYPE_NAMES: BLOCK_TYPE_NAMES,
    BLOCK_TYPE_DESCRIPTIONS: BLOCK_TYPE_DESCRIPTIONS,
    ARM_TYPES: ARM_TYPES,
    decodeDial: decodeDial,
    parseHeader: parseHeader,
    readFrameSizes: readFrameSizes,
    decodeRleFrame: decodeRleFrame,
    decodeRawFrame: decodeRawFrame,
    findBlock: findBlock,
    handPivot: handPivot
  };
});
