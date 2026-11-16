#!/usr/bin/env python3
"""A stand-in for FlightGear for the ground control station: the JSBSim model with the flight laws, the mission
manager and the aircraft's end of the command link, behind FlightGear's own web protocol.

    python3 fdm/gcs_server.py [--port 5400] [--speed 1] [--plan GlobalHawk/Missions/demo-local.json]

Then open http://localhost:5400/gcs/ (the server also hands out the station's files), or open
GlobalHawk/gcs/index.html yourself and point it at this host and port.

What it speaks, as `fgfs --httpd=5400` does:
    GET  /json/<path>               {"path","name","value","type"}
    POST /json/<path>  {"value":v}  sets it
    ws   /PropertyListener          {"command":"addListener"|"get"|"set","node":path[,"value":v]}; pushes on change
Properties: /gcs/* (the link), /fdm/jsbsim/* (the flight model), and the few of FlightGear's own that the station
reads (/position, /orientation, /velocities, /sim/time/elapsed-sec).

The aircraft starts on its stand at the plan's field, engine running, waiting for a plan and a start. --plan only
says where that stand is: the plan itself comes up the link from the station.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import math
import mimetypes
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H                 # noqa: E402
import onboard as OB
import airportdata as AD                # noqa: E402

GCS_DIR = os.path.join(HERE, '..', 'GlobalHawk', 'gcs')
FG = {   # FlightGear's own properties, from the flight model's
    '/position/latitude-deg': 'position/lat-geod-deg', '/position/longitude-deg': 'position/long-gc-deg',
    '/position/altitude-ft': 'position/h-sl-ft', '/position/altitude-agl-ft': 'position/h-agl-ft',
    '/orientation/heading-deg': 'attitude/psi-deg', '/orientation/pitch-deg': 'attitude/theta-deg', '/orientation/roll-deg': 'attitude/phi-deg',
    '/velocities/airspeed-kt': 'velocities/vc-kts', '/velocities/groundspeed-kt': 'ap/ground-speed-kt',
    '/velocities/vertical-speed-fps': 'velocities/h-dot-fps', '/velocities/mach': 'velocities/mach',
    '/sim/time/elapsed-sec': 'simulation/sim-time-sec',
}


class Sim:
    """The aircraft: the flight model, the laws and the on-board end of the link. step() runs one frame."""

    def __init__(self, plan_path=None, weight=25600.0, scenery=None):
        self.f = H.load()
        fld = dict(lat=34.9, lon=-117.88, elev_ft=2300.0, stand=None, stand_heading=0.0)
        if plan_path:
            fld.update(json.load(open(plan_path))['field'])
        lat, lon = fld.get('stand') or (fld['lat'], fld['lon'])
        H.on_ground(self.f, weight, elevation=fld['elev_ft'], heading=fld.get('stand_heading', 0.0), lat=lat, lon=lon)
        self.f['limits/reset'] = 1
        self.f.run()
        self.f['limits/reset'] = 0
        self.ob = OB.Onboard(self.f, scenery=scenery)
        self.extra = {}                          # properties a client set that nothing else owns
        self.ok = True

    def step(self):
        self.ob.step()
        self.ok = bool(self.f.run())
        return self.ok

    def get(self, path):
        """A property's value, or None if there is no such property."""
        if path in self.ob.down:
            return self.ob.down[path]
        if path in FG:
            return self.f[FG[path]]
        if path.startswith('/fdm/jsbsim/'):
            name = path[len('/fdm/jsbsim/'):]
            if self.f.get_property_manager().hasNode(name):
                return self.f[name]
            return None
        return self.extra.get(path)

    def set(self, path, value):
        if path.startswith('/gcs/up/'):
            self.extra[path] = value
            self.ob.uplink(path, value)
        elif path.startswith('/fdm/jsbsim/'):
            name = path[len('/fdm/jsbsim/'):]
            if self.f.get_property_manager().hasNode(name):
                self.f[name] = float(value)
        elif path not in FG and not path.startswith('/gcs/down/'):
            self.extra[path] = value


