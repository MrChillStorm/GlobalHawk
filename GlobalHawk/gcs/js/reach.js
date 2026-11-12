/**
 * Glide reach without the engine: the aircraft's own planner (fdm/missionmgr.py: reach, entry), ported, so the
 * station can show at any moment what the aircraft would count on. Height in hand at a site's entry point = height
 * now - (distance / 20 + 300 ft per 90 deg of turn + the site's elevation + 2,500 ft + 1,000 ft in hand).
 */
(function (root) {
  'use strict';
  const geo = typeof module !== 'undefined' && module.exports ? require('./geo.js') : root.GCS.geo;
  const GLIDE_TAN = 0.07782;
  const GLIDE_RATIO = 20;
  const ENTRY_HEIGHT = 2500;
  const TURN_COST = 300;
  const IN_HAND = 1000;

  /** The entry point of a site { aim: [lat, lon], course, elev_ft }: on the extended centreline, 5.3 nmi out. */
  function entry(site) {
    return geo.along(site.aim, site.course + 180, ENTRY_HEIGHT / GLIDE_TAN);
  }

  /** Height left over at the site's entry point by the planner's book, ft (negative: out of reach). */
  function margin(site, here, altFt, trackDeg) {
    const c = geo.course(here, entry(site));
    const need = c.ft / GLIDE_RATIO + (TURN_COST * Math.abs(geo.turn(trackDeg, c.deg))) / 90 + site.elev_ft + ENTRY_HEIGHT + IN_HAND;
    return altFt - need;
  }

  /** How far the aircraft could glide straight ahead to an entry point at this elevation, ft. */
  function radius(altFt, elevFt) {
    return Math.max(0, (altFt - elevFt - ENTRY_HEIGHT - IN_HAND) * GLIDE_RATIO);
  }

  const api = { entry, margin, radius, GLIDE_RATIO, ENTRY_HEIGHT, IN_HAND };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).reach = api;
})(typeof window !== 'undefined' ? window : globalThis);
