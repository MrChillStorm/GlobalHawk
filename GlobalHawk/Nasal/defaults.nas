# Written by fdm/genghawk.py: do not edit. The flight model's properties that start at a value other than zero.
# Nasal/globalhawk.nas sets those that FlightGear has without a value when the flight model has loaded.
var DEFAULTS = {
    "cal/spoiler-lift": -0.5306,
    "cal/spoiler-drag": 0.03941,
    "engine/running": 1,
    "engine/master": 1,
    "cal/fuel-factor": 1,
    "cal/drag-increment": 0.00564,
    "flex/enable": 1,
    "ap/speed-cmd-kcas": 150,
    "ap/speed-schedule": 1,
    "ap/throttle-cmd": 0.5,
    "ap/gain-scale": 1,
    "ap/leg-lat1-deg": 0.01,
    "ap/spoiler-base": 0.667,
    "ap/link-timeout-sec": 30,
    "nav/kna-on": 1,
    "nav/knb-on": 1,
    "nav/lna-on": 1,
    "nav/lnb-on": 1,
};
