"""Mech Royale bot: loot early, stay inside the zone, face enemies, strafe/dodge, shoot with lead."""
import json
import math
import os
import random
import sys
import threading
import time
from array import array

import mechfight as mf

PI = math.pi
hypot = math.hypot


def wrap(a):
    return (a + PI) % (2 * PI) - PI


def clamp(v, a, b):
    return a if v < a else b if v > b else v


# ----------------------------------------------------------------------------- map
class World:
    def __init__(self, mapdir):
        self.ok = False
        base = os.path.join(mapdir, "v2")
        with open(os.path.join(base, "world.json")) as f:
            wj = json.load(f)
        tr = wj["terrain"]
        self.nx, self.ny = tr["nx"], tr["ny"]
        self.minx, self.miny, self.st = tr["minX"], tr["minY"], tr["step"]
        g = array("h")
        with open(os.path.join(base, tr["file"]), "rb") as f:
            g.frombytes(f.read())
        if sys.byteorder != "little":
            g.byteswap()
        self.g = g
        self.bh = array("f", [-1000.0]) * (self.nx * self.ny)
        for p in wj["prisms"]:
            if p["kind"] == "bridge":
                continue
            try:
                self._fill(p)
            except Exception:
                pass
        b = wj["bounds"]
        self.bx0, self.bx1, self.by0, self.by1 = b["minX"], b["maxX"], b["minY"], b["maxY"]
        try:
            self.build_grid()
        except Exception:
            self.blk = None
        self.ok = True

    def _fill(self, p):
        top = p["top"]
        edges = []
        rings = [p["ring"]]
        for h in p.get("holes") or []:
            rings.append(h)
        ymin, ymax = 1e9, -1e9
        for ring in rings:
            n = len(ring) // 2
            for k in range(n):
                x0, y0 = ring[2 * k], ring[2 * k + 1]
                k2 = (k + 1) % n
                x1, y1 = ring[2 * k2], ring[2 * k2 + 1]
                if y0 != y1:
                    edges.append((x0, y0, x1, y1))
                ymin = min(ymin, y0)
                ymax = max(ymax, y0)
        st, minx, miny, nx, ny, bh = self.st, self.minx, self.miny, self.nx, self.ny, self.bh
        j0 = max(0, int(math.ceil((ymin - miny) / st)))
        j1 = min(ny - 1, int(math.floor((ymax - miny) / st)))
        for j in range(j0, j1 + 1):
            yc = miny + j * st
            xs = []
            for x0, y0, x1, y1 in edges:
                if (y0 <= yc < y1) or (y1 <= yc < y0):
                    xs.append(x0 + (yc - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            row = j * nx
            for q in range(0, len(xs) - 1, 2):
                i0 = max(0, int(math.ceil((xs[q] - minx) / st)))
                i1 = min(nx - 1, int(math.floor((xs[q + 1] - minx) / st)))
                for i in range(i0, i1 + 1):
                    if bh[row + i] < top:
                        bh[row + i] = top

    def build_grid(self, cs=3.0):
        import heapq  # noqa: F401
        self.cs = cs
        self.gx0, self.gy0 = self.bx0 + 3, self.by0 + 3
        self.gw = int((self.bx1 - self.bx0 - 6) / cs)
        self.gh = int((self.by1 - self.by0 - 6) / cs)
        blk = bytearray(self.gw * self.gh)
        bh, g = self.bh, self.g
        pts = ((0.5, 0.5), (0.2, 0.2), (0.8, 0.2), (0.2, 0.8), (0.8, 0.8))
        for j in range(self.gh):
            y0 = self.gy0 + j * cs
            for i in range(self.gw):
                x0 = self.gx0 + i * cs
                nb = 0
                cen = 0
                for q, (fx, fy) in enumerate(pts):
                    k = self.idx(x0 + fx * cs, y0 + fy * cs)
                    if bh[k] > g[k] * 0.01 + 1.3:
                        nb += 1
                        if q == 0:
                            cen = 1
                blk[j * self.gw + i] = 1 if (cen or nb >= 2) else 0
        self.blk = blk

    def cell(self, x, y):
        i = int((x - self.gx0) / self.cs)
        j = int((y - self.gy0) / self.cs)
        return clamp(i, 0, self.gw - 1), clamp(j, 0, self.gh - 1)

    def nearest_open(self, i, j):
        if not self.blk[j * self.gw + i]:
            return i, j
        for r in range(1, 12):
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    if max(abs(di), abs(dj)) != r:
                        continue
                    a, b = i + di, j + dj
                    if 0 <= a < self.gw and 0 <= b < self.gh and not self.blk[b * self.gw + a]:
                        return a, b
        return i, j

    def plan(self, sx, sy, gx, gy, max_nodes=60000):
        import heapq
        gw, gh, blk, cs = self.gw, self.gh, self.blk, self.cs
        si, sj = self.nearest_open(*self.cell(sx, sy))
        ti, tj = self.nearest_open(*self.cell(gx, gy))
        start, goal = sj * gw + si, tj * gw + ti
        if start == goal:
            return [(gx, gy)]
        gd = self.g
        dist = {start: 0.0}
        prev = {}
        W_ = 1.5
        h0 = max(abs(si - ti), abs(sj - tj)) + 0.414 * min(abs(si - ti), abs(sj - tj))
        pq = [(h0 * W_, start)]
        closed = set()
        best, besth = start, h0
        n = 0
        SQ = 1.4142
        while pq and n < max_nodes:
            _, cur = heapq.heappop(pq)
            if cur in closed:
                continue
            closed.add(cur)
            n += 1
            if cur == goal:
                best = cur
                break
            ci, cj = cur % gw, cur // gw
            dcur = dist[cur]
            gcur = gd[self.idx(self.gx0 + (ci + 0.5) * cs, self.gy0 + (cj + 0.5) * cs)] * 0.01
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                a, b = ci + di, cj + dj
                if a < 0 or b < 0 or a >= gw or b >= gh:
                    continue
                nb = b * gw + a
                if blk[nb] or nb in closed:
                    continue
                if di and dj and (blk[cj * gw + a] or blk[b * gw + ci]):
                    continue  # no corner cutting
                gn = gd[self.idx(self.gx0 + (a + 0.5) * cs, self.gy0 + (b + 0.5) * cs)] * 0.01
                if abs(gn - gcur) > 3.2:
                    continue
                nd = dcur + (SQ if di and dj else 1.0) + abs(gn - gcur) * 0.3
                if nd < dist.get(nb, 1e18):
                    dist[nb] = nd
                    prev[nb] = cur
                    hh = max(abs(a - ti), abs(b - tj)) + 0.414 * min(abs(a - ti), abs(b - tj))
                    if hh < besth:
                        besth, best = hh, nb
                    heapq.heappush(pq, (nd + W_ * hh, nb))
        path = []
        c = best
        while c != start:
            path.append((self.gx0 + (c % gw + 0.5) * cs, self.gy0 + (c // gw + 0.5) * cs))
            c = prev[c]
        path.reverse()
        if best == goal:
            path.append((gx, gy))
        return path

    def line_free(self, ax, ay, bx, by, z):
        d = hypot(bx - ax, by - ay)
        n = int(d / 1.5) + 1
        for k in range(1, n + 1):
            f = k / n
            px, py = ax + (bx - ax) * f, ay + (by - ay) * f
            if not self.free(px, py, z, 3.0):
                return False
            # clearance: sides
        return True

    def idx(self, x, y):
        i = int((x - self.minx) / self.st + 0.5)
        j = int((y - self.miny) / self.st + 0.5)
        if i < 0:
            i = 0
        elif i >= self.nx:
            i = self.nx - 1
        if j < 0:
            j = 0
        elif j >= self.ny:
            j = self.ny - 1
        return j * self.nx + i

    def ground(self, x, y):
        return self.g[self.idx(x, y)] * 0.01

    def roof(self, x, y):
        return self.bh[self.idx(x, y)]

    def free(self, x, y, z, s):
        if not (self.bx0 + 3 < x < self.bx1 - 3 and self.by0 + 3 < y < self.by1 - 3):
            return False
        k = self.idx(x, y)
        if self.bh[k] > z + 1.3:
            return False
        if self.g[k] * 0.01 - z > 1.19 * s + 1.5:
            return False
        return True

    def los(self, ax, ay, az, bx, by, bz):
        dx, dy = bx - ax, by - ay
        n = int(hypot(dx, dy) / 1.5)
        bh, g = self.bh, self.g
        for k in range(1, n):
            f = k / n
            i = self.idx(ax + dx * f, ay + dy * f)
            z = az + (bz - az) * f
            if bh[i] > z or g[i] * 0.01 > z:
                return False
        return True


# ----------------------------------------------------------------------------- bot
UPGRADE_PRIORITY = [
    "plating", "armor", "nanites", "gyros", "gun_damage", "lightning_chain", "laser_damage",
    "gun_rate", "servos", "gun_mag", "laser_charge", "lightning_efficiency", "lightning_range",
    "capacitor", "reactor", "sensors", "jets", "gun_velocity",
]
P = dict(want_l=28.0, want_g=80.0, want_lz=125.0, weak=0.35, amp=0.9, flip_lo=0.5, flip_hi=1.3, hold_hp=0.6, cube_r=30.0, cube_w=1.6, multi_n=99, multi_hp=0.7, adv_d=70.0, cover_camp=1, drop_r=120.0, drop_hp=0.6, late_pre=25.0, snd_avoid=1, avoid_s=3.0, tri=1, tri_far=58.0, laser_aim=1, engage_r=999.0, dmg_window=6.0, farm_until=999.0, camp=0.5, dodge_t=0.9, strafe_keep=0.7, v5=1, brain=1, team=0, eng_d=60.0, max_t=240.0, open_t=20.0, snipe_d=0.0, v5_open=0, v5_pos=0, v5_hide=0, v5_fight=0, corner_d=35.0, opp_d=60.0, opp_hp=0.6, opp_ratio=1.5, open_s=40.0, camp_late=0.3, loot_r=160.0, cube_roam=90.0)
try:
    _ENV = json.loads(os.environ.get("BOT_PARAMS", "{}"))
except Exception:
    _ENV = {}
P.update(_ENV)
# v5 "hide and survive" defaults: applied unless BOT_PARAMS sets v5=0; anything set explicitly in BOT_PARAMS wins.
V5 = dict(v5_open=0, loot_r=150.0, farm_until=999.0, v5_pos=1, v5_hide=1, v5_fight=0, weak=0.35, adv_d=70.0, cube_w=1.6, cube_r=30.0, cube_roam=90.0, snipe_d=0.0, team=1)
if _ENV.get("v5", 1):
    for _k, _v in V5.items():
        if _k not in _ENV:
            P[_k] = _v
WEAPON_SCORE = {"lightning": 2.0, "laser": 3.0, "mortar": 0.0, "gun": 1.0}


def wscore(kind):
    """Loot preference. v5 opening prefers the laser (hitscan, outranges mortar), then lightning."""
    if P["v5_open"]:
        return {"laser": 3.0, "lightning": 2.5}.get(kind, 0.0)
    return WEAPON_SCORE.get(kind, 0)


class Bot:
    name = "soloing-v15"

    def __init__(self, hello):
        cfg = hello["config"]
        self.cfg = cfg
        self.rng = random.Random(hello.get("seed", 0))
        self.slot = hello.get("slot", 0)
        self.world = None
        for d in (hello["map"]["dir"], "/arena"):
            try:
                self.world = World(d)
                break
            except Exception as e:  # map is an optimisation; play without it
                mf.log("map load failed:", d, repr(e))
        self.camp_ang = self.rng.uniform(-PI, PI)
        self.camp_cache = {}
        self.fight_reason = ""
        self.hit_by = {}
        self.stick = (-1, -99.0)
        self.lose_at = -99.0
        self.t_sign = 1
        self.t_sflip = 0.0
        self.snd_fight = None   # (bearing, t, dist) of the latest gunfire/explosion
        self.tel_on = os.environ.get("BOT_TELEMETRY", "1") == "1"
        self.tel_dmg = []          # last 10 damaged events
        self.tel_dt = []           # decision times (ms), capped
        self.tel_wdmg = {}         # damage taken by weapon
        self.tel_rear = 0.0
        self.tel_last = None       # last obs summary
        self.tel_beat = -99.0
        self.last_label = ""
        self.tel_maxvis = 0
        self.tel_first_dmg = None
        self.pk = {}      # pickup id -> {kind,pos}
        self.cb = {}      # cube id -> pos
        self.cr = {}      # crate id -> pos
        self.bad = {}     # blacklisted ids -> until time
        self.hist = []    # (t,x,y)
        self.ssign = 1
        self.sflip = 0.0
        self.bias = 1
        self.escape_until = 0.0
        self.escape_dir = 0.0
        self.alert = None  # (bearing, t)
        self.last_dmg_t = -99.0
        self.cover = None
        self.cover_t = -99.0
        self.sweep = 0.0
        self.last_move = (0.0, 0.0)
        self.goal_since = {}
        self.upg_taken = {}
        self.path = None
        self.plan_res = None
        self.planning = False
        self.sync_plan = False
        self.path_goal = (0.0, 0.0)
        self.path_t = -99.0

    # ------------------------------------------------------------------ helpers
    def steer(self, x, y, z, dx, dy, look=7.0):
        n = hypot(dx, dy)
        if n < 1e-6:
            return 0.0, 0.0
        dx /= n
        dy /= n
        w = self.world
        if w is None:
            return dx, dy
        base = math.atan2(dy, dx)
        offs = [0.0]
        for k in range(1, 8):
            offs.append(k * 0.4 * self.bias)
            offs.append(-k * 0.4 * self.bias)
        for off in offs:
            a = base + off
            ux, uy = math.cos(a), math.sin(a)
            ok = True
            for s in (2.5, 5.0, look):
                if not w.free(x + ux * s, y + uy * s, z, s):
                    ok = False
                    break
            if ok:
                # side probes
                px, py = -uy * 2.4, ux * 2.4
                if not (w.free(x + ux * 5 + px, y + uy * 5 + py, z, 5) and w.free(x + ux * 5 - px, y + uy * 5 - py, z, 5)):
                    if off != offs[-1]:
                        continue
                return ux, uy
        return dx, dy

    def safe_zone(self, zone, t):
        if P["v5_pos"] and t >= P["open_s"]:
            # after the opening, always stand inside the NEXT circle (it lies wholly inside the current one)
            return zone["next_center"], max(zone["next_radius"], 15.0)
        lead = 10 if zone["radius"] > 150 else P["late_pre"]
        if t >= zone["shrink_start"] - lead:
            return zone["next_center"], zone["next_radius"]
        return zone["center"], zone["radius"]

    def lead(self, sx, sy, sz, tp, tv, speed):
        tt = 0.0
        px, py, pz = tp
        for _ in range(3):
            px = tp[0] + tv[0] * tt
            py = tp[1] + tv[1] * tt
            pz = tp[2]
            d = math.sqrt((px - sx) ** 2 + (py - sy) ** 2 + (pz - sz) ** 2)
            tt = d / max(speed, 1.0) + 0.075
        return px, py, pz

    def aim_angles(self, sx, sy, sz, tx, ty, tz):
        yaw = math.atan2(ty - sy, tx - sx)
        pitch = math.atan2(tz - sz, hypot(tx - sx, ty - sy))
        m = self.cfg["mech"]
        return yaw, clamp(pitch, m["min_pitch"], m["max_pitch"])

    def choose_upgrade(self, offer, me):
        """Pick by value for what we hold; ids are validated against hello.config.upgrades."""
        held = {w["kind"] for w in me["weapons"] if w}
        defs = {u["id"]: u for u in self.cfg.get("upgrades", [])}
        taken = {}
        for u in me.get("upgrades", []):
            taken[u] = taken.get(u, 0) + 1
        base = {"armor": 10.0, "plating": 9.0, "nanites": 8.0, "gun_rate": 7.5, "gun_damage": 7.0, "gyros": 6.0,
                "servos": 5.0, "gun_mag": 4.5, "gun_velocity": 3.5, "sensors": 4.0, "capacitor": 3.0, "reactor": 3.0, "jets": 2.0}
        if "lightning" in held:
            base.update(lightning_chain=7.8, lightning_efficiency=5.5, lightning_range=5.0)
        if "laser" in held:
            base.update(laser_damage=8.9, laser_charge=8.5, laser_pierce=3.0)
        if "mortar" in held:
            base.update(mortar_splash=4.0, mortar_reload=4.0, mortar_velocity=3.0)
        best, bi = -1e9, 0
        for i, c in enumerate(offer["choices"]):
            cid = c["id"]
            d = defs.get(cid)
            sc = base.get(cid, 1.0)
            if d is not None:
                req = d.get("requires")
                if req and req not in held:
                    sc -= 50
                if taken.get(cid, 0) >= d.get("max", 99):
                    sc -= 50
            sc -= 1.5 * taken.get(cid, 0)
            if sc > best:
                best, bi = sc, i
        return bi

    def ingest(self, obs, me, t):
        x, y, z = me["pos"]
        for e in obs["events"]:
            ty = e.get("type")
            if ty == "took":
                self.pk.pop(e["id"], None)
            elif ty == "take_failed":
                if e["reason"] in ("gone", "have"):
                    self.pk.pop(e["id"], None)
                else:
                    self.bad[e["id"]] = t + 15
            elif ty == "dropped":
                self.bad[e["id"]] = t + 4
            elif ty == "damaged":
                self.last_dmg_t = t
                if e.get("by") is not None:
                    self.hit_by[e["by"]] = t
                if e.get("bearing") is not None:
                    self.alert = (e["bearing"], t)
        vis_pk = set()
        for p in obs["pickups"]:
            vis_pk.add(p["id"])
            self.pk[p["id"]] = {"kind": p["kind"], "pos": p["pos"]}
        vis_cb = set(c["id"] for c in obs["cubes"])
        self.cb = {i: p for i, p in self.cb.items() if i in vis_cb or hypot(p[0] - x, p[1] - y) > 30}
        for c in obs["cubes"]:
            self.cb[c["id"]] = c["pos"]
        vis_cr = set(c["id"] for c in obs["crates"])
        self.cr = {i: p for i, p in self.cr.items() if i in vis_cr or hypot(p[0] - x, p[1] - y) > 30}
        for c in obs["crates"]:
            self.cr[c["id"]] = c["pos"]
        for i in [i for i, p in self.pk.items() if i not in vis_pk and hypot(p["pos"][0] - x, p["pos"][1] - y) < 28]:
            del self.pk[i]
        # sounds -> alert (face it) and fight-avoidance memory
        for s in obs["sounds"]:
            k = s["kind"]
            if k in ("gun", "laser", "lightning", "mortar", "laser_charge", "explosion") and s["dist"] != "far":
                if self.alert is None or t - self.alert[1] > 1.0:
                    self.alert = (s["bearing"], t - s["age"])
                self.snd_fight = (s["bearing"], t - s["age"], s["dist"])
            elif k in ("gun", "laser", "lightning", "mortar", "explosion") and P["v5_hide"]:
                self.snd_fight = (s["bearing"], t - s["age"], s["dist"])  # far combat noise: still walk away from it
            elif k in ("step", "boost", "jet") and s["dist"] == "near":
                # a mech walking up on us: turn to face it (steps are only audible within 40 m)
                if self.alert is None or t - self.alert[1] > 1.0:
                    self.alert = (s["bearing"], t - s["age"])
        # stuck history
        self.hist.append((t, x, y))
        while self.hist and t - self.hist[0][0] > 1.5:
            self.hist.pop(0)

    def blocked_id(self, i, t):
        return self.bad.get(i, -1) > t

    def nearest_cube(self, x, y, r):
        best, bp = r, None
        for p in self.cb.values():
            d = hypot(p[0] - x, p[1] - y)
            if d < best:
                best, bp = d, p
        return bp

    def sheltered(self, base, zc, zr):
        """Camp spot near `base` that has buildings on several sides (fewer open firing lanes). Cached."""
        w = self.world
        if w is None or getattr(w, "blk", None) is None:
            return base
        key = (round(zc[0] / 15), round(zc[1] / 15), round(zr / 15), round(base[0] / 15), round(base[1] / 15))
        hit = self.camp_cache.get(key)
        if hit is not None:
            return hit
        best, bp = -1, base
        for r in (0.0, 15.0, 30.0, 45.0):
            for k in range(1 if r == 0 else 10):
                a = k * PI / 5
                cx, cy = base[0] + r * math.cos(a), base[1] + r * math.sin(a)
                if hypot(cx - zc[0], cy - zc[1]) > zr - 15 or w.blk[w.cell(cx, cy)[1] * w.gw + w.cell(cx, cy)[0]]:
                    continue
                gz = w.ground(cx, cy)
                shelter = 0
                for q in range(8):
                    ca, sa = math.cos(q * PI / 4), math.sin(q * PI / 4)
                    for dist in (5, 10, 15, 22):
                        if w.roof(cx + ca * dist, cy + sa * dist) > gz + 6:
                            shelter += 1
                            break
                sc_ = shelter - r * 0.02
                if sc_ > best:
                    best, bp = sc_, (cx, cy)
        if len(self.camp_cache) > 200:
            self.camp_cache.clear()
        self.camp_cache[key] = bp
        return bp

    def fight_ok(self, m, d, hpm, hpf, me, enemies, mine, t, outside):
        """v5: engage only when hurt, cornered, or when ALL of: target hurt/weaker, alone, matchup fine, close."""
        if t - self.last_dmg_t < P["dmg_window"]:
            return "hurt-by-someone"
        if outside:
            return None
        if d < P["corner_d"]:
            return "cornered"
        if d > P["opp_d"] or len(enemies) > 1:
            return None
        ew = set(m.get("weapons", []))
        against = ("lightning" in ew and "lightning" not in mine) or ("mortar" in ew and "lightning" in mine and "laser" not in mine)
        if against:
            return None
        if hpm < P["opp_hp"]:
            return "opp:target-hurt"
        if me["hp"] > P["opp_ratio"] * m.get("hp", 1400):
            return "opp:stronger"
        return None

    def engage_ok(self, m, d, me, obs, t):
        """Reactive engagement: fight what is close, what hurt us, what comes at us or aims at us; ignore the rest."""
        x, y = me["pos"][0], me["pos"][1]
        mid = m.get("id")
        hit = t - self.hit_by.get(mid, -99.0)
        hpm = m.get("hp", 700)
        hmax = max(1.0, m.get("max_hp", 1400))
        bearing = math.atan2(y - m["pos"][1], x - m["pos"][0])
        aimed = abs(wrap(m.get("aim", [0.0, 0.0])[0] - bearing)) < 0.22
        late = obs["zone"]["next_radius"] <= 70 or obs["alive"] <= 3
        if t < P["open_t"]:      # cautious opening: only close, attackers, or a charged laser pointed at us
            return (d < P["eng_d"] or hit < 4 or (aimed and m.get("charging") and d < 120)
                    or (hpm < 350 and d < 120) or obs["alive"] <= 2)
        if d < P["eng_d"] or hit < 6 or late:
            return True
        mv, sv = m.get("vel", [0, 0, 0]), me.get("vel", [0, 0, 0])
        closing = -((mv[0] - sv[0]) * (m["pos"][0] - x) + (mv[1] - sv[1]) * (m["pos"][1] - y)) / max(d, 1.0)
        if closing > 3 and d < 180:
            return True
        if hpm < 0.4 * hmax and d < 160:
            return True
        return aimed and d < 190

    def fight_move(self, x, y, z, tgt, rp, want_los, enemies, zone, t, w):
        """Pick one of 17 nearby spots: right range, line of sight to the target, out of sight of the others, inside the circle."""
        tp = tgt["pos"]
        sc = 1 + 0.05 * tgt.get("cubes", 0)
        tcz = tp[2] + 4.5 * sc
        bx, by = tp[0] - x, tp[1] - y
        bd = hypot(bx, by) or 1e-9
        ux, uy = bx / bd, by / bd
        if t >= self.t_sflip:
            if self.rng.random() < 0.6:
                self.t_sign = -self.t_sign
            self.t_sflip = t + 0.3 + self.rng.random() * 0.7
        sx, sy = -uy * self.t_sign, ux * self.t_sign
        others = sorted((e for e in enemies if e is not tgt and hypot(e["pos"][0] - x, e["pos"][1] - y) < 170),
                        key=lambda e: hypot(e["pos"][0] - x, e["pos"][1] - y))[:3]
        zc0, zr0 = zone["center"], zone["radius"]
        nc, nr = zone["next_center"], zone["next_radius"]
        soon = clamp(1 - (zone["shrink_start"] - t) / 25.0, 0.1, 1.0)
        best, bm = -1e9, (0.0, 0.0)
        blocked_side = False
        mzh = 7.0
        t0 = time.perf_counter()
        for k in range(-1, 16):
            if k >= 0:
                a = k * math.pi / 8
                dx, dy = math.cos(a), math.sin(a)
                r = 6.0
                cx, cy = x + dx * r, y + dy * r
                if w is not None and not (w.free(cx, cy, z, 5.0) and w.line_free(x, y, cx, cy, z)):
                    if dx * sx + dy * sy > 0.9:
                        blocked_side = True
                    continue
            else:
                dx = dy = r = 0.0
                cx, cy = x, y
            if k >= 0 and time.perf_counter() - t0 > 0.012:
                break
            d = hypot(tp[0] - cx, tp[1] - cy)
            s_ = -1.1 * abs(d - rp) - r * 0.4
            los = True if w is None else w.los(cx, cy, z + mzh, tp[0], tp[1], tcz)
            if los:
                s_ += 45 * want_los
            if w is not None:
                for e in others:
                    if w.los(e["pos"][0], e["pos"][1], e["pos"][2] + 8.0, cx, cy, z + 5.0):
                        s_ -= 30
            dd = hypot(cx - zc0[0], cy - zc0[1]) - zr0
            if dd > -5:
                s_ -= 150 + 5 * (dd + 5)
            dn = hypot(cx - nc[0], cy - nc[1]) - nr
            if dn > -5:
                s_ -= soon * (25 + 0.8 * (dn + 5))
            if want_los > 0:
                s_ += 9 * (dx * sx + dy * sy)
            if k < 0:
                s_ -= 8
                if want_los < 0 and not los:
                    s_ += 14
            if s_ > best:
                best, bm = s_, (dx, dy)
        if blocked_side:
            self.t_sign = -self.t_sign
            self.t_sflip = t + 0.5
        return bm

    def snap(self, p):
        w = self.world
        if w is None or getattr(w, "blk", None) is None:
            return p
        i, j = w.cell(p[0], p[1])
        if not w.blk[j * w.gw + i]:
            return p
        i, j = w.nearest_open(i, j)
        return (w.gx0 + (i + 0.5) * w.cs, w.gy0 + (j + 0.5) * w.cs)

    def waypoint(self, x, y, z, goal, t, T0):
        """Next point to walk toward: straight if clear, else follow an A* path."""
        w = self.world
        gd = hypot(goal[0] - x, goal[1] - y)
        if w is None or getattr(w, "blk", None) is None or gd < 6:
            return goal
        if gd < 45 and w.line_free(x, y, goal[0], goal[1], z):
            self.path = None
            return goal
        if self.plan_res is not None:
            self.path, self.path_goal, self.path_t = self.plan_res
            self.plan_res = None
        need = (
            self.path is None
            or hypot(self.path_goal[0] - goal[0], self.path_goal[1] - goal[1]) > 8
            or t - self.path_t > 5.0
            or (len(self.path) <= 1 and gd > 15)
            or t < self.escape_until
        )
        if need and not self.planning:
            self.planning = True
            sx, sy = x, y

            def job():
                try:
                    res = w.plan(sx, sy, goal[0], goal[1])
                    self.plan_res = (res, goal, t)
                except Exception:
                    self.plan_res = (None, goal, t)
                finally:
                    self.planning = False

            if self.sync_plan:
                job()
                self.path, self.path_goal, self.path_t = self.plan_res
                self.plan_res = None
            else:
                threading.Thread(target=job, daemon=True).start()
        if not self.path:
            return goal
        # drop passed waypoints; pick the farthest visible one within 30 m
        while len(self.path) > 1 and hypot(self.path[0][0] - x, self.path[0][1] - y) < 4.0:
            self.path.pop(0)
        tgt = self.path[0]
        for k in range(min(len(self.path), 10)):
            px, py = self.path[k]
            if hypot(px - x, py - y) > 30:
                break
            if w.line_free(x, y, px, py, z):
                tgt = self.path[k]
        return tgt

    # ------------------------------------------------------------------ telemetry (stderr only, size-capped)
    def act(self, obs):
        t0 = time.perf_counter()
        try:
            return self._act(obs)
        finally:
            dt = (time.perf_counter() - t0) * 1000.0
            if self.tel_on:
                try:
                    self._tel(obs, dt)
                except Exception:
                    pass

    def _tel(self, obs, dt):
        if len(self.tel_dt) < 6000:
            self.tel_dt.append(dt)
        t = obs["t"]
        me = obs["self"]
        for e in obs["events"]:
            if e.get("type") == "damaged":
                rec = [round(t, 1), round(e["amount"]), e.get("weapon"), e.get("by"), 1 if e.get("rear") else 0,
                       None if e.get("bearing") is None else round(e["bearing"], 2)]
                self.tel_dmg.append(rec)
                if len(self.tel_dmg) > 10:
                    self.tel_dmg.pop(0)
                w = e.get("weapon", "?")
                self.tel_wdmg[w] = self.tel_wdmg.get(w, 0) + e["amount"]
                if e.get("rear"):
                    self.tel_rear += e["amount"]
                if self.tel_first_dmg is None and w != "zone":
                    self.tel_first_dmg = round(t, 1)
        nvis = sum(1 for m in obs["mechs"] if m["kind"] == "mech")
        self.tel_maxvis = max(self.tel_maxvis, nvis)
        self.tel_last = dict(
            t=round(t, 1), hp=round(me["hp"]), max_hp=round(me["max_hp"]), en=round(me["energy"]),
            pos=[round(v) for v in me["pos"]], in_zone=me["in_zone"], cubes=me["cubes"], alive=obs["alive"],
            loadout=[(w["kind"] if w else None) for w in me["weapons"]], vis=nvis, mode=self.last_label, why=self.fight_reason,
            foes=[[m["id"], round(m["pos"][0] - me["pos"][0]), round(m["pos"][1] - me["pos"][1]), round(m.get("hp", 0)),
                   m.get("weapons", [])] for m in obs["mechs"] if m["kind"] == "mech"][:4],
        )
        if t - self.tel_beat >= 15.0:
            self.tel_beat = t
            mf.log("TEL beat " + json.dumps(self.tel_last, separators=(",", ":"))[:400])

    def on_end(self, msg):
        if not self.tel_on:
            return
        d = sorted(self.tel_dt)
        p99 = d[int(0.99 * (len(d) - 1))] if d else 0.0
        last = self.tel_dmg[-1] if self.tel_dmg else None
        rec = dict(place=msg.get("place"), kills=msg.get("kills"), death_t=(self.tel_last or {}).get("t"),
                   killer=(last[3] if last else None), weapon=(last[2] if last else None), rear=(last[4] if last else None),
                   state=self.tel_last, last_dmg=self.tel_dmg, dmg_by_weapon={k: round(v) for k, v in self.tel_wdmg.items()},
                   rear_dmg=round(self.tel_rear), first_dmg_t=self.tel_first_dmg, max_vis=self.tel_maxvis,
                   n_obs=len(d), p99_ms=round(p99, 2), max_ms=round(d[-1], 2) if d else 0.0, name=self.name)
        mf.log("TEL end " + json.dumps(rec, separators=(",", ":"))[:3000])

    def find_cover(self, x, y, z, threats, zc, zr):
        w = self.world
        if w is None or not threats:
            return None
        best, bp = 1e9, None
        for r in (12.0, 22.0, 32.0):
            for k in range(12):
                a = k * PI / 6
                cx, cy = x + r * math.cos(a), y + r * math.sin(a)
                if not w.free(cx, cy, z, r):
                    continue
                if hypot(cx - zc[0], cy - zc[1]) > zr - 8:
                    continue
                cz = w.ground(cx, cy)
                hid = True
                for tp in threats[:2]:
                    if w.los(tp[0], tp[1], tp[2] + 8, cx, cy, cz + 4.5):
                        hid = False
                        break
                if hid:
                    score = r + 0.1 * hypot(cx - zc[0], cy - zc[1])
                    if score < best:
                        best, bp = score, (cx, cy)
            if bp:
                break
        return bp

    # ------------------------------------------------------------------ main
    def _act(self, obs):
        T0 = time.perf_counter()
        me = obs["self"]
        x, y, z = me["pos"]
        t = obs["t"]
        tick = obs["tick"]
        stats = me["stats"]
        hpf = me["hp"] / me["max_hp"]
        energy = me["energy"]
        act = {"tick": tick}
        mcfg = self.cfg["mech"]
        w = self.world
        self.ingest(obs, me, t)
        if obs["offer"]:
            act["pick"] = self.choose_upgrade(obs["offer"], me)

        wl = me["weapons"]
        kinds = [(wk["kind"] if wk else None) for wk in wl]
        eye_h = stats.get("eye_height", 8.0)
        mz = stats.get("muzzle_height", 7.0)
        ex, ey, ez = x, y, z + eye_h

        zc, zr = self.safe_zone(obs["zone"], t)
        dzc = hypot(x - zc[0], y - zc[1])
        outside = dzc > zr - 12 or not me["in_zone"]
        cf = P["camp_late"] if (P["v5_pos"] and zr < 140) else P["camp"]
        camp = self.snap((zc[0] + cf * zr * math.cos(self.camp_ang), zc[1] + cf * zr * math.sin(self.camp_ang)))
        if P["cover_camp"]:
            camp = self.sheltered(camp, zc, zr)

        def in_safe(px, py, margin=10.0):
            return hypot(px - zc[0], py - zc[1]) < zr - margin

        enemies = [m for m in obs["mechs"] if m["kind"] == "mech"]
        npcs = [m for m in obs["mechs"] if m["kind"] == "npc"]

        # --- choose target
        tgt = None
        tgt_vis = False
        tgt_is_enemy = True
        best = 1e9
        hid = None
        for m in enemies:
            p = m["pos"]
            d = hypot(p[0] - x, p[1] - y)
            sc_ = max(1.0, m.get("cubes", 0))
            tz = p[2] + 4.5 * (1 + 0.05 * m.get("cubes", 0))
            vis = True if w is None else w.los(ex, ey, ez, p[0], p[1], tz)
            hpm = m.get("hp", 700) / max(1.0, m.get("max_hp", 1400))
            if d > P["engage_r"] and t - self.last_dmg_t > P["dmg_window"]:
                continue  # passive: ignore far enemies unless they are hurting us
            if P["v5_fight"]:
                why = self.fight_ok(m, d, hpm, hpf, me, enemies, kinds, t, outside)
                if why is None:
                    continue
                self.fight_reason = why
            if P["team"]:
                if d > P["max_t"] or not self.engage_ok(m, d, me, obs, t):
                    continue
                if not vis:
                    if hid is None or d < hid[1]:
                        hid = (m, d)
                    continue
                score = d + 0.2 * m.get("hp", 700)
                if hpm <= 0.3:
                    score -= 100
                if self.stick[0] == m.get("id") and t - self.stick[1] < 2.0:
                    score -= 120
                if t - self.hit_by.get(m.get("id"), -99.0) < 4:
                    score -= 40
                self.fight_reason = "team"
            else:
                score = d * (0.6 + hpm) + (0 if vis else 60)
                if d > 230:
                    score += 200
            if score < best:
                best, tgt, tgt_vis = score, m, vis
        if P["team"]:
            if tgt is None and hid is not None:
                tgt, tgt_vis = hid[0], False
            if tgt is not None:
                self.stick = (tgt.get("id"), t)
        if tgt is None and hpf > 0.5 and t < P["farm_until"]:
            for m in npcs:
                p = m["pos"]
                d = hypot(p[0] - x, p[1] - y)
                if d > 60 or not in_safe(p[0], p[1], 0):
                    continue
                vis = True if w is None else w.los(ex, ey, ez, p[0], p[1], p[2] + 1.7)
                if vis and d < best:
                    best, tgt, tgt_vis, tgt_is_enemy = d, m, True, False

        move = None     # desired world direction (unit-ish) or None = hold
        aim = None
        fire = [False, False]
        boost = False
        jump = False
        label = ""
        goal = None
        threats_pos = [m["pos"] for m in enemies]

        # --- incoming projectile / laser dodge vector
        dodge = None
        cxm, cym, czm = x, y, z + 4.5
        tmin = 9.0
        for pr in obs["projectiles"]:
            v = pr["vel"]
            sp2 = v[0] ** 2 + v[1] ** 2 + v[2] ** 2
            if sp2 < 1:
                continue
            rel = (cxm - pr["pos"][0], cym - pr["pos"][1], czm - pr["pos"][2])
            if pr["kind"] == "mortar":
                # landing estimate with gravity
                g = self.cfg["weapons"]["mortar"]["gravity"]
                px, py, pz = pr["pos"]
                vx, vy, vz = v
                tl = 0.0
                for _ in range(40):
                    tl += 0.1
                    floor_z = w.ground(px + vx * tl, py + vy * tl) if w else 0.0
                    if pz + vz * tl - 0.5 * g * tl * tl <= floor_z:
                        break
                lx, ly = px + vx * tl, py + vy * tl
                if hypot(lx - x, ly - y) < 10 and tl < tmin:
                    tmin = tl
                    dx, dy = x - lx, y - ly
                    n = hypot(dx, dy) or 1.0
                    dodge = (dx / n, dy / n)
                continue
            tc = (rel[0] * v[0] + rel[1] * v[1] + rel[2] * v[2]) / sp2
            if tc < 0 or tc > 0.9:
                continue
            mx, my, mzz = rel[0] - v[0] * tc, rel[1] - v[1] * tc, rel[2] - v[2] * tc
            if math.sqrt(mx * mx + my * my + mzz * mzz) < 4.2 and tc < tmin:
                tmin = tc
                n = hypot(mx, my)
                if n < 0.5:
                    dodge = (-v[1] / (hypot(v[0], v[1]) or 1), v[0] / (hypot(v[0], v[1]) or 1))
                else:
                    dodge = (mx / n, my / n)
        # laser telegraph from enemies aiming at me
        for m in enemies:
            if m.get("charging"):
                p = m["pos"]
                bearing = math.atan2(y - p[1], x - p[0])
                if abs(wrap(m["aim"][0] - bearing)) < 0.25:
                    ax, ay = math.cos(m["aim"][0]), math.sin(m["aim"][0])
                    px, py = -ay, ax
                    side = 1 if (x - p[0]) * px + (y - p[1]) * py >= 0 else -1
                    dodge = (px * side, py * side)
                    tmin = 0.0

        # --- upkeep: pickups in reach
        near_take = None
        for i, p in self.pk.items():
            if self.blocked_id(i, t):
                continue
            kd = p["kind"]
            sc_new = wscore(kd)
            if sc_new <= 0 or kd in kinds:
                continue
            if P["v5_open"] and kinds[1] is not None:
                continue  # opening: one good weapon only, no swapping
            cur = wscore(kinds[1]) if kinds[1] else 0
            if len(kinds) > 1 and kinds[1] is not None and sc_new <= cur:
                continue
            dd = hypot(p["pos"][0] - x, p["pos"][1] - y)
            if dd < 3.6 and abs(p["pos"][2] - z) < 3.5:
                near_take = (i, kd)
        if near_take and not (tgt and tgt_vis and hypot(tgt["pos"][0] - x, tgt["pos"][1] - y) < 40 and False):
            act["take"] = near_take[0]
            if len(wl) > 1 and wl[1] is not None:
                act["drop"] = 1

        # --- combat
        if tgt is not None:
            tp = tgt["pos"]
            tv = tgt.get("vel", [0, 0, 0])
            d = hypot(tp[0] - x, tp[1] - y)
            scale = 1 + 0.05 * tgt.get("cubes", 0) if tgt_is_enemy else 1.0
            tcz = tp[2] + (4.5 * scale if tgt_is_enemy else 1.7)
            gun = wl[0] if wl and wl[0] and wl[0]["kind"] == "gun" else None
            gspeed = gun["stats"]["speed"] if gun else 252.0
            sx, sy, sz = x, y, z + mz
            lp = self.lead(sx, sy, sz, (tp[0], tp[1], tcz), tv, gspeed)
            yaw, pitch = self.aim_angles(sx, sy, sz, lp[0], lp[1], lp[2])
            aim = [yaw, pitch]
            yerr = abs(wrap(yaw - me["aim"][0]))
            perr = abs(pitch - me["aim"][1])
            yerr_l, perr_l = yerr, perr
            has_lightning = "lightning" in kinds
            has_laser = "laser" in kinds
            # laser is hitscan: aim where the target will be when we release, not with bullet lead
            lw = next((w_ for w_ in wl if w_ and w_["kind"] == "laser"), None)
            if P["laser_aim"] and lw is not None and tgt_vis and d > 18 and (lw.get("charge", 0.0) > 0 or lw["cooldown"] <= 0.05):
                t_rel = max(0.0, lw["stats"]["charge"] - lw.get("charge", 0.0)) + 0.1
                lyaw, lpit = self.aim_angles(sx, sy, sz, tp[0] + tv[0] * t_rel, tp[1] + tv[1] * t_rel, tcz)
                aim = [lyaw, lpit]
                yerr_l = abs(wrap(lyaw - me["aim"][0]))
                perr_l = abs(lpit - me["aim"][1])
                yerr = abs(wrap(yaw - me["aim"][0]))  # gun still gated on its own solution
            if has_lightning and energy > 12:
                want = P["want_l"]
            elif has_laser:
                want = P["want_lz"]
            else:
                want = P["want_g"]
            if P["tri"] and tgt_is_enemy:
                ew = set(tgt.get("weapons", []))
                if "lightning" in ew and not has_lightning:
                    want = max(want, P["tri_far"])      # stay outside its 45 m arc range
                elif "laser" in ew and has_lightning and energy > 12:
                    want = P["want_l"]                   # lightning shorts lasers: close in
                if "mortar" in ew and has_laser:
                    want = max(want, 70.0)               # laser outranges and cooks off mortars
            if P["snipe_d"] and tgt_is_enemy:
                want = max(want, P["snipe_d"])      # v9: fight from long range, outside an idle bot's reach
            n_close = sum(1 for m_ in enemies if hypot(m_["pos"][0] - x, m_["pos"][1] - y) < 70)
            outnumbered = tgt_is_enemy and n_close >= P["multi_n"] and hpf < P["multi_hp"]
            weak = outnumbered or tgt_is_enemy and hpf < P["weak"] and (len(enemies) >= 2 or tgt.get("hp", 700) / max(1, tgt.get("max_hp", 1400)) > hpf)
            finishing = False
            if P["team"] and tgt_is_enemy:
                late_ = obs["zone"]["next_radius"] <= 70 or obs["alive"] <= 3
                thp = tgt.get("hp", 700)
                finishing = d < 120 and (thp < 200 or thp < me["hp"] * 0.5)
                near = sum(1 for m_ in enemies if hypot(m_["pos"][0] - x, m_["pos"][1] - y) < 160)
                tf = thp / max(1.0, tgt.get("max_hp", 1400))
                losing = (near >= 2 and hpf < 0.55) or (near >= 3 and hpf < 0.8)
                if hpf < 0.35 and tf > hpf + 0.1:
                    losing = True
                if tf < 0.25 and hpf > 0.2 and near <= 2:
                    losing = False
                if losing:
                    self.lose_at = t
                weak = (t - self.lose_at < 1.5) and not finishing and not late_
            tol = max(0.025, 0.7 * math.atan2(2.5, max(d, 5.0)))
            slew_y = stats.get("turn_rate", 4.0) * 0.05 * 0.9
            slew_p = stats.get("pitch_rate", 3.0) * 0.05 * 0.9
            tol_g = max(tol, slew_y)
            tol_gp = max(tol + 0.03, slew_p)
            # firing
            for si, wk in enumerate(wl):
                if not wk:
                    continue
                kd = wk["kind"]
                st = wk["stats"]
                if kd == "gun":
                    if wk.get("ammo", 1) <= 0:
                        act["reload"] = True
                    elif tgt_vis and d < st["range"] * 0.92 and yerr < tol_g and perr < tol_gp:
                        fire[si] = True
                elif kd == "lightning":
                    if tgt_vis and d < st["range"] * 0.95 and yerr < 0.2 and energy > 5:
                        fire[si] = True
                elif kd == "laser":
                    full = st["charge"]
                    ch = wk.get("charge", 0.0)
                    if tgt_vis and d < st["range"] * (0.97 if P["team"] else 0.9) and (d > 18 or ch > 0):
                        lethal = False
                        if 0 < ch < full - 0.05 and tgt_is_enemy and ch >= st.get("min_charge", 0.15):
                            mfrac = st.get("min_frac", 0.35)
                            ld = st["damage"] * (mfrac + (1 - mfrac) * ch / full) * (1 + 0.04 * min(me.get("cubes", 0), 10))
                            if "mortar" in tgt.get("weapons", []):
                                ld *= 1 + st.get("cookoff", 0.6)
                            lethal = ld * 0.8 >= tgt.get("hp", 1e9) and yerr_l < tol_g and perr_l < tol_gp
                        if lethal:
                            fire[si] = False   # release now: the partial charge already kills
                        elif ch > 0:
                            if ch >= full - 0.05 and yerr_l < tol_g and perr_l < tol_gp:
                                fire[si] = False
                            else:
                                fire[si] = True
                        elif wk["cooldown"] <= 0.05:
                            fire[si] = True
                    else:
                        fire[si] = False
            # movement
            hpt = tgt.get("hp", 700) / max(1.0, tgt.get("max_hp", 1400))
            if weak:
                if self.cover is None or t - self.cover_t > 0.7:
                    self.cover = self.find_cover(x, y, z, threats_pos, zc, zr) if time.perf_counter() - T0 < 0.02 else self.cover
                    self.cover_t = t
                if self.cover and hypot(self.cover[0] - x, self.cover[1] - y) > 3:
                    goal = self.cover
                    boost = energy > 30
                    label = "retreat"
                else:
                    move = (0.0, 0.0)
                    label = "hide"
            elif not tgt_vis:
                if tgt_is_enemy and hpf > P["hold_hp"] and d < P["adv_d"] and in_safe(tp[0], tp[1], 0):
                    goal = (tp[0], tp[1])
                    label = "advance"
                else:
                    cn = self.nearest_cube(x, y, 45.0)
                    if cn is not None and hpf > 0.3:
                        goal = (cn[0], cn[1])
                        label = "cube!"
                    else:
                        move = (0.0, 0.0)
                        label = "ambush"
            else:
                label = "fight"
                if t >= self.sflip:
                    self.ssign = -self.ssign if self.rng.random() < P["strafe_keep"] else self.ssign
                    self.sflip = t + self.rng.uniform(P["flip_lo"], P["flip_hi"])
                rx, ry = (tp[0] - x) / (d or 1), (tp[1] - y) / (d or 1)
                radial = clamp((d - want) / 15.0, -1.0, 1.0)
                if not tgt_is_enemy:
                    radial = clamp((d - 25) / 10.0, -1.0, 1.0)
                mx = radial * rx + P["amp"] * self.ssign * (-ry)
                my = radial * ry + P["amp"] * self.ssign * rx
                move = (mx, my)
                cn = self.nearest_cube(x, y, P["cube_r"])
                if cn is not None:
                    cdx, cdy = cn[0] - x, cn[1] - y
                    cdn = hypot(cdx, cdy) or 1.0
                    move = (mx + P["cube_w"] * cdx / cdn, my + P["cube_w"] * cdy / cdn)
            if P["team"] and tgt_is_enemy and not weak and w is not None:
                th_ = tgt.get("weapons", [])
                if "lightning" in kinds and energy > 12:
                    rp = P["want_l"]
                elif "laser" in kinds:
                    rp = P["want_lz"]
                else:
                    rp = P["want_g"]
                if "lightning" not in kinds and "lightning" in th_:
                    rp = max(rp, 64.0)
                if "mortar" in th_ and "lightning" not in kinds:
                    rp = max(rp, 80.0)
                crowd_ = sum(1 for m_ in enemies if hypot(m_["pos"][0] - x, m_["pos"][1] - y) < 150)
                if (tgt.get("hp", 700) < 0.38 * max(1.0, tgt.get("max_hp", 1400)) and hpf > 0.42 and crowd_ <= 2):
                    rp = 14.0
                gun_ = wl[0] if wl and wl[0] and wl[0]["kind"] == "gun" else None
                ready = ("laser" in kinds) or ("lightning" in kinds and energy >= 9)
                if not ready and gun_ is not None:
                    ready = gun_.get("ammo", 1) > 0 and gun_.get("reload", 0) <= 0.25 and d <= gun_["stats"]["range"] - 10
                tmv = self.fight_move(x, y, z, tgt, rp, 1.0 if ready else -1.0, enemies, obs["zone"], t, w)
                move, goal = tmv, None
                label = "fight"
                # cube detour in a fight (closer cubes matter more when healthy)
                cr = 70.0 if hpf > 0.5 else 40.0
                cbest, cd_ = None, cr
                for _cid, cp_ in self.cb.items():
                    dc_ = hypot(cp_[0] - x, cp_[1] - y)
                    if dc_ < cd_:
                        cbest, cd_ = cp_, dc_
                if cbest is not None:
                    goal, move, label = (cbest[0], cbest[1]), None, "fight:cube"
            if dodge is not None and tmin < P["dodge_t"]:
                move = dodge
                goal = None
                boost = boost
            if outside:
                goal = zc
                move = None
                boost = not me["in_zone"] and energy > 5
        else:
            # ---- no target: roam
            if self.alert and t - self.alert[1] < 1.5:
                aim = [self.alert[0], 0.0]
            # flee unseen damage
            if self.alert and t - self.last_dmg_t < 1.5 and t - self.alert[1] < 1.5:
                a = self.alert[0] + PI + 0.8 * self.ssign
                goal = (x + 40 * math.cos(a), y + 40 * math.sin(a))
                boost = energy > 40
                label = "flee"
            # someone else's fight nearby and nobody is shooting at us: walk away from it
            if (P["snd_avoid"] and goal is None and self.snd_fight and t - self.snd_fight[1] < P["avoid_s"]
                    and t - self.last_dmg_t > 3.0 and hpf > 0.3):
                a = self.snd_fight[0] + PI
                ag = (x + 35 * math.cos(a), y + 35 * math.sin(a))
                if in_safe(ag[0], ag[1], 12):
                    goal = ag
                    label = "avoid"
            if dodge is not None and tmin < 0.9:
                move = dodge
                goal = None
            # reload if idle
            gun = wl[0] if wl and wl[0] and wl[0]["kind"] == "gun" else None
            if gun and gun.get("ammo", 99) < self.cfg["weapons"]["gun"]["mag"] * 0.5:
                act["reload"] = True
            if goal is None and move is None:
                if outside:
                    goal = zc
                    boost = not me["in_zone"] and energy > 5
                    label = "zone"
                else:
                    # supply drop
                    cand = None
                    for dr in obs["drops"]:
                        dd = hypot(dr["pos"][0] - x, dr["pos"][1] - y)
                        if in_safe(dr["pos"][0], dr["pos"][1], 6) and dd < P["drop_r"] and dr["lands_in"] <= dd / 11.0 + 6 and hpf > P["drop_hp"]:
                            if dr.get("holder") not in (None, self.slot) and dd > 25:
                                continue
                            if cand is None or dd < cand[0]:
                                cand = (dd, dr)
                    if cand:
                        dr = cand[1]
                        goal = (dr["pos"][0], dr["pos"][1])
                        label = "drop"
                        if cand[0] < dr["radius"] * 0.5:
                            move = (0.0, 0.0)
                            goal = None
                    if goal is None and move is None:
                        # weapon pickup
                        wants = []
                        for i, p in self.pk.items():
                            if self.blocked_id(i, t):
                                continue
                            kd = p["kind"]
                            scn = wscore(kd)
                            if scn <= 0 or kd in kinds:
                                continue
                            if P["v5_open"] and len(kinds) > 1 and kinds[1] is not None:
                                continue
                            cur = wscore(kinds[1]) if len(kinds) > 1 and kinds[1] else 0
                            if scn <= cur:
                                continue
                            pp = p["pos"]
                            dd = hypot(pp[0] - x, pp[1] - y)
                            if dd > P["loot_r"] or not in_safe(pp[0], pp[1], 5):
                                continue
                            if pp[2] - (w.ground(pp[0], pp[1]) if w else 0) > 4:
                                continue
                            wants.append((dd - 20 * scn, i, pp))
                        if wants:
                            wants.sort()
                            _, i, pp = wants[0]
                            first = self.goal_since.setdefault(i, t)
                            if t - first > 40:
                                self.bad[i] = t + 90
                            else:
                                goal = (pp[0], pp[1])
                                label = "loot"
                    if goal is None and move is None and hpf > 0.3:
                        # cubes
                        cands = []
                        for i, p in self.cb.items():
                            if self.blocked_id(i, t):
                                continue
                            dd = hypot(p[0] - x, p[1] - y)
                            if dd < P["cube_roam"] and in_safe(p[0], p[1], 5):
                                cands.append((dd, i, p))
                        if cands:
                            cands.sort()
                            dd, i, p = cands[0]
                            first = self.goal_since.setdefault(i, t)
                            if t - first > 25:
                                self.bad[i] = t + 90
                            else:
                                goal = (p[0], p[1])
                                label = "cube"
                    if goal is None and move is None and hpf > 0.6 and t < min(330, P["farm_until"]):
                        # crates: approach and shoot
                        cands = []
                        for i, p in self.cr.items():
                            if self.blocked_id(i, t):
                                continue
                            dd = hypot(p[0] - x, p[1] - y)
                            if dd < 70 and in_safe(p[0], p[1], 5) and p[2] - (w.ground(p[0], p[1]) if w else 0) < 4:
                                cands.append((dd, i, p))
                        if cands:
                            cands.sort()
                            dd, i, p = cands[0]
                            first = self.goal_since.setdefault(i, t)
                            if t - first > 20:
                                self.bad[i] = t + 120
                            else:
                                cz = p[2] + 1.2
                                yaw, pitch = self.aim_angles(x, y, z + mz, p[0], p[1], cz)
                                aim = [yaw, pitch]
                                vis = True if w is None else w.los(ex, ey, ez, p[0], p[1], cz)
                                if dd > 22 or not vis:
                                    goal = (p[0], p[1])
                                else:
                                    move = (0.0, 0.0)
                                    perr = abs(pitch - me["aim"][1])
                                    if abs(wrap(yaw - me["aim"][0])) < 0.08 and perr < 0.1:
                                        for si, wk in enumerate(wl):
                                            if wk and wk["kind"] == "gun" and wk.get("ammo", 1) > 0 and dd < 150:
                                                fire[si] = True
                                            if wk and wk["kind"] == "lightning" and dd < wk["stats"]["range"] * 0.9 and energy > 30:
                                                fire[si] = True
                                label = "crate"
                    if goal is None and move is None:
                        dc = hypot(camp[0] - x, camp[1] - y)
                        if dc > 8:
                            goal = camp
                            label = "camp-go"
                        else:
                            move = (0.0, 0.0)
                            label = "camp"

        # --- turn goal into move
        if goal is not None and move is None:
            wp = self.waypoint(x, y, z, goal, t, T0)
            gdx, gdy = wp[0] - x, wp[1] - y
            gd = hypot(gdx, gdy)
            if hypot(goal[0] - x, goal[1] - y) < 1.2 or gd < 0.5:
                move = (0.0, 0.0)
            else:
                move = (gdx / gd, gdy / gd)

        # stuck detection (only when we wanted to move)
        stuck = False
        if self.hist and move and hypot(*move) > 0.5 and t - self.hist[0][0] > 1.2:
            h0 = self.hist[0]
            if hypot(x - h0[1], y - h0[2]) < 2.0 and not (fire[0] or fire[1]):
                stuck = True
        if stuck and t > self.escape_until:
            self.bias = -self.bias
            self.escape_until = t + 1.0
            self.escape_dir = self.rng.uniform(-PI, PI)
            self.hist = []
        if t < self.escape_until:
            move = (math.cos(self.escape_dir), math.sin(self.escape_dir))
            jump = True
            boost = energy > 25
            label = "unstick"

        if move is None:
            move = (0.0, 0.0)
        mx, my = move
        if hypot(mx, my) > 1e-6:
            mx, my = self.steer(x, y, z, mx, my)
            if label in ("hide", "camp", "ambush"):
                mx, my = 0.0, 0.0
        else:
            mx = my = 0.0

        # --- aim default
        if aim is None:
            if hypot(mx, my) > 0.1:
                aim = [math.atan2(my, mx), 0.0]
            else:
                self.sweep += 0.12
                if P["v5_hide"]:
                    base = math.atan2(zc[1] - y, zc[0] - x) if dzc > 15 else self.camp_ang
                    aim = [wrap(base + 1.0 * math.sin(t * 0.6)), 0.0]
                else:
                    aim = [wrap(me["aim"][0] + 0.12), 0.0]

        act["move"] = [round(mx, 4), round(my, 4)]
        act["aim"] = [round(aim[0], 4), round(aim[1], 4)]
        act["fire"] = fire
        act["boost"] = bool(boost)
        act["jump"] = bool(jump)
        self.last_move = (mx, my)

        # prune bad
        if tick % 100 == 0:
            self.bad = {k: v for k, v in self.bad.items() if v > t}
        self.last_label = label
        mf.draw.label(f"{label} hp{me['hp']:.0f}")
        return act



# ----------------------------------------------------------------------------- soloist brain
# Soloist: the decision brain of this bot (engage, fight positioning, retreat, loot, zone, firing).


class Soloist(Bot):
    name = "soloing-v15"
    LAT = 0.075

    OPENING_P = dict(retreat_hp=0.38, recover_hp=0.8, gun_range=85.0, light_range=28.0, laser_range=85.0, engage_dist=60.0,
                farm_npc=True, ghost=True, home_expo=120.0, loot_radius=90.0, crate_until=150.0, dodge=True,
                peek=True, laser_first=True, no_mortar=True, crowd_hide=True, practice=True,
                laser_seek=0.0, lethal=False, stick=0.0, hpw=0.0, low_bonus=0.0, max_target=0.0, lose_rule=False,
                fight_loot=0.0, farm_hp=0.0, laser_up=False, finish=0.0, pursue=0.0)
    MIDGAME_P = dict(ghost=False, peek=False, laser_first=True, laser_range=120.0, loot_radius=150.0, crate_until=1e9,
                 stick=120.0, hpw=0.2, low_bonus=100.0, max_target=240.0, lose_rule=True, fight_loot=70.0,
                 farm_hp=0.5, laser_seek=240.0, laser_up=True, lethal=True, finish=14.0, pursue=1.01)
    UPG_STD = ["plating", "armor", "gun_damage", "nanites", "gun_rate", "lightning_efficiency", "lightning_range",
             "laser_damage", "servos", "laser_charge", "gun_mag", "gun_velocity", "gyros", "lightning_chain",
             "reactor", "capacitor", "mortar_reload", "mortar_splash", "mortar_velocity", "sensors", "jets",
             "laser_pierce"]
    UPG_LASER = ["plating", "armor", "laser_damage", "laser_charge", "nanites", "gun_damage", "gun_rate",
                   "lightning_efficiency", "lightning_range", "servos", "gun_mag", "gun_velocity", "gyros",
                   "lightning_chain", "reactor", "capacitor", "mortar_reload", "mortar_splash", "mortar_velocity",
                   "sensors", "jets", "laser_pierce"]
    W_RANK = {"lightning": 3, "laser": 2, "mortar": 1}
    # extra behaviours (each can be switched off via BOT_PARAMS {"extras": {...}})
    EXTRAS = dict(safe=0, escape=0, hear=0, rear=0.0, drops=0, fight_drop_r=0.0)

    def __init__(self, hello):
        super().__init__(hello)
        self.foes = {}
        self.npcs = {}
        self.cube_mem = {}
        self.crate_mem = {}
        self.pick_mem = {}
        self.base = dict(self.OPENING_P)
        self.phase_p = dict(self.OPENING_P)
        self.prac_on = False
        self.not_practice = False
        self.start_alive = None
        self.kills = 0
        self.other_dead = 0
        self.now = 0.0
        self.prev_t = 0.0
        self.last_hurt = -100.0
        self.hurt_bearing = 0.0
        self.npc_hurt = -100.0
        self.npc_bearing = 0.0
        self.last_threat = -100.0
        self.retreat = False
        self.retreat_until = 0.0
        self.lose_t = -100.0
        self.cover_ok = False
        self.cover_at = -100.0
        self.cover_goal = (0.0, 0.0)
        self.strafe = 1.0
        self.strafe_until = 0.0
        self.stick_id = -1
        self.stick_at = -100.0
        self.hold_start = None
        self.hold = (0.0, 0.0, 1e9)
        self.loot_id = -1
        self.loot_since = 0.0
        self.home_xy = None
        self.home_at = -100.0
        self.stuck_since = -1.0
        self.unstuck_until = 0.0
        self.unstuck_dir = (0.0, 0.0)
        self.g_aim = [0.0, 0.0]
        self.mode = "idle"
        self.extras = dict(self.EXTRAS)
        self.extras.update(P.get("extras") or {})
        self.heard_at = -100.0
        self.heard_bearing = 0.0
        self.hear_until = 0.0
        self.hear_dx = 0.0
        self.hear_dy = 0.0
        self.comp = None
        self.main_comp = -1
        self.esc_until = 0.0
        self.esc_goal = None
        self.esc_at = -100.0
        self.errs = 0
        self.finish_range = None
        w = self.world
        if self.extras["escape"] and w is not None and getattr(w, "blk", None) is not None:
            threading.Thread(target=self._label_components, daemon=True).start()

    # ------------------------------------------------------------------ small helpers
    def clear(self, ax, ay, az, bx, by, bz):
        w = self.world
        return True if w is None else w.los(ax, ay, az, bx, by, bz)

    def solid(self, px, py, pz):
        w = self.world
        if w is None:
            return False
        return pz < max(w.roof(px, py), w.ground(px, py))

    def walkable(self, x0, y0, x1, y1, z):
        w = self.world
        return True if w is None else w.line_free(x0, y0, x1, y1, z)

    def free_cell(self, x, y, z):
        w = self.world
        return True if w is None else w.free(x, y, z, 3.0)

    def reachable(self, x, y):
        w = self.world
        if w is None or getattr(w, "blk", None) is None:
            return True
        i, j = w.cell(x, y)
        return not w.blk[j * w.gw + i]

    def scale_of(self, cubes):
        return 1 + self.cfg["cubes"].get("size_per_cube", 0.05) * cubes

    def center(self, tr):
        mc = self.cfg["mech"]
        h = mc["height"] * self.scale_of(tr.get("cubes", 0))
        if tr["kind"] == "npc":
            h = self.cfg["npc"]["height"]
        return (tr["pos"][0], tr["pos"][1], tr["pos"][2] + h * 0.5)

    def eye(self, tr):
        mc = self.cfg["mech"]
        return (tr["pos"][0], tr["pos"][1], tr["pos"][2] + mc["eye_height"] * self.scale_of(tr.get("cubes", 0)))

    def holds(self, lst, kind):
        return kind in (lst or [])

    def has_weapon(self, wl, kind):
        for i, wk in enumerate(wl):
            if wk and wk["kind"] == kind:
                return i, wk
        return -1, None

    def travel(self, x, y, z, extras, gy, t, T0):
        d = hypot(extras - x, gy - y)
        if d < 0.8:
            return (0.0, 0.0)
        wp = self.waypoint(x, y, z, (extras, gy), t, T0)
        dx, dy = wp[0] - x, wp[1] - y
        n = hypot(dx, dy)
        if n < 1e-6:
            return (0.0, 0.0)
        return self.steer(x, y, z, dx / n, dy / n)

    # ------------------------------------------------------------------ zone
    def zone_update(self, z, now):
        if self.hold_start != z["shrink_start"]:
            self.hold_start = z["shrink_start"]
            self.hold = (z["center"][0], z["center"][1], z["radius"])
        elif now <= z["shrink_start"]:
            self.hold = (z["center"][0], z["center"][1], z["radius"])

    def zone_at(self, z, t):
        if t <= z["shrink_start"] or z["shrink_end"] <= z["shrink_start"]:
            return self.hold
        f = clamp((t - z["shrink_start"]) / (z["shrink_end"] - z["shrink_start"]), 0.0, 1.0)
        hx, hy, hr = self.hold
        nc = z["next_center"]
        return (hx + (nc[0] - hx) * f, hy + (nc[1] - hy) * f, hr + (z["next_radius"] - hr) * f)

    def cur_zone(self, z):
        live = (z["center"][0], z["center"][1], z["radius"])
        if self.now <= z["shrink_start"]:
            return live
        if abs(live[2] - self.hold[2]) > 0.01 or abs(live[0] - self.hold[0]) > 0.01:
            return live
        return self.zone_at(z, self.now)

    def zone_deadline(self, z, x, y, pad):
        nc = z["next_center"]
        if hypot(x - nc[0], y - nc[1]) <= z["next_radius"] - pad:
            return 1e18
        for k in range(25):
            tt = z["shrink_start"] + (z["shrink_end"] - z["shrink_start"]) * k / 24.0
            c = self.zone_at(z, tt)
            if hypot(x - c[0], y - c[1]) > c[2] - pad:
                return tt
        return z["shrink_end"]

    def zone_penalty(self, z, x, y):
        c = self.cur_zone(z)
        p = 0.0
        d = hypot(x - c[0], y - c[1]) - c[2]
        if d > -5:
            p += 150 + 5 * (d + 5)
        nc = z["next_center"]
        dn = hypot(x - nc[0], y - nc[1]) - z["next_radius"]
        if dn > -5:
            soon = clamp(1 - (z["shrink_start"] - self.now) / 25.0, 0.1, 1.0)
            p += soon * (25 + 0.8 * (dn + 5))
        return p

    def zone_goal(self, z, x, y):
        nc = z["next_center"]
        nr = z["next_radius"]
        margin = clamp(0.3 * nr, 3.0, 30.0)
        if nr <= 30:
            return (nc[0], nc[1])
        dx, dy = x - nc[0], y - nc[1]
        d = hypot(dx, dy)
        if d < 1:
            return (x, y)
        r = max(0.0, nr - margin - 5)
        if d <= r:
            return (x, y)
        return (nc[0] + dx / d * r, nc[1] + dy / d * r)

    # ------------------------------------------------------------------ perception
    def observe(self, obs, me, t):
        self.now = t
        mc = self.cfg["mech"]
        x, y, zf = me["pos"]
        mzh = me["stats"].get("muzzle_height", 7.0)
        ezh = me["stats"].get("eye_height", 8.0)
        for m in obs["mechs"]:
            tab = self.npcs if m["kind"] == "npc" else self.foes
            tr = tab.get(m["id"])
            if tr is None:
                tr = {"hit_me": -100.0, "engage": False, "los": False}
                tab[m["id"]] = tr
            tr.update(id=m["id"], kind=m["kind"], pos=m["pos"], vel=m.get("vel", [0, 0, 0]), aim=m.get("aim", [0.0, 0.0]),
                      hp=m.get("hp", 700), max_hp=m.get("max_hp", 1400), cubes=m.get("cubes", 0),
                      weapons=m.get("weapons", []), charging=bool(m.get("charging", False)), seen=t)
            dx, dy = m["pos"][0] - x, m["pos"][1] - y
            tr["dist"] = hypot(dx, dy)
            c = self.center(tr)
            los = self.clear(x, y, zf + mzh, c[0], c[1], c[2])
            if not los and m["kind"] == "mech":
                h = mc["height"] * self.scale_of(tr["cubes"])
                los = self.clear(x, y, zf + mzh, m["pos"][0], m["pos"][1], m["pos"][2] + h * 0.85)
            tr["los"] = los
            if tr["dist"] > 1:
                mv = tr["vel"]
                sv = me.get("vel", [0, 0, 0])
                tr["closing"] = -((mv[0] - sv[0]) * dx + (mv[1] - sv[1]) * dy) / tr["dist"]
            else:
                tr["closing"] = 0.0
        for i in [i for i, tr in self.foes.items() if t - tr["seen"] > 20]:
            del self.foes[i]
        for i in [i for i, tr in self.npcs.items() if t - tr["seen"] > 120]:
            del self.npcs[i]
        self.prev_t = t

        def upd(tab, items, kind_key=False):
            for it in items:
                k = tab.get(it["id"])
                if k is None:
                    k = {"id": it["id"]}
                    tab[it["id"]] = k
                k["pos"] = it["pos"]
                k["kind"] = it.get("kind")
                k["hp"] = it.get("hp")
                k["seen"] = t
            for i in list(tab.keys()):
                k = tab[i]
                if k["seen"] == t:
                    continue
                d = hypot(k["pos"][0] - x, k["pos"][1] - y)
                if d < 40 and t - k["seen"] > 0.35 and self.clear(x, y, zf + ezh, k["pos"][0], k["pos"][1], k["pos"][2] + 1.5):
                    del tab[i]

        upd(self.crate_mem, obs["crates"])
        upd(self.cube_mem, obs["cubes"])
        upd(self.pick_mem, obs["pickups"])
        for e in obs["events"]:
            ty = e.get("type")
            if ty == "damaged":
                if e.get("weapon") == "npc" and e.get("bearing") is not None:
                    self.npc_hurt, self.npc_bearing = t, e["bearing"]
                if e.get("by") is not None:
                    self.last_hurt = t
                    if e.get("bearing") is not None:
                        self.hurt_bearing = e["bearing"]
                    if e["by"] in self.foes:
                        self.foes[e["by"]]["hit_me"] = t
                    if e["by"] in self.npcs:
                        self.npcs[e["by"]]["hit_me"] = t
            elif ty == "kill":
                self.kills += 1
                self.foes.pop(e.get("target"), None)
            elif ty == "took":
                self.pick_mem.pop(e["id"], None)
            elif ty == "take_failed":
                if e["reason"] in ("gone", "have"):
                    self.pick_mem.pop(e["id"], None)
                else:
                    self.bad[e["id"]] = t + 15
            elif ty == "dropped":
                self.bad[e["id"]] = t + 4
        if self.start_alive is None:
            self.start_alive = obs["alive"]
        if self.start_alive - obs["alive"] - self.kills > 0:
            self.other_dead += 1
        else:
            self.other_dead = 0
        if self.other_dead >= 5:
            self.not_practice = True
        on = self.base["practice"] and not self.not_practice and t > 20.0
        if on != self.prac_on:
            self.prac_on = on
            self.phase_p = dict(self.base)
            if on:
                self.phase_p.update(self.MIDGAME_P)
        if self.extras["hear"] and self.prac_on:
            self.hear(obs, me, t)
        self.zone_update(obs["zone"], t)

    # ------------------------------------------------------------------ upgrades and pickups
    def pick_upgrade(self, offer):
        order = self.UPG_LASER if self.phase_p["laser_up"] else self.UPG_STD
        best, br = 0, 1 << 30
        for i, c in enumerate(offer["choices"]):
            rank = len(order)
            if c["id"] in order:
                rank = order.index(c["id"])
            if rank < br:
                best, br = i, rank
        return best

    def want_pickup(self, wl, kind):
        if kind == "gun":
            return len(wl) > 0 and wl[0] is None
        if self.has_weapon(wl, kind)[0] >= 0:
            return False
        if kind == "mortar" and self.phase_p["no_mortar"]:
            return False

        def rank(k):
            if self.phase_p["laser_first"] and k == "laser":
                return 4
            return self.W_RANK.get(k, 0)

        cur = 0
        if len(wl) > 1 and wl[1] is not None:
            cur = rank(wl[1]["kind"])
        return rank(kind) > cur

    def pref_range(self, wl, energy, tr):
        _, light = self.has_weapon(wl, "lightning")
        _, laser = self.has_weapon(wl, "laser")
        r = self.phase_p["gun_range"]
        if light is not None and energy > 12:
            r = self.phase_p["light_range"]
        elif laser is not None:
            r = self.phase_p["laser_range"]
        if tr["kind"] == "npc":
            return 58.0
        if light is None:
            if self.holds(tr["weapons"], "lightning"):
                r = max(r, 64.0)
            if self.holds(tr["weapons"], "mortar"):
                r = max(r, 80.0)
        return r

    # ------------------------------------------------------------------ movement helpers
    def pick_spot(self, obs, me, tg, seen, want_los, wl, energy):
        x, y, zf = me["pos"]
        zone = obs["zone"]
        t = self.now
        rp = self.pref_range(wl, energy, tg)
        if self.finish_range:
            rp = self.finish_range
        bx, by = tg["pos"][0] - x, tg["pos"][1] - y
        bd = hypot(bx, by) + 1e-9
        ux, uy = bx / bd, by / bd
        if t >= self.strafe_until:
            if self.rng.random() < 0.6:
                self.strafe = -self.strafe
            self.strafe_until = t + 0.3 + self.rng.random() * 0.7
        sx, sy = -uy * self.strafe, ux * self.strafe
        tc = self.center(tg)
        mh = me["stats"].get("muzzle_height", 7.0)
        cube = None
        cd = 40.0
        for c in self.cube_mem.values():
            d = hypot(c["pos"][0] - x, c["pos"][1] - y)
            if d < cd and abs(c["pos"][2] - zf) < 4:
                cube, cd = c, d
        best, bm = -1e18, (0.0, 0.0)
        blocked_side = False
        rings = 2 if self.phase_p["peek"] else 1
        others = sorted((e for e in seen if e is not tg and e["seen"] == t and e["kind"] == "mech"
                         and hypot(e["pos"][0] - x, e["pos"][1] - y) <= 170),
                        key=lambda e: hypot(e["pos"][0] - x, e["pos"][1] - y))[:3]
        t0 = time.perf_counter()
        for k in range(-1, 16 * rings):
            if k >= 0 and time.perf_counter() - t0 > 0.008:
                break
            cx, cy, dx, dy, r = x, y, 0.0, 0.0, 0.0
            if k >= 0:
                a = (k % 16) * PI / 8
                r = 6.0 * (1 + k // 16)
                dx, dy = math.cos(a), math.sin(a)
                cx, cy = x + dx * r, y + dy * r
                if not (self.walkable(x, y, cx, cy, zf) and self.free_cell(cx, cy, zf)):
                    if k < 16 and dx * sx + dy * sy > 0.9:
                        blocked_side = True
                    continue
            d = hypot(tg["pos"][0] - cx, tg["pos"][1] - cy)
            s = -1.1 * abs(d - rp) - r * 0.4
            los = self.clear(cx, cy, zf + mh, tc[0], tc[1], tc[2])
            if los:
                s += 45 * want_los
            if self.phase_p["peek"] and 0 <= k < 16 and (los == (want_los > 0)):
                for q in range(0, 16, 2):
                    qx, qy = cx + math.cos(q * PI / 8) * 7, cy + math.sin(q * PI / 8) * 7
                    if self.free_cell(qx, qy, zf) and self.clear(qx, qy, zf + mh, tc[0], tc[1], tc[2]) != los:
                        s += 8
                        break
            for e in others:
                ee = self.eye(e)
                if self.clear(ee[0], ee[1], ee[2], cx, cy, zf + me["stats"].get("height", 9.0) * 0.6):
                    s -= 30
            s -= self.zone_penalty(zone, cx, cy)
            if cube is not None:
                s += 1.5 * (hypot(cube["pos"][0] - x, cube["pos"][1] - y) - hypot(cube["pos"][0] - cx, cube["pos"][1] - cy))
            if want_los > 0:
                s += 9 * (dx * sx + dy * sy)
            if k < 0:
                s -= 8
                if want_los < 0 and not los:
                    s += 14
            if s > best:
                best, bm = s, (dx, dy)
        if blocked_side:
            self.strafe = -self.strafe
            self.strafe_until = t + 0.5
        return bm

    def seek_cover(self, obs, me, seen, T0):
        w = self.world
        x, y, zf = me["pos"]
        t = self.now
        zone = obs["zone"]
        threats = [tr for tr in seen if hypot(tr["pos"][0] - x, tr["pos"][1] - y) < 230]
        if not threats:
            return None
        if len(threats) > 4:
            threats.sort(key=lambda q: hypot(q["pos"][0] - x, q["pos"][1] - y))
            threats = threats[:4]
        hgt = me["stats"].get("height", 9.0)

        def hidden(cx, cy):
            cz = w.ground(cx, cy) if w is not None else zf
            cz = max(cz, zf) if abs(cz - zf) < 4 else cz
            for tr in threats:
                e = self.eye(tr)
                if self.clear(e[0], e[1], e[2], cx, cy, cz + hgt) or self.clear(e[0], e[1], e[2], cx, cy, cz + hgt * 0.5):
                    return False
            return True

        if self.cover_ok and t - self.cover_at < 0.4:
            return self.travel_cover(x, y, zf, t, T0)
        self.cover_at = t
        if hidden(x, y) and self.zone_penalty(zone, x, y) == 0:
            self.cover_ok = True
            self.cover_goal = (x, y)
            return (0.0, 0.0)
        if w is None or getattr(w, "blk", None) is None:
            return None
        si, sj = w.nearest_open(*w.cell(x, y))
        gw, gh, cs, blk = w.gw, w.gh, w.cs, w.blk
        seenc = {sj * gw + si: 0}
        queue = [sj * gw + si]
        best_c, best_s = None, 1e18
        checked = 0
        h = 0
        while h < len(queue) and checked < 60:
            if time.perf_counter() - T0 > 0.012:
                break
            c = queue[h]
            h += 1
            ci, cj = c % gw, c // gw
            steps = seenc[c]
            if steps > 34 or (best_c is not None and steps * 2 > best_s + 30):
                break
            if (ci + cj) % 2 == 0 and steps > 0:
                cx, cy = w.gx0 + (ci + 0.5) * cs, w.gy0 + (cj + 0.5) * cs
                checked += 1
                if hidden(cx, cy):
                    sc = steps * 2 + self.zone_penalty(zone, cx, cy)
                    near = min(hypot(q["pos"][0] - cx, q["pos"][1] - cy) for q in threats)
                    sc -= min(near, 80) * 0.25
                    if sc < best_s:
                        best_c, best_s = (cx, cy), sc
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                a, b = ci + di, cj + dj
                if a < 0 or b < 0 or a >= gw or b >= gh:
                    continue
                nb = b * gw + a
                if nb in seenc or blk[nb]:
                    continue
                if di and dj and (blk[cj * gw + a] or blk[b * gw + ci]):
                    continue
                seenc[nb] = steps + 1
                queue.append(nb)
        if best_c is None:
            self.cover_ok = False
            return None
        self.cover_ok = True
        self.cover_goal = best_c
        return self.travel_cover(x, y, zf, t, T0)

    def travel_cover(self, x, y, zf, t, T0):
        if hypot(self.cover_goal[0] - x, self.cover_goal[1] - y) < 1.5:
            return (0.0, 0.0)
        return self.travel(x, y, zf, self.cover_goal[0], self.cover_goal[1], t, T0)

    def hide_from_bearing(self, obs, me, seen, T0):
        x, y, zf = me["pos"]
        ghost = {"pos": [x + math.cos(self.hurt_bearing) * 80, y + math.sin(self.hurt_bearing) * 80, zf],
                 "kind": "mech", "cubes": 0, "seen": self.now, "weapons": []}
        return self.seek_cover(obs, me, [ghost] + list(seen), T0)

    def dodge_vec(self, obs, me):
        cx, cy, cz = me["pos"][0], me["pos"][1], me["pos"][2] + me["stats"].get("height", 9.0) * 0.56
        reach = me["stats"].get("radius", 2.5) + 1.1
        dx = dy = 0.0
        laser = False
        for p in obs["projectiles"]:
            if p["kind"] == "mortar":
                continue
            v = p["vel"]
            v2 = v[0] * v[0] + v[1] * v[1] + v[2] * v[2]
            if v2 < 1:
                continue
            tc = ((cx - p["pos"][0]) * v[0] + (cy - p["pos"][1]) * v[1] + (cz - p["pos"][2]) * v[2]) / v2
            if tc <= 0 or tc > 0.7:
                continue
            mxx, myy = p["pos"][0] + v[0] * tc - cx, p["pos"][1] + v[1] * tc - cy
            if hypot(mxx, myy) < reach:
                vh = hypot(v[0], v[1])
                if vh < 1:
                    continue
                px, py = -v[1] / vh, v[0] / vh
                if px * mxx + py * myy > 0:
                    px, py = -px, -py
                dx += px
                dy += py
        for m in obs["mechs"]:
            if m["kind"] != "mech" or not m.get("charging"):
                continue
            to_me = math.atan2(cy - m["pos"][1], cx - m["pos"][0])
            if abs(wrap(m["aim"][0] - to_me)) > 0.15:
                continue
            dx += math.cos(to_me + PI / 2 * self.strafe) * 1.5
            dy += math.sin(to_me + PI / 2 * self.strafe) * 1.5
            laser = True
        n = hypot(dx, dy)
        if n > 0.01:
            return dx / n, dy / n, laser
        return 0.0, 0.0, False

    def dodge_shell(self, obs, me):
        g = self.cfg["weapons"].get("mortar", {}).get("gravity", 22.0) or 22.0
        rad = self.cfg["weapons"].get("mortar", {}).get("splash_radius", 7.0) + me["stats"].get("radius", 2.5) + 2
        x, y, z = me["pos"]
        for p in obs["projectiles"]:
            if p["kind"] != "mortar":
                continue
            px, py, pz = p["pos"]
            vz = p["vel"][2]
            tt = 0.0
            while tt < 4:
                px += p["vel"][0] * 0.05
                py += p["vel"][1] * 0.05
                pz += vz * 0.05
                vz -= g * 0.05
                tt += 0.05
                if self.solid(px, py, pz):
                    d = hypot(px - x, py - y)
                    if d < rad and tt < 2.5:
                        dx, dy = x - px, y - py
                        if d < 0.5:
                            dx, dy = -p["vel"][1], p["vel"][0]
                            d = hypot(dx, dy) or 1.0
                        dx, dy = dx / d, dy / d
                        for rot in (0.0, 0.7, -0.7, 1.4, -1.4):
                            c, s = math.cos(rot), math.sin(rot)
                            ex, ey = dx * c - dy * s, dx * s + dy * c
                            if self.walkable(x, y, x + ex * 6, y + ey * 6, z):
                                return (ex, ey)
                    break
        return None

    # ------------------------------------------------------------------ opening hideout (ghost params)
    def exposure(self, px, py):
        w = self.world
        if w is None:
            return 0.5
        z = w.ground(px, py) + 7
        total = 0.0
        for k in range(12):
            a = k * PI / 6
            c, s = math.cos(a), math.sin(a)
            d = 5.0
            while d < 200:
                qx, qy = px + c * d, py + s * d
                if self.solid(qx, qy, z):
                    break
                d += 5.0
            total += d
        return total / (12 * 200)

    def home_cost(self, obs, me, px, py):
        z = obs["zone"]
        crowd = 0.0
        for tr in self.foes.values():
            if self.now - tr["seen"] < 20:
                crowd += max(0.0, 80 - hypot(tr["pos"][0] - px, tr["pos"][1] - py)) / 80
        for dr in obs["drops"]:
            crowd += max(0.0, 60 - hypot(dr["pos"][0] - px, dr["pos"][1] - py)) / 60
        nc = z["next_center"]
        edge = hypot(px - nc[0], py - nc[1]) / max(30.0, z["next_radius"])
        return (self.phase_p["home_expo"] * self.exposure(px, py) + 0.25 * hypot(px - me["pos"][0], py - me["pos"][1])
                + 40 * crowd + 10 * edge)

    def home(self, obs, me):
        z = obs["zone"]
        nc, nr = z["next_center"], z["next_radius"]
        out = self.home_xy is None or hypot(self.home_xy[0] - nc[0], self.home_xy[1] - nc[1]) > nr * 0.8
        if out or self.now - self.home_at > 12:
            self.home_at = self.now
            best, bc = None, 1e18
            for _ in range(8):
                a = self.rng.random() * 2 * PI
                r = math.sqrt(self.rng.random()) * nr * 0.7
                px, py = nc[0] + math.cos(a) * r, nc[1] + math.sin(a) * r
                if not self.reachable(px, py):
                    continue
                c = self.home_cost(obs, me, px, py)
                if c < bc:
                    best, bc = (px, py), c
            if best is not None and (out or bc < self.home_cost(obs, me, *self.home_xy) - 15):
                self.home_xy = best
        return self.home_xy

    # ------------------------------------------------------------------ loot
    def pick_loot(self, obs, me, hpf, danger, wl):
        x, y, zf = me["pos"]
        z = obs["zone"]
        now = self.now
        cur = self.cur_zone(z)
        pp = self.phase_p
        best = None
        best_u = 0.0
        ws = me["stats"].get("walk_speed", 11.7)
        cube_cap = int(self.cfg["cubes"].get("stat_cap", 10))

        def consider(kind, iid, pos, value):
            nonlocal best, best_u
            if self.bad.get(iid, -1) > now:
                return
            d = hypot(pos[0] - x, pos[1] - y)
            if d > 260:
                return
            if hypot(pos[0] - cur[0], pos[1] - cur[1]) > cur[2] - 6:
                return
            if now + d * 1.4 / ws + 5 > self.zone_deadline(z, pos[0], pos[1], 6):
                return
            if self.world is not None and pos[2] - self.world.ground(pos[0], pos[1]) > 3.2:
                return
            if not self.reachable(pos[0], pos[1]):
                return
            u = value / (d + 18)
            if iid == self.loot_id:
                u *= 1.35
            if u > best_u:
                best_u = u
                best = {"kind": kind, "id": iid, "pos": pos, "value": value}

        for p in self.pick_mem.values():
            rad = pp["loot_radius"]
            seek = p["kind"] == "laser" and pp["laser_seek"] > rad
            if seek:
                rad = pp["laser_seek"]
            if self.want_pickup(wl, p["kind"]) and hypot(p["pos"][0] - x, p["pos"][1] - y) < rad:
                v = 60.0
                if len(wl) > 1 and wl[1] is None:
                    v = 130.0
                if seek:
                    v = max(v, 150.0)
                consider("pickup", p["id"], p["pos"], v)
        cube_v = 25.0 if me["cubes"] >= cube_cap else 75.0
        for c in self.cube_mem.values():
            if hypot(c["pos"][0] - x, c["pos"][1] - y) < max(60.0, pp["loot_radius"] * 0.7):
                consider("cube", c["id"], c["pos"], cube_v)
        if self.extras["drops"] and self.prac_on and not danger and hpf > 0.5:
            for dr in obs["drops"]:
                dist = hypot(dr["pos"][0] - x, dr["pos"][1] - y)
                eta = max(0.0, dist - self.drop_radius(dr) * 0.5) / max(1.0, ws)
                if dr["lands_in"] <= eta + 3 and (dist < self.drop_radius(dr) or self.drop_free(dr, me["id"], 6)):
                    consider("drop", dr["id"], dr["pos"], self.drop_worth(me, hpf))
        farm_hp = pp["farm_hp"] if pp["farm_hp"] > 0 else 0.7
        if hpf > farm_hp and not danger and now < pp["crate_until"]:
            for c in self.crate_mem.values():
                if hypot(c["pos"][0] - x, c["pos"][1] - y) < pp["loot_radius"]:
                    consider("crate", c["id"], c["pos"], cube_v * 0.6)
            if pp["farm_npc"] and me["cubes"] < cube_cap:
                for n in self.npcs.values():
                    if now - n["seen"] < 12 and hypot(n["pos"][0] - x, n["pos"][1] - y) < pp["loot_radius"]:
                        consider("npc", n["id"], n["pos"], 85.0)
        if best is None:
            self.loot_id = -1
            return None
        if best["id"] != self.loot_id:
            self.loot_id = best["id"]
            self.loot_since = now
        elif now - self.loot_since > (60.0 if best["kind"] == "drop" else 30.0):
            self.bad[best["id"]] = now + 60
            self.loot_id = -1
            return None
        return best

    # ------------------------------------------------------------------ additions: escape from enclosed pockets
    def _label_components(self):
        try:
            w = self.world
            gw, gh, blk = w.gw, w.gh, w.blk
            comp = array("i", [-1]) * (gw * gh)
            sizes = []
            for s0 in range(gw * gh):
                if (s0 & 2047) == 0:
                    time.sleep(0.002)
                if blk[s0] or comp[s0] >= 0:
                    continue
                cid = len(sizes)
                comp[s0] = cid
                stack = [s0]
                n = 0
                while stack:
                    c = stack.pop()
                    n += 1
                    if (n & 2047) == 0:
                        time.sleep(0.002)
                    ci, cj = c % gw, c // gw
                    for nb in ((c + 1) if ci + 1 < gw else -1, (c - 1) if ci > 0 else -1,
                               (c + gw) if cj + 1 < gh else -1, (c - gw) if cj > 0 else -1):
                        if nb >= 0 and not blk[nb] and comp[nb] < 0:
                            comp[nb] = cid
                            stack.append(nb)
                sizes.append(n)
            if sizes:
                self.main_comp = max(range(len(sizes)), key=lambda i: sizes[i])
                self.comp = comp
        except Exception:
            self.comp = None

    def off_main(self, x, y):
        w = self.world
        if self.comp is None or w is None:
            return False
        i, j = w.cell(x, y)
        if w.blk[j * w.gw + i]:
            i, j = w.nearest_open(i, j)
        return self.comp[j * w.gw + i] != self.main_comp

    def escape_step(self, me, t):
        """Trapped in an enclosed pocket: jump and boost toward the nearest cell of the main walkable area."""
        w = self.world
        x, y, zf = me["pos"]
        grounded = me.get("grounded", True)
        if t < self.esc_until and self.esc_goal is not None:
            extras, gy = self.esc_goal
            d = hypot(extras - x, gy - y)
            if d < 3:
                self.esc_until = 0.0
                return None
            ux, uy = (extras - x) / d, (gy - y) / d
            need = -1e9
            for k in range(0, int(min(d, 30)) + 1, 2):
                need = max(need, w.roof(x + ux * k, y + uy * k), w.ground(x + ux * k, y + uy * k))
            return ux, uy, (zf < need + 2.5 and me["energy"] > 1), (grounded and me["energy"] > 40)
        if not grounded or t - self.esc_at < 6 or self.comp is None or w is None:
            return None
        if zf - w.ground(x, y) > 3 or not self.off_main(x, y):
            return None
        self.esc_at = t
        for r in range(6, 48, 6):
            for k in range(16):
                a = k * PI / 8
                px, py = x + math.cos(a) * r, y + math.sin(a) * r
                i, j = w.cell(px, py)
                c = j * w.gw + i
                if not w.blk[c] and self.comp[c] == self.main_comp:
                    self.esc_goal = (px, py)
                    self.esc_until = t + 4.0
                    return None
        return None

    # ------------------------------------------------------------------ additions: hearing, rear armor, supply drops
    MECH_SOUNDS = {"gun", "mortar", "laser_charge", "laser", "lightning", "step", "boost", "jet", "reload"}

    def hear(self, obs, me, t):
        x, y = me["pos"][0], me["pos"][1]
        for s in obs.get("sounds", []):
            if s["kind"] not in self.MECH_SOUNDS or s.get("dist") == "far":
                continue
            if any(tr["seen"] == t and abs(wrap(math.atan2(tr["pos"][1] - y, tr["pos"][0] - x) - s["bearing"])) < 0.35
                   for tr in self.foes.values()):
                continue
            at = t - s.get("age", 0.0)
            if at > self.heard_at:
                self.heard_at, self.heard_bearing = at, s["bearing"]
            if s["kind"] == "laser_charge" and at > self.hear_until - 0.8:
                side = -1.0 if self.rng.random() < 0.5 else 1.0
                self.hear_dx, self.hear_dy = -math.sin(s["bearing"]) * side, math.cos(s["bearing"]) * side
                self.hear_until = t + 0.8

    def behind(self, tr, x, y):
        arc = self.cfg["mech"].get("front_arc_deg", 180) or 180
        return abs(wrap(tr["aim"][0] - math.atan2(y - tr["pos"][1], x - tr["pos"][0]))) > arc * PI / 360 + 0.3

    def drop_radius(self, dr):
        return dr.get("radius") or self.cfg.get("drops", {}).get("radius", 8.0) or 8.0

    def drop_free(self, dr, my_id, pad):
        if dr.get("holder") is not None and dr["holder"] != my_id:
            return False
        r = self.drop_radius(dr) + pad
        for tr in self.foes.values():
            if self.now - tr["seen"] < 3 and hypot(tr["pos"][0] - dr["pos"][0], tr["pos"][1] - dr["pos"][1]) < r:
                return False
        return True

    def drop_worth(self, me, hpf):
        n = self.cfg.get("drops", {}).get("cubes", 3) or 3
        cap = int(self.cfg["cubes"].get("stat_cap", 10))
        under = min(max(cap - me["cubes"], 0), n)
        return 75.0 * under + 25.0 * (n - under) + 400.0 * clamp(1 - hpf, 0.0, 1.0)

    def fight_drop(self, obs, me, hpf):
        cap = int(self.cfg["cubes"].get("stat_cap", 10))
        if hpf >= 0.9 and me["cubes"] >= cap:
            return None
        x, y = me["pos"][0], me["pos"][1]
        z = obs["zone"]
        cur = self.cur_zone(z)
        walk = max(1.0, me["stats"].get("walk_speed", 11.7))
        best, best_d = None, self.extras["fight_drop_r"]
        for dr in obs["drops"]:
            dd = hypot(dr["pos"][0] - x, dr["pos"][1] - y)
            if dd > best_d:
                continue
            r = self.drop_radius(dr)
            eta = max(0.0, dd - r * 0.5) / walk
            if dr["lands_in"] > eta + 0.5:
                continue
            if dd >= r and not self.drop_free(dr, me["id"], 4):
                continue
            if hypot(dr["pos"][0] - cur[0], dr["pos"][1] - cur[1]) > cur[2] - 6:
                continue
            cap_s = dr.get("capture_s") or self.cfg.get("drops", {}).get("capture_s", 4.0)
            if dr.get("holder") == me["id"]:
                cap_s -= dr.get("progress", 0.0)
            if self.zone_deadline(z, dr["pos"][0], dr["pos"][1], 6) < self.now + eta + cap_s + 2:
                continue
            if not self.reachable(dr["pos"][0], dr["pos"][1]):
                continue
            best, best_d = dr, dd
        return best

    # ------------------------------------------------------------------ main step
    def _act(self, obs):
        if not self.extras["safe"]:
            return self._think(obs)
        try:
            return self._think(obs)
        except Exception as e:
            self.errs += 1
            if self.errs <= 3:
                mf.log("soloist error:", repr(e))
            try:
                return Bot._act(self, obs)
            except Exception:
                return {"tick": obs["tick"], "move": [0, 0], "aim": list(obs["self"]["aim"]), "fire": [False, False]}

    def _think(self, obs):
        T0 = time.perf_counter()
        me = obs["self"]
        t = obs["t"]
        x, y, zf = me["pos"]
        st = me["stats"]
        w = self.world
        act = {"tick": obs["tick"]}
        self.observe(obs, me, t)
        pp = self.phase_p
        hpf = me["hp"] / max(1.0, me["max_hp"])
        energy = me["energy"]
        zone = obs["zone"]
        wl = me["weapons"]
        if obs["offer"] and obs["offer"].get("choices"):
            act["pick"] = self.pick_upgrade(obs["offer"])
        _, gun = self.has_weapon(wl, "gun")
        _, light = self.has_weapon(wl, "lightning")
        _, laser = self.has_weapon(wl, "laser")
        late = zone["next_radius"] <= 70 or obs["alive"] <= 3
        ws = st.get("walk_speed", 11.7)
        mzh = st.get("muzzle_height", 7.0)

        seen = []
        target = hidden = None
        best_score = 1e18
        max_t = pp["max_target"] if pp["max_target"] > 0 else 215.0
        hpw = pp["hpw"] if pp["hpw"] > 0 else 60.0 / 1400
        for tr in self.foes.values():
            if t - tr["seen"] > 2.5:
                continue
            tr["engage"] = False
            if tr["seen"] == t:
                seen.append(tr)
            else:
                seen.append(tr)
                tr["los"] = False
                continue
            to_me = math.atan2(y - tr["pos"][1], x - tr["pos"][0])
            aimed = abs(wrap(tr["aim"][0] - to_me)) < 0.22
            hit = t - tr["hit_me"]
            if pp["ghost"]:
                tr["engage"] = (tr["dist"] < pp["engage_dist"] or hit < 4 or (aimed and tr["charging"] and tr["dist"] < 120)
                                or (tr["hp"] < 350 and tr["dist"] < 120) or obs["alive"] <= 2)
            elif tr["dist"] < pp["engage_dist"] or hit < 6 or late:
                tr["engage"] = True
            elif tr["closing"] > 3 and tr["dist"] < 180:
                tr["engage"] = True
            elif tr["hp"] < 0.4 * tr["max_hp"] and tr["dist"] < 160:
                tr["engage"] = True
            elif aimed and tr["dist"] < 190:
                tr["engage"] = True
            if tr["engage"] and not tr["los"] and tr["dist"] < max_t and (hidden is None or tr["dist"] < hidden["dist"]):
                hidden = tr
            if not tr["engage"] or not tr["los"] or tr["dist"] > max_t:
                continue
            s = tr["dist"] + hpw * tr["hp"]
            if pp["low_bonus"] > 0 and tr["hp"] <= 0.3 * tr["max_hp"]:
                s -= pp["low_bonus"]
            if pp["stick"] > 0 and tr["id"] == self.stick_id and t - self.stick_at < 2:
                s -= pp["stick"]
            if hit < 4:
                s -= 40
            if tr["closing"] > 3:
                s -= 15
            if self.extras["rear"] > 0 and self.prac_on and self.behind(tr, x, y):
                s -= self.extras["rear"]
            if s < best_score:
                best_score, target = s, tr
        if target is not None:
            self.stick_id, self.stick_at = target["id"], t
        foe = target
        if foe is None and pp["peek"]:
            foe = hidden
        if foe is None and pp["pursue"] > 0 and hidden is not None and hidden["hp"] < pp["pursue"] * hidden["max_hp"]:
            foe = hidden

        danger = False
        crowd = 0
        for tr in seen:
            if tr["engage"] or t - tr["hit_me"] < 4:
                danger = True
            if tr["seen"] == t and (tr["engage"] or (tr["los"] and tr["dist"] < 150)):
                crowd += 1
        if danger or t - self.last_hurt < 3:
            self.last_threat = t
        finishing = target is not None and target["dist"] < 120 and (target["hp"] < 200 or target["hp"] < me["hp"] * 0.5)
        outgunned = (target is not None and self.holds(target["weapons"], "laser") and laser is None
                     and target["dist"] > 55 and hpf < 0.8)
        swamped = pp["crowd_hide"] and (crowd >= 3 or (crowd == 2 and hpf < 0.65) or outgunned)
        if not self.retreat and ((hpf < pp["retreat_hp"] and t - self.last_threat < 2) or swamped):
            self.retreat = True
            self.cover_at = -1
        if self.retreat and not swamped and (hpf > pp["recover_hp"] or (t - self.last_threat > 7 and hpf > 0.55)):
            self.retreat = False
        if pp["lose_rule"]:
            near = sum(1 for tr in seen if tr["seen"] == t and tr["dist"] < 160)
            losing = (near >= 2 and hpf < 0.55) or (near >= 3 and hpf < min(0.95, 0.8))
            if target is not None:
                tf = target["hp"] / max(1.0, target["max_hp"])
                if hpf < 0.35 and tf > hpf + 0.1:
                    losing = True
                if tf < 0.25 and hpf > 0.2 and near <= 2:
                    losing = False
            if losing:
                self.lose_t = t
            self.retreat = (t - self.lose_t < 1.5) and self.lose_t > 0

        mx = my = 0.0
        boost = False
        jump = False
        mode = "idle"
        farm = None
        farm_pos = None
        self.finish_range = None
        zgx, zgy = self.zone_goal(zone, x, y)
        zdist = hypot(zgx - x, zgy - y)
        t_need = zdist * 1.45 / ws + 4
        deadline = self.zone_deadline(zone, x, y, 8)
        zone_must = (not me["in_zone"]) or t + t_need + 3 >= deadline
        zone_should = t + t_need + 14 >= deadline

        shell = self.dodge_shell(obs, me)
        esc = self.escape_step(me, t) if self.extras["escape"] else None
        if esc is not None:
            mx, my, boost, esc_jump = esc
            jump = jump or esc_jump
            mode = "escape"
        elif t < self.unstuck_until:
            mx, my = self.unstuck_dir
            mode = "unstuck"
        elif shell is not None:
            mx, my = shell
            boost = energy > 15
            mode = "dodge"
        elif zone_must and zdist > 2:
            mx, my = self.travel(x, y, zf, zgx, zgy, t, T0)
            boost = ((not me["in_zone"]) or t + t_need >= deadline) and energy > 5
            mode = "zone"
        elif self.retreat and not finishing and not late:
            cm = self.seek_cover(obs, me, seen, T0)
            if cm is not None:
                mx, my = cm
                boost = energy > 10 and (mx != 0 or my != 0)
                mode = "cover"
            elif target is not None:
                mx, my = self.pick_spot(obs, me, target, seen, 1.0, wl, energy)
                mode = "cornered"
            else:
                mx, my = self.travel(x, y, zf, zgx, zgy, t, T0)
                mode = "flee"
        elif target is None and t - self.last_hurt < 2.5 and not late and pp["ghost"]:
            cm = self.hide_from_bearing(obs, me, seen, T0)
            if cm is not None:
                mx, my = cm
                boost = energy > 30 and (mx != 0 or my != 0)
                mode = "cover"
            else:
                foe = foe  # fall through to the normal branches below
        if mode == "idle" and foe is not None:
            ready = (gun is not None and gun.get("ammo", 0) > 0 and gun.get("reload", 0) <= 0.25
                     and foe["dist"] <= gun["stats"]["range"] - 10)
            hot = laser is not None and laser.get("charge", 0.0) >= laser["stats"]["charge"] - 0.3 and \
                foe["dist"] <= laser["stats"]["range"] - 5
            if hot or (light is not None and foe["dist"] <= light["stats"]["range"] + 6
                       and energy >= light["stats"].get("energy", 3.0) * 3):
                ready = True
            if not pp["peek"] and (light is not None or laser is not None):
                ready = True
            want_los = 1.0 if ready else -1.0
            if pp["peek"] and not hot:
                for tr in seen:
                    if tr["seen"] == t and tr["charging"] and abs(wrap(tr["aim"][0] - math.atan2(y - tr["pos"][1], x - tr["pos"][0]))) < 0.3:
                        want_los = -1.6
            fin_hp = 0.38
            if pp["finish"] > 0 and foe["hp"] < fin_hp * foe["max_hp"] and hpf > 0.42 and crowd <= 2:
                self.finish_range = pp["finish"]
            mx, my = self.pick_spot(obs, me, foe, seen, want_los, wl, energy)
            self.finish_range = None
            if light is not None and foe["dist"] > 50 and energy > 55 and want_los > 0:
                boost = True
            mode = "fight"
            if pp["fight_loot"] > 0:
                r = pp["fight_loot"] * (0.57 if hpf <= 0.5 else 1.0)
                bc = None
                for c in self.cube_mem.values():
                    d = hypot(c["pos"][0] - x, c["pos"][1] - y)
                    if d < r:
                        r, bc = d, c["pos"]
                if bc is not None:
                    mx, my = self.travel(x, y, zf, bc[0], bc[1], t, T0)
                    mode = "fight:cube"
            if self.extras["drops"] and self.prac_on and self.extras["fight_drop_r"] > 0 and not (finishing and hpf > 0.5):
                fd = self.fight_drop(obs, me, hpf)
                if fd is not None:
                    r = self.drop_radius(fd)
                    dd = hypot(fd["pos"][0] - x, fd["pos"][1] - y)
                    if dd > r - 3 or hypot(x + mx * 2 - fd["pos"][0], y + my * 2 - fd["pos"][1]) > r - 2.5:
                        mx, my = self.travel(x, y, zf, fd["pos"][0], fd["pos"][1], t, T0)
                    boost = dd > r + 4 and energy > 30
                    mode = "fight:drop"
        elif mode == "idle" and zone_should and zdist > 2:
            mx, my = self.travel(x, y, zf, zgx, zgy, t, T0)
            mode = "zone"
        elif mode == "idle":
            lc = self.pick_loot(obs, me, hpf, danger, wl)
            if lc is not None:
                mode = "loot:" + lc["kind"]
                if lc["kind"] == "npc":
                    n = self.npcs.get(lc["id"])
                    if n is not None and t - n["seen"] < 1 and n["los"] and n["dist"] < 75:
                        farm = n
                        mx, my = self.pick_spot(obs, me, n, seen, 1.0, wl, energy)
                    else:
                        mx, my = self.travel(x, y, zf, lc["pos"][0], lc["pos"][1], t, T0)
                elif lc["kind"] == "crate":
                    d = hypot(lc["pos"][0] - x, lc["pos"][1] - y)
                    ch = self.cfg["crates"].get("height", 3.0)
                    cp = (lc["pos"][0], lc["pos"][1], lc["pos"][2] + ch * 0.5)
                    if d < 50 and self.clear(x, y, zf + mzh, cp[0], cp[1], cp[2]):
                        farm_pos = cp
                        if d < 12:
                            mx, my = (x - lc["pos"][0]) / max(d, 0.1), (y - lc["pos"][1]) / max(d, 0.1)
                    else:
                        mx, my = self.travel(x, y, zf, lc["pos"][0], lc["pos"][1], t, T0)
                else:
                    mx, my = self.travel(x, y, zf, lc["pos"][0], lc["pos"][1], t, T0)
                    if lc["kind"] == "drop" and hypot(lc["pos"][0] - x, lc["pos"][1] - y) < 2.5:
                        mx = my = 0.0
            elif zdist > 3 and (not pp["ghost"] or zone["next_radius"] <= 30):
                mx, my = self.travel(x, y, zf, zgx, zgy, t, T0)
                mode = "zone-walk"
            elif pp["ghost"]:
                hm = self.home(obs, me)
                if hm is not None and hypot(hm[0] - x, hm[1] - y) > 3:
                    mx, my = self.travel(x, y, zf, hm[0], hm[1], t, T0)
                    if not danger and t - self.last_hurt > 6:
                        q = min(1.0, 4.6 / ws)
                        mx, my = mx * q, my * q
                    mode = "home"

        # ---- dodge blending
        if pp["dodge"] and mode not in ("unstuck", "escape"):
            dx, dy, lz = self.dodge_vec(obs, me)
            if dx != 0 or dy != 0:
                mx, my = mx * 0.4 + dx * 0.9, my * 0.4 + dy * 0.9
                l = hypot(mx, my)
                if l > 1:
                    mx, my = mx / l, my / l
                if lz and energy > 25:
                    boost = True

        if self.extras["hear"] and self.prac_on and t < self.hear_until and mode not in ("unstuck", "escape"):
            mx, my = mx * 0.4 + self.hear_dx * 0.9, my * 0.4 + self.hear_dy * 0.9
            l = hypot(mx, my)
            if l > 1:
                mx, my = mx / l, my / l
            if energy > 25 and me.get("grounded", True):
                boost = True

        # ---- stuck detection
        grounded = me.get("grounded", True)
        sp = hypot(me.get("vel", [0, 0, 0])[0], me.get("vel", [0, 0, 0])[1])
        if (mx != 0 or my != 0) and sp < 1.2 and grounded and mode not in ("unstuck", "escape"):
            if self.stuck_since < 0:
                self.stuck_since = t
            elif t - self.stuck_since > 0.7:
                a = self.rng.random() * 2 * PI
                self.unstuck_dir = (math.cos(a), math.sin(a))
                self.unstuck_until = t + 0.5
                self.stuck_since = -1.0
                self.path = None
                jump = True
        else:
            self.stuck_since = -1.0

        # ---- aiming and firing
        lat = self.LAT
        vel = me.get("vel", [0, 0, 0])
        muzzle = (x + vel[0] * lat, y + vel[1] * lat, zf + mzh)
        aim = [me["aim"][0], 0.0]
        have_aim = False
        fire = [False, False]
        tp = tv = None
        tr_r = th_h = 0.0
        shootable = False
        is_mech = False
        defend = False
        if target is None and self.npc_hurt > 0 and t - self.npc_hurt < 3:
            worst, best_off = None, 0.7
            for n in self.npcs.values():
                if t - n["seen"] > 0.5 or not n["los"] or n["dist"] > 150:
                    continue
                off = abs(wrap(math.atan2(n["pos"][1] - y, n["pos"][0] - x) - self.npc_bearing))
                if t - n["hit_me"] < 3:
                    off = 0.0
                if off < best_off:
                    best_off, worst = off, n
            if worst is not None:
                farm, farm_pos, defend = worst, None, True
        mc = self.cfg["mech"]
        if target is not None:
            sc = self.scale_of(target["cubes"])
            tr_r, th_h = mc["radius"] * sc, mc["height"] * sc
            tp = list(target["pos"])
            tv = target["vel"]
            tp[2] += th_h * 0.5
            if not self.clear(muzzle[0], muzzle[1], muzzle[2], tp[0], tp[1], tp[2]):
                tp[2] = target["pos"][2] + th_h * 0.85
            shootable, is_mech = True, True
        elif farm is not None:
            tr_r, th_h = self.cfg["npc"]["radius"], self.cfg["npc"]["height"]
            tp = list(farm["pos"])
            tv = farm["vel"]
            tp[2] += th_h * 0.5
            shootable = True
        elif farm_pos is not None:
            tr_r, th_h = self.cfg["crates"]["radius"], self.cfg["crates"]["height"]
            tp = list(farm_pos)
            tv = [0, 0, 0]
            shootable = True
        if not is_mech and target is None and (self.retreat or hpf < 0.5) and not defend:
            shootable = False

        if shootable:
            dist = hypot(tp[0] - x, tp[1] - y)
            grounded_t = abs(tv[2]) < 0.5
            gy = gp = 0.0
            gun_ok = False
            if gun is not None:
                spd = gun["stats"].get("speed", 252.0) or 252.0
                tt = 0.0
                px = py = pz = 0.0
                for _ in range(4):
                    ttl = lat + tt
                    px, py, pz = tp[0] + tv[0] * ttl, tp[1] + tv[1] * ttl, tp[2]
                    if not grounded_t:
                        pz += tv[2] * ttl * 0.5
                    dd = math.sqrt((px - muzzle[0]) ** 2 + (py - muzzle[1]) ** 2 + (pz - muzzle[2]) ** 2)
                    tt = max(0.0, dd - 3) / spd
                gy = math.atan2(py - muzzle[1], px - muzzle[0])
                gp = math.atan2(pz - muzzle[2], hypot(px - muzzle[0], py - muzzle[1]))
                gun_ok = dist <= gun["stats"]["range"] * 0.96
            dpx, dpy = tp[0] + tv[0] * (lat + 0.05), tp[1] + tv[1] * (lat + 0.05)
            hy = math.atan2(dpy - muzzle[1], dpx - muzzle[0])
            hp_ = math.atan2(tp[2] - muzzle[2], hypot(dpx - muzzle[0], dpy - muzzle[1]))
            aim = [gy, gp]
            if gun is None:
                aim = [hy, hp_]
            have_aim = True
            tol_y = math.atan2(tr_r * 0.75, max(dist, 1.0))
            tol_p = math.atan2(th_h * 0.4, max(dist, 1.0))

            def slew(wy, wp):
                ey = max(0.0, abs(wrap(wy - me["aim"][0])) - st.get("turn_rate", 4.0) * 0.05)
                ep = max(0.0, abs(wp - me["aim"][1]) - st.get("pitch_rate", 3.0) * 0.05)
                return ey < tol_y and ep < tol_p

            for i, wk in enumerate(wl):
                if wk is None or i > 1:
                    continue
                kd = wk["kind"]
                ws_ = wk["stats"]
                if kd == "gun":
                    if gun_ok and wk.get("ammo", 0) > 0 and wk.get("reload", 0) <= 0 and slew(gy, gp):
                        fire[i] = True
                elif kd == "lightning":
                    cone = ws_.get("cone_deg", 30.0) * PI / 180
                    if (dist < ws_["range"] - 1.5 and abs(wrap(hy - me["aim"][0])) < cone * 0.5 - 0.05
                            and energy >= ws_.get("energy", 3.0)):
                        fire[i] = True
                elif kd == "laser":
                    if not is_mech or dist > ws_["range"] * 0.97:
                        continue
                    full = ws_["charge"]
                    ch = wk.get("charge", 0.0)
                    if pp["lethal"] and ch >= ws_.get("min_charge", 0.15) and ch < full - 0.051:
                        mfr = ws_.get("min_frac", 0.35)
                        dmg = ws_["damage"] * (mfr + (1 - mfr) * ch / full) * \
                            (1 + self.cfg["cubes"].get("damage_per_cube", 0.04) * min(me["cubes"], int(self.cfg["cubes"].get("stat_cap", 10))))
                        if self.holds(target["weapons"], "mortar"):
                            dmg *= 1 + ws_.get("cookoff", 0.6)
                        rm = self.cfg["mech"].get("rear_mult", 1.0)
                        if self.extras["rear"] > 0 and self.prac_on and rm > 1 and self.behind(target, x, y):
                            dmg *= rm
                        if dmg * 0.8 >= target["hp"] and abs(wrap(hy - me["aim"][0])) < tol_y * 0.9 and abs(hp_ - me["aim"][1]) < tol_p:
                            aim = [hy, hp_]
                            fire[i] = False
                            continue
                    if ch < full - 0.051:
                        fire[i] = True
                        if ch > full * 0.45:
                            aim = [hy, hp_]
                    else:
                        aim = [hy, hp_]
                        ey = abs(wrap(hy - me["aim"][0]))
                        ep = abs(hp_ - me["aim"][1])
                        fire[i] = not (ey < tol_y * 0.9 and ep < tol_p)
        if target is None and foe is not None:
            for i, wk in enumerate(wl):
                if wk is not None and i < 2 and wk["kind"] == "laser" and wk.get("cooldown", 0) <= 0.05 \
                        and foe["dist"] < wk["stats"]["range"] \
                        and wk.get("charge", 0.0) < wk["stats"]["charge"] + wk["stats"].get("hold_s", 2.0) - 0.35:
                    fire[i] = True

        if not have_aim:
            watch = None
            for tr in seen:
                if tr["engage"] or t - tr["hit_me"] < 6:
                    if watch is None or tr["dist"] < watch["dist"]:
                        watch = tr
            if watch is not None:
                aim[0] = math.atan2(watch["pos"][1] - y, watch["pos"][0] - x)
            elif self.npc_hurt > 0 and t - self.npc_hurt < 2.5:
                aim[0] = self.npc_bearing
            elif t - self.last_hurt < 2.5:
                aim[0] = self.hurt_bearing
            elif self.extras["hear"] and self.prac_on and self.heard_at > 0 and t - self.heard_at < 2:
                aim[0] = self.heard_bearing
            elif mx != 0 or my != 0:
                aim[0] = math.atan2(my, mx) + 1.15 * math.sin(t * 1.3)
            else:
                aim[0] = me["aim"][0] + 0.35
            aim[1] = 0.0
        aim[1] = clamp(aim[1], mc.get("min_pitch", -1.2), mc.get("max_pitch", 1.2))
        aim[0] = wrap(aim[0])

        if gun is not None and gun.get("reload", 0) <= 0 and gun.get("ammo", 0) < gun["stats"].get("mag", 12):
            if target is None and farm is None and farm_pos is None and \
                    (gun["ammo"] <= gun["stats"].get("mag", 12) * 0.6 or t - self.last_threat > 3):
                act["reload"] = True

        slot1 = wl[1]["kind"] if len(wl) > 1 and wl[1] is not None else ""
        prad = self.cfg["loot"].get("pickup_radius", 4.0) - 0.3
        for p in obs["pickups"]:
            if hypot(p["pos"][0] - x, p["pos"][1] - y) > prad or abs(p["pos"][2] - zf) > 3.6:
                continue
            if not self.want_pickup(wl, p["kind"]):
                continue
            act["take"] = p["id"]
            if slot1 and len(wl) > 0 and wl[0] is not None:
                if slot1 == "laser" and wl[1].get("charge", 0.0) > 0:
                    act.pop("take", None)
                    break
                act["drop"] = 1
            break

        if jump:
            act["jump"] = True
        if not math.isfinite(mx) or not math.isfinite(my):
            mx = my = 0.0
        act["move"] = [round(mx, 4), round(my, 4)]
        act["aim"] = [round(aim[0], 4), round(aim[1], 4)]
        act["fire"] = fire
        act["boost"] = bool(boost and (mx != 0 or my != 0))
        self.mode = mode
        self.last_label = mode
        self.fight_reason = ("T" if target is not None else "H" if foe is not None else "-") + str(int(self.retreat)) + str(crowd)
        mf.draw.label(f"{mode} hp{me['hp']:.0f}")
        return act


mf.run(Soloist if P.get("brain", 1) else Bot)
