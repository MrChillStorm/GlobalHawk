/**
 * Terrain against the aircraft's height, from Terrarium elevation tiles (Mapzen / AWS open terrain data): ground within NEAR_FT
 * below the aircraft is lighter, ground at or above it darker. Elevation in a tile pixel is (R × 256 + G + B / 256) − 32768 metres.
 * Nothing here knows about obstacles or the aircraft's glide: it is the ground, against one height.
 */
(function (root) {
  'use strict';
  const NEAR_FT = 500;
  const FT_PER_M = 3.28084;
  const URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';

  const elevationM = (r, g, b) => r * 256 + g + b / 256 - 32768;

  /** 2: the ground is at or above the height; 1: within NEAR_FT below it; 0: clear. Sea level (0 m and below) is never terrain. */
  function classify(alt_ft, elev_m) {
    if (elev_m <= 0) return 0;
    const d = alt_ft - elev_m * FT_PER_M;
    return d <= 0 ? 2 : d < NEAR_FT ? 1 : 0;
  }

  /** RGBA of an elevation tile (Uint8ClampedArray, 256 × 256) into the shading for a height, written into out. Returns the count of pixels in each class. */
  function shade(rgba, alt_ft, out) {
    const n = { 0: 0, 1: 0, 2: 0 };
    for (let i = 0; i < rgba.length; i += 4) {
      const c = classify(alt_ft, elevationM(rgba[i], rgba[i + 1], rgba[i + 2]));
      n[c]++;
      if (c === 2) {
        out[i] = 122; out[i + 1] = 30; out[i + 2] = 30; out[i + 3] = 150;
      } else if (c === 1) {
        out[i] = 200; out[i + 1] = 110; out[i + 2] = 50; out[i + 3] = 120;
      } else {
        out[i] = out[i + 1] = out[i + 2] = out[i + 3] = 0;
      }
    }
    return n;
  }

  const urlFor = (z, x, y) => URL.replace('{z}', z).replace('{x}', x).replace('{y}', y);

  const api = { NEAR_FT, elevationM, classify, shade, urlFor };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).terrain = api;
})(typeof window !== 'undefined' ? window : globalThis);
