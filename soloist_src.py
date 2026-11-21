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
