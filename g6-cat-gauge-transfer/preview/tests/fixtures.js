/**
 * Absolute paths to the dial BINs used by the decoder tests.
 * Kept in one place so a test run from any directory finds them.
 */
const path = require('path');
const REPO = path.resolve(__dirname, '..', '..', '..');

module.exports = {
  REPO,
  DIALS: [
    ['11448', path.join(REPO, 'trek-watchfaces/0.0_AM05_G6_11448.bin')],
    ['11359', path.join(REPO, 'trek-watchfaces/0.0_AM05_G6_11359.bin')],
    ['analog-test', path.join(REPO, 'trek-watchfaces/cat-gauge-analog-test/cat-gauge-analog-test.bin')],
    ['cat-gauge-v1', path.join(REPO, 'trek-watchfaces/cat-gauge/cat-gauge-v1.bin')],
    ['cat-gauge-v2', path.join(REPO, 'trek-watchfaces/cat-gauge-v2/cat-gauge-v2.bin')],
    ['image-test', path.join(REPO, 'trek-watchfaces/cat-gauge-image-test/cat-gauge-image-test.bin')],
    ['roundtrip-11359', path.join(REPO, 'trek-watchfaces/roundtrip_11359.bin')],
    ['roundtrip-11448', path.join(REPO, 'trek-watchfaces/roundtrip_11448.bin')]
  ]
};