def traffic(t, lat0=34.9, lon0=-117.88):
    """Two aircraft made up for the station's traffic display, as FlightGear's /ai/models tree gives them.
    One flies up and down a line that crosses the demo plan's first leg at 20,000 ft; one passes high and far."""
    def leafs(d):
        return [dict(name=k, children=leafs(v)) if isinstance(v, dict) else dict(name=k, value=v, type='double') for k, v in d.items()]

    def model(i, callsign, lat, lon, alt, hdg, kt, vs=0.0):
        return dict(path='/ai/models/aircraft[%d]' % i, name='aircraft', index=i, type='none', children=leafs({
            'callsign': callsign, 'valid': True, 'position': {'latitude-deg': lat, 'longitude-deg': lon, 'altitude-ft': alt},
            'orientation': {'true-heading-deg': hdg}, 'velocities': {'true-airspeed-kt': kt, 'vertical-speed-fps': vs}}))
    # a shuttle: 40 nmi each way at 240 kt along 130/310 deg through a point 18 nmi up the first leg
    leg, period = 40.0, 2 * 40.0 / 240.0 * 3600.0
    ph = (t % period) / period
    s, hdg = (ph * 2 * leg - leg / 2, 130.0) if ph < 0.5 else ((1 - ph) * 2 * leg - leg / 2, 310.0)
    cx, cy = lat0 + 18 / 60.0 * math.cos(math.radians(40)), lon0 + 18 / 60.0 * math.sin(math.radians(40)) / math.cos(math.radians(lat0))
    a = (cx + s / 60.0 * math.cos(math.radians(130)), cy + s / 60.0 * math.sin(math.radians(130)) / math.cos(math.radians(lat0)))
    b = (lat0 + 0.9, lon0 - 1.2 + (t * 420.0 / 3600.0) / 60.0 / math.cos(math.radians(lat0)))
    return dict(path='/ai/models', name='models', index=0, type='none', children=[
        model(0, 'SHUTTLE1', a[0], a[1], 20000.0, hdg, 240.0), model(1, 'HIGH22', b[0], b[1], 36000.0, 90.0, 420.0),
        dict(name='count', value=2, type='int')])


def node(path, value):
    return dict(path=path, name=path.rsplit('/', 1)[-1], value=value, type='string' if isinstance(value, str) else 'double', index=0)


# ---- a small websocket (RFC 6455: text frames, ping, close) on asyncio streams: the standard library has none
async def ws_read(reader):
    """One message: (opcode, bytes), or None when the peer has gone."""
    try:
        data = b''
        while True:
            b0, b1 = await reader.readexactly(2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack('>H', await reader.readexactly(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', await reader.readexactly(8))[0]
            mask = await reader.readexactly(4) if b1 & 0x80 else None
            chunk = await reader.readexactly(n)
            if mask:
                chunk = bytes(c ^ mask[i % 4] for i, c in enumerate(chunk))
            data += chunk
            if b0 & 0x80:
                return b0 & 0x0F, data
    except (asyncio.IncompleteReadError, ConnectionError):
        return None


def ws_frame(payload, opcode=1):
    n = len(payload)
    head = bytes([0x80 | opcode]) + (bytes([n]) if n < 126 else bytes([126]) + struct.pack('>H', n) if n < 65536 else bytes([127]) + struct.pack('>Q', n))
    return head + payload


class Server:
    def __init__(self, sim, speed=1.0):
        self.sim, self.speed = sim, speed
        self.clients = []                        # each: dict(writer, paths, last)

    async def run_sim(self):
        """The flight model in step with the clock, `speed` times as fast."""
        owed, last = 0.0, time.monotonic()
        while self.sim.ok:
            now = time.monotonic()
            owed += (now - last) * self.speed * H.HZ
            last = now
            n = min(int(owed), int(0.25 * self.speed * H.HZ) + 1)      # never more than a quarter second's worth at once
            owed -= int(owed)
            for _ in range(n):
                if not self.sim.step():
                    break
            self.push()
            await asyncio.sleep(0.02)

    def push(self):
        for c in self.clients:
            out = []
            for p in c['paths']:
                v = self.sim.get(p)
                if v is not None and c['last'].get(p) != v:
                    c['last'][p] = v
                    out.append(node(p, v))
            for m in out:
                c['writer'].write(ws_frame(json.dumps(m).encode()))

    async def handle(self, reader, writer):
        try:
            line = await reader.readline()
            if not line:
                return
            method, target, _ = line.decode('latin1').split(' ', 2)
            headers = {}
            while True:
                h = (await reader.readline()).decode('latin1').strip()
                if not h:
                    break
                k, _, v = h.partition(':')
                headers[k.strip().lower()] = v.strip()
            path = target.split('?', 1)[0]
            if headers.get('upgrade', '').lower() == 'websocket' and path == '/PropertyListener':
                await self.websocket(reader, writer, headers)
                return
            body = await reader.readexactly(int(headers.get('content-length', 0) or 0))
            status, ctype, payload = self.http(method, path, body)
            writer.write(('HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nAccess-Control-Allow-Origin: *\r\n'
                          'Access-Control-Allow-Headers: *\r\nAccess-Control-Allow-Methods: GET, POST, OPTIONS\r\nCache-Control: no-store\r\n'
                          'Connection: close\r\n\r\n' % (status, ctype, len(payload))).encode() + payload)
            await writer.drain()
        except (ConnectionError, ValueError, asyncio.IncompleteReadError):
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    def http(self, method, path, body):
        if method == 'OPTIONS':
            return '204 No Content', 'text/plain', b''
        if path.startswith('/json/ai/models'):
            return '200 OK', 'application/json', json.dumps(traffic(self.sim.f['simulation/sim-time-sec'])).encode()
        if path.startswith('/json/'):
            prop = path[5:]
            if method == 'POST':
                try:
                    self.sim.set(prop, json.loads(body.decode())['value'])
                except (ValueError, KeyError, TypeError):
                    return '400 Bad Request', 'application/json', b'{}'
            v = self.sim.get(prop)
            if v is None:
                return '404 Not Found', 'application/json', b'{}'
            return '200 OK', 'application/json', json.dumps(node(prop, v)).encode()
        if method == 'GET':
            # the station's own files and the mission files, as they lie in the aircraft's folder
            for prefix, folder in (('/gcs/', GCS_DIR), ('/Missions/', os.path.join(GCS_DIR, '..', 'Missions'))):
                if path.startswith(prefix) or path + '/' == prefix:
                    full = os.path.realpath(os.path.join(folder, path[len(prefix):] or 'index.html'))
                    if full.startswith(os.path.realpath(folder) + os.sep) and os.path.isfile(full):
                        return '200 OK', mimetypes.guess_type(full)[0] or 'application/octet-stream', open(full, 'rb').read()
        return '404 Not Found', 'text/plain', b'not found'

    async def websocket(self, reader, writer, headers):
        key = base64.b64encode(hashlib.sha1((headers['sec-websocket-key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        writer.write(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n' % key).encode())
        c = dict(writer=writer, paths=[], last={})
        self.clients.append(c)
        try:
            while True:
                msg = await ws_read(reader)
                if msg is None or msg[0] == 8:
                    break
                if msg[0] == 9:
                    writer.write(ws_frame(msg[1], 10))
                    continue
                if msg[0] != 1:
                    continue
                try:
                    m = json.loads(msg[1].decode())
                    cmd, path = m['command'], m['node']
                except (ValueError, KeyError, TypeError):
                    continue
                if cmd == 'addListener' and path not in c['paths']:
                    c['paths'].append(path)
                elif cmd == 'removeListener' and path in c['paths']:
                    c['paths'].remove(path)
                elif cmd == 'get':
                    v = self.sim.get(path)
                    if v is not None:
                        c['last'][path] = v
                        writer.write(ws_frame(json.dumps(node(path, v)).encode()))
                elif cmd == 'set':
                    self.sim.set(path, m.get('value'))
        finally:
            self.clients.remove(c)

    async def serve(self, port, host='127.0.0.1'):
        srv = await asyncio.start_server(self.handle, host, port)
        async with srv:
            await self.run_sim()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--port', type=int, default=5400)
    ap.add_argument('--host', default='127.0.0.1', help='0.0.0.0 to let other machines in')
    ap.add_argument('--speed', type=float, default=1.0)
    ap.add_argument('--plan', default=os.path.join(HERE, '..', 'GlobalHawk', 'Missions', 'demo-local.json'))
    ap.add_argument('--scenery', action='append', help="a scenery folder to read an airport's ground network from (the airport command); repeat for more. Default: FG_SCENERY and the usual TerraSync folders")
    a = ap.parse_args()
    # the made-up field of the demo plan has its ground network among the station's test fixtures (mkdemoground.py): always at hand, after the real scenery
    scenery = (a.scenery or AD.scenery_dirs()) + [os.path.join(HERE, '..', 'GlobalHawk', 'gcs', 'tests', 'fixtures', 'scenery')]
    sim = Sim(a.plan, scenery=scenery)
    print('the aircraft is on its stand; station: http://localhost:%d/gcs/   (speed %gx)' % (a.port, a.speed), flush=True)
    asyncio.run(Server(sim, a.speed).serve(a.port, a.host))


if __name__ == '__main__':
    main()
