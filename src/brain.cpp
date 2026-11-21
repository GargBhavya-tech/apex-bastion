#include "brain.hpp"
#include <cmath>
#include <algorithm>
#include <iostream>

namespace mech {

static const double LAT = 0.075;

static inline double ang_diff(double a, double b) {
    double d = std::fmod(a - b, 2.0 * M_PI);
    if (d > M_PI) d -= 2.0 * M_PI;
    else if (d < -M_PI) d += 2.0 * M_PI;
    return d;
}

static inline bool holds(const std::vector<std::string>& list, const std::string& kind) {
    return std::find(list.begin(), list.end(), kind) != list.end();
}

static inline std::pair<int, std::shared_ptr<WeaponState>> has_weapon(
    const std::vector<std::shared_ptr<WeaponState>>& ws, const std::string& kind) {
    for (size_t i = 0; i < ws.size(); i++) {
        if (ws[i] && ws[i]->kind == kind) {
            return {static_cast<int>(i), ws[i]};
        }
    }
    return {-1, nullptr};
}

static const std::vector<std::string> UPGRADE_ORDER = {
    "plating", "armor", "gun_damage", "nanites", "gun_rate", "lightning_efficiency", "lightning_range", "laser_damage",
    "servos", "laser_charge", "gun_mag", "gun_velocity", "gyros", "lightning_chain", "reactor", "capacitor",
    "mortar_reload", "mortar_splash", "mortar_velocity", "sensors", "jets", "laser_pierce"
};

static const std::vector<std::string> UPGRADE_ORDER_LASER = {
    "plating", "armor", "laser_damage", "laser_charge", "nanites", "gun_damage", "gun_rate", "lightning_efficiency", "lightning_range",
    "servos", "gun_mag", "gun_velocity", "gyros", "lightning_chain", "reactor", "capacitor",
    "mortar_reload", "mortar_splash", "mortar_velocity", "sensors", "jets", "laser_pierce"
};

static const std::vector<std::string> UPGRADE_ORDER_NANO = {
    "plating", "armor", "nanites", "laser_damage", "laser_charge", "gun_damage", "gun_rate", "lightning_efficiency", "lightning_range",
    "servos", "gun_mag", "gun_velocity", "gyros", "lightning_chain", "reactor", "capacitor",
    "mortar_reload", "mortar_splash", "mortar_velocity", "sensors", "jets", "laser_pierce"
};

static const std::vector<std::string> UPGRADE_ORDER_SPEED = {
    "plating", "armor", "servos", "jets", "reactor", "laser_damage", "laser_charge", "nanites", "gun_damage", "gun_rate", "lightning_efficiency", "lightning_range",
    "gun_mag", "gun_velocity", "gyros", "lightning_chain", "capacitor",
    "mortar_reload", "mortar_splash", "mortar_velocity", "sensors", "laser_pierce"
};

static int pick_upgrade(const Offer* of, bool laser_up, bool nano_up, bool speed_up) {
    const auto& order = speed_up ? UPGRADE_ORDER_SPEED :
                        (nano_up ? UPGRADE_ORDER_NANO :
                        (laser_up ? UPGRADE_ORDER_LASER : UPGRADE_ORDER));
    int best = 0, best_rank = 1 << 30;
    for (size_t i = 0; i < of->choices.size(); i++) {
        int rank = (int)order.size();
        for (size_t r = 0; r < order.size(); r++) {
            if (order[r] == of->choices[i].id) {
                rank = (int)r;
                break;
            }
        }
        if (rank < best_rank) {
            best = (int)i;
            best_rank = rank;
        }
    }
    return best;
}

static const std::map<std::string, int> WEAPON_RANK = {
    {"lightning", 3}, {"laser", 2}, {"mortar", 1}
};

Params default_params() {
    Params p;
    p.retreat_hp = 0.38;
    p.recover_hp = 0.8;
    p.gun_range = 85.0;
    p.light_range = 28.0;
    p.laser_range = 85.0;
    p.engage_dist = 60.0;
    p.farm_npc = true;
    p.explore = false;
    p.ghost = true;
    p.home_expo = 120.0;
    p.loot_radius = 90.0;
    p.crate_until = 150.0;
    p.use_drops = false;
    p.dodge = true;
    p.no_mortar = true;
    p.peek = true;
    p.laser_first = true;
    p.crowd_hide = true;
    p.practice = true;
    return p;
}

Params squad_params(Params p) {
    p.ghost = false;
    p.peek = false;
    p.laser_first = true;
    p.laser_range = 120.0;
    p.loot_radius = 150.0;
    p.crate_until = 1e9;
    p.stick = 120.0;
    p.hpw = 0.18;
    p.low_bonus = 200.0;
    p.max_target = 240.0;
    p.lose_rule = true;
    p.fight_loot = 70.0;
    p.farm_hp = 0.5;
    p.laser_seek = 240.0;
    p.laser_up = true;
    p.lethal = true;
    p.finish = 20.0;
    p.stick = 200.0;
    p.lethal_k = 0.7;
    return p;
}

Brain::Brain(const Hello& h, std::shared_ptr<World> world)
    : w(world), cfg(h.config), slot(h.slot), p(default_params()) {
    uint64_t seed = h.seed;
    if (seed == 0) seed = static_cast<uint64_t>(h.slot) + 1;
    rng.seed(seed);
}

double Brain::rand_float() {
    std::uniform_real_distribution<double> dist(0.0, 1.0);
    return dist(rng);
}

double Brain::scale_of(int cubes_count) const {
    return 1.0 + cfg.cubes.size_per_cube * static_cast<double>(cubes_count);
}

Vec3 Brain::center(const Track& t) const {
    double h = cfg.mech.height * scale_of(t.mech.cubes);
    if (t.mech.kind == "npc") h = cfg.npc.height;
    return {t.mech.pos[0], t.mech.pos[1], t.mech.pos[2] + h * 0.5};
}

Vec3 Brain::eye(const Track& t) const {
    return {t.mech.pos[0], t.mech.pos[1], t.mech.pos[2] + cfg.mech.eye_height * scale_of(t.mech.cubes)};
}

void Brain::observe(Obs* o) {
    auto& me = o->self;
    double t_now = o->t;
    if (me.stats.radius == 0.0) me.stats = cfg.mech;

    Vec3 my_eye = {me.pos[0], me.pos[1], me.pos[2] + me.stats.eye_height};
    Vec3 my_muzzle = {me.pos[0], me.pos[1], me.pos[2] + me.stats.muzzle_height};

    for (const auto& m : o->mechs) {
        auto& tab = (m.kind == "npc") ? npcs : tracks;
        auto it = tab.find(m.id);
        if (it == tab.end()) {
            Track tr;
            tr.hit_me = -100.0;
            tab[m.id] = tr;
            it = tab.find(m.id);
        }
        Track& tr = it->second;
        tr.mech = m;
        tr.seen = t_now;
        double dx = m.pos[0] - me.pos[0], dy = m.pos[1] - me.pos[1];
        tr.dist = std::hypot(dx, dy);
        Vec3 c = center(tr);
        tr.los = w->clear(my_muzzle, c);
        if (!tr.los && m.kind == "mech") {
            double h = cfg.mech.height * scale_of(m.cubes);
            tr.los = w->clear(my_muzzle, {m.pos[0], m.pos[1], m.pos[2] + h * 0.85});
        }
        if (tr.dist > 1.0) {
            tr.closing = -((m.vel[0] - me.vel[0]) * dx + (m.vel[1] - me.vel[1]) * dy) / tr.dist;
        }
    }

    for (auto it = tracks.begin(); it != tracks.end();) {
        if (t_now - it->second.seen > 20.0) it = tracks.erase(it);
        else ++it;
    }
    for (auto it = npcs.begin(); it != npcs.end();) {
        if (t_now - it->second.seen > 120.0) it = npcs.erase(it);
        else ++it;
    }

    auto upd = [&](std::map<int, Known>& tab, const std::vector<Item>& items) {
        for (const auto& it_item : items) {
            Known& k = tab[it_item.id];
            k.id = it_item.id;
            k.kind = it_item.kind;
            k.pos = it_item.pos;
            k.hp = it_item.hp;
            k.seen = t_now;
        }
        for (auto it = tab.begin(); it != tab.end();) {
            if (it->second.seen == t_now) {
                ++it;
                continue;
            }
            double d = std::hypot(it->second.pos[0] - me.pos[0], it->second.pos[1] - me.pos[1]);
            if (d < 40.0 && t_now - it->second.seen > 0.35 &&
                w->clear(my_eye, {it->second.pos[0], it->second.pos[1], it->second.pos[2] + 1.5})) {
                it = tab.erase(it);
            } else {
                ++it;
            }
        }
    };
    upd(crates, o->crates);
    upd(cubes, o->cubes);
    upd(pickups, o->pickups);

    for (const auto& e : o->events) {
        if (e.type == "damaged") {
            if (e.weapon == "npc" && e.bearing.has_value()) {
                npc_hurt = t_now;
                npc_bearing = e.bearing.value();
            }
            if (e.by.has_value()) {
                last_hurt = t_now;
                if (e.bearing.has_value()) hurt_bearing = e.bearing.value();
                auto it = tracks.find(e.by.value());
                if (it != tracks.end()) it->second.hit_me = t_now;
                auto nit = npcs.find(e.by.value());
                if (nit != npcs.end()) nit->second.hit_me = t_now;
            }
        } else if (e.type == "kill") {
            kills++;
            tracks.erase(e.target);
        }
    }

    if (!base_set) {
        base = p;
        base_set = true;
        start_alive = o->alive;
    }
    if (start_alive - o->alive - kills > 0) other_dead++;
    else other_dead = 0;
    if (other_dead >= 5) not_practice = true;

    bool on = base.practice && !not_practice && t_now > 20.0;
    if (on != prac_on) {
        prac_on = on;
        p = base;
        if (on) p = squad_params(base);
    }

    bool open = base.opening && !not_practice && !prac_on && (start_alive - o->alive - kills <= 0);
    if (open != open_on) {
        open_on = open;
        p = base;
        if (open) {
            p.laser_first = true;
            p.laser_seek = 240.0;
            p.loot_radius = 150.0;
        } else if (prac_on) {
            p = squad_params(base);
        }
    }

    auto& z = o->zone;
    if (hold_start != z.shrink_start) {
        hold_start = z.shrink_start;
        hold = Circle{z.center[0], z.center[1], z.radius};
    } else if (t_now <= z.shrink_start) {
        hold = Circle{z.center[0], z.center[1], z.radius};
    }
}

Circle Brain::zone_at(const Zone& z, double t) const {
    if (t <= z.shrink_start || z.shrink_end <= z.shrink_start) return hold;
    double f = std::clamp((t - z.shrink_start) / (z.shrink_end - z.shrink_start), 0.0, 1.0);
    return Circle{
        hold.x + (z.next_center[0] - hold.x) * f,
        hold.y + (z.next_center[1] - hold.y) * f,
        hold.r + (z.next_radius - hold.r) * f
    };
}

Circle Brain::cur_zone(const Zone& z) const {
    Circle live{z.center[0], z.center[1], z.radius};
    if (now <= z.shrink_start) return live;
    if (std::abs(live.r - hold.r) > 0.01 || std::abs(live.x - hold.x) > 0.01) return live;
    return zone_at(z, now);
}

double Brain::zone_deadline(const Zone& z, double x, double y, double pad) const {
    if (std::hypot(x - z.next_center[0], y - z.next_center[1]) <= z.next_radius - pad) {
        return std::numeric_limits<double>::infinity();
    }
    for (int k = 0; k <= 24; k++) {
        double t = z.shrink_start + (z.shrink_end - z.shrink_start) * static_cast<double>(k) / 24.0;
        Circle c = zone_at(z, t);
        if (std::hypot(x - c.x, y - c.y) > c.r - pad) return t;
    }
    return z.shrink_end;
}

double Brain::zone_penalty(const Zone& z, double x, double y) const {
    Circle c = cur_zone(z);
    double penalty = 0.0;
    double d = std::hypot(x - c.x, y - c.y) - c.r;
    if (d > -5.0) penalty += 150.0 + 5.0 * (d + 5.0);

    double dn = std::hypot(x - z.next_center[0], y - z.next_center[1]) - z.next_radius;
    if (dn > -5.0) {
        double soon = std::clamp(1.0 - (z.shrink_start - now) / 25.0, 0.1, 1.0);
        penalty += soon * (25.0 + 0.8 * (dn + 5.0));
    }
    return penalty;
}

std::pair<double, double> Brain::zone_goal(const Zone& z, double x, double y) const {
    double margin = std::clamp(0.3 * z.next_radius, 3.0, 30.0);
    if (z.next_radius <= 30.0) return {z.next_center[0], z.next_center[1]};
    double dx = x - z.next_center[0], dy = y - z.next_center[1];
    double d = std::hypot(dx, dy);
    if (d < 1.0) return {x, y};
    double r = std::max(0.0, z.next_radius - margin - 5.0);
    if (d <= r) return {x, y};
    return {z.next_center[0] + dx / d * r, z.next_center[1] + dy / d * r};
}

Action Brain::act(Obs* o) {
    Action act;
    act.tick = o->tick;
    try {
        step(o, &act);
    } catch (...) {
        panics++;
        act = Action{};
        act.tick = o->tick;
        act.aim = last_aim;
        return act;
    }
    if (act.aim.has_value()) {
        auto a = act.aim.value();
        if (std::isnan(a[0]) || std::isinf(a[0]) || std::isnan(a[1]) || std::isinf(a[1])) {
            act.aim.reset();
        } else {
            last_aim = a;
        }
    }
    if (std::isnan(act.move[0]) || std::isnan(act.move[1]) || std::isinf(act.move[0]) || std::isinf(act.move[1])) {
        act.move = {0.0, 0.0};
    }
    return act;
}

void Brain::step(Obs* o, Action* act) {
    auto& me = o->self;
    now = o->t;
    observe(o);
    const auto& st = me.stats;
    double x = me.pos[0], y = me.pos[1], zf = me.pos[2];
    auto& z = o->zone;
    double hp_frac = me.hp / std::max(1.0, me.max_hp);

    if (o->offer && !o->offer->choices.empty()) {
        int pick = pick_upgrade(o->offer.get(), p.laser_up, p.nano_up, p.speed_up);
        act->pick = pick;
    }

    auto [_, gun] = has_weapon(me.weapons, "gun");
    auto [__, light] = has_weapon(me.weapons, "lightning");
    auto [___, laser] = has_weapon(me.weapons, "laser");
    bool late = (z.next_radius <= 70.0 || o->alive <= 3);

    std::vector<Track*> seen;
    Track* target = nullptr;
    Track* hidden = nullptr;
    Track* shy = nullptr;
    double best_score = std::numeric_limits<double>::infinity();
    double max_t = (p.max_target > 0.0) ? p.max_target : 215.0;
    double hpw = (p.hpw > 0.0) ? p.hpw : (60.0 / 1400.0);

    for (auto& [id, t] : tracks) {
        if (now - t.seen > 2.5) continue;
        t.engage = false;
        if (t.seen == now) {
            seen.push_back(&t);
        } else {
            seen.push_back(&t);
            t.los = false;
            continue;
        }
        double to_me = std::atan2(y - t.mech.pos[1], x - t.mech.pos[0]);
        bool aimed = std::abs(ang_diff(t.mech.aim[0], to_me)) < 0.22;

        if (p.ghost) {
            t.engage = (t.dist < p.engage_dist) || (now - t.hit_me < 4.0) ||
                       (aimed && t.mech.charging && t.dist < 120.0) ||
                       (t.mech.hp < 350.0 && t.dist < 120.0) || (o->alive <= 2);
            double off = std::abs(ang_diff(t.mech.aim[0], to_me));
            if (p.vulture > 0.0 && hp_frac > 0.75 && t.mech.hp < p.vulture * t.mech.max_hp && off > 0.6 && t.dist < 165.0) {
                t.engage = true;
            }
            if (p.alert > 0.0 && t.los && t.dist < p.alert && (t.closing > 3.0 || aimed)) {
                t.engage = true;
            }
            if (p.shy > 0.0 && t.los && t.dist < p.shy && t.dist >= p.engage_dist && (t.closing > 3.0 || aimed) && !t.engage &&
                (!shy || t.dist < shy->dist)) {
                shy = &t;
            }
            if (p.ambush > 0.0 && hp_frac > 0.85 && off > 1.75 && t.dist < p.ambush) {
                t.engage = true;
            }
            if (p.odds > 0.0 && !t.engage && t.los && hp_frac > 0.5 && t.dist < reach(&me) && odds(&me, t, now, true) >= p.odds) {
                t.engage = true;
            }
        } else if (p.all_foes && t.dist < max_t) {
            t.engage = true;
        } else if (t.dist < p.engage_dist || now - t.hit_me < 6.0 || late) {
            t.engage = true;
        } else if (t.closing > 3.0 && t.dist < 180.0) {
            t.engage = true;
        } else if (t.mech.hp < 0.4 * t.mech.max_hp && t.dist < 160.0) {
            t.engage = true;
        } else if (aimed && t.dist < 190.0) {
            t.engage = true;
        }

        if (t.engage && !t.los && t.dist < max_t && (!hidden || t.dist < hidden->dist)) {
            hidden = &t;
        }
        if (!t.engage || !t.los || t.dist > max_t) continue;

        double s = t.dist + hpw * t.mech.hp;
        if (p.low_bonus > 0.0 && t.mech.hp <= 0.3 * t.mech.max_hp) s -= p.low_bonus;
        if (p.stick > 0.0 && t.mech.id == stick_id && now - stick_at < 2.0) s -= p.stick;
        if (p.backstab > 0.0 && shows_back(t, x, y)) s -= p.backstab;
        if (now - t.hit_me < 4.0) s -= 40.0;
        if (t.closing > 3.0) s -= 15.0;
        if (s < best_score) {
            best_score = s;
            target = &t;
        }
    }

    if (target) {
        stick_id = target->mech.id;
        stick_at = now;
    }
    Track* foe = target;
    if (!foe && p.peek) foe = hidden;
    if (!foe && p.pursue > 0.0 && hidden && hidden->mech.hp < p.pursue * hidden->mech.max_hp) foe = hidden;

    bool danger = false;
    int crowd = 0;
    for (auto* t : seen) {
        if (t->engage || now - t->hit_me < 4.0) danger = true;
        if (t->seen == now && (t->engage || (t->los && t->dist < 150.0))) crowd++;
    }
    if (danger || now - last_hurt < 3.0) last_threat_at = now;

    bool finishing = target && target->dist < 120.0 && (target->mech.hp < 200.0 || target->mech.hp < me.hp * 0.5);
    auto [____, my_laser] = has_weapon(me.weapons, "laser");
    bool outgunned = target && holds(target->mech.weapons, "laser") && !my_laser && target->dist > 55.0 && hp_frac < 0.8;
    bool swamped = p.crowd_hide && (crowd >= 3 || (crowd == 2 && hp_frac < 0.65) || outgunned);
    if (p.odds_flee > 0.0 && target && !finishing && odds(&me, *target, now, false) < p.odds_flee) {
        odds_flee_until = now + 5.0;
    }
    if (now < odds_flee_until && !finishing) swamped = true;
    if (!retreat && ((hp_frac < p.retreat_hp && now - last_threat_at < 2.0) || swamped)) {
        retreat = true;
        cover_at = -1.0;
    }
    if (retreat && !swamped && (hp_frac > p.recover_hp || (now - last_threat_at > 7.0 && hp_frac > 0.55))) {
        retreat = false;
    }

    if (p.lose_rule) {
        int near_count = 0;
        for (auto* t : seen) {
            if (t->seen == now && t->dist < 160.0) near_count++;
        }
        bool losing = (near_count >= 2 && hp_frac < 0.55) || (near_count >= 3 && hp_frac < 0.8);
        if (target) {
            double tf = target->mech.hp / std::max(1.0, target->mech.max_hp);
            if (hp_frac < 0.35 && tf > hp_frac + 0.1) losing = true;
            if (tf < 0.25 && hp_frac > 0.2 && near_count <= 2) losing = false;
        }
        if (losing) lose_at = now;
        retreat = (now - lose_at < 1.5 && lose_at > 0.0);
    }

    bool exposed = false;
    for (auto* t : seen) {
        if (t->seen == now && t->los && t->dist < 230.0) exposed = true;
    }
    for (auto* t : seen) {
        if (t->seen == now && t->dist < 45.0) exposed = false;
    }

    double mx = 0.0, my = 0.0;
    bool boost = false;
    std::string new_mode = "idle";
    Track* farm = nullptr;
    const Vec3* farm_pos = nullptr;
    Vec3 farm_pos_val{};

    auto [zgx, zgy] = zone_goal(z, x, y);
    double zdist = std::hypot(zgx - x, zgy - y);
    double t_need = zdist * 1.45 / st.walk_speed + 4.0;
    double deadline = zone_deadline(z, x, y, 8.0);
    bool zone_must = !me.in_zone || (now + t_need + 3.0 >= deadline);
    bool zone_should = now + t_need + 14.0 >= deadline;
    bool esc_jump = false;

    if (escape(&me, &mx, &my, &boost, &esc_jump)) {
        new_mode = "escape";
    } else if (now < unstuck_until) {
        mx = unstuck_dir[0];
        my = unstuck_dir[1];
        new_mode = "unstuck";
    } else if (dodge_shell(o, &mx, &my)) {
        boost = me.energy > 15.0;
        new_mode = "dodge";
    } else if (zone_must && zdist > 2.0) {
        std::tie(mx, my) = travel(&me, zgx, zgy);
        boost = (!me.in_zone || now + t_need >= deadline) && me.energy > 5.0;
        new_mode = "zone";
    } else if (retreat && !finishing && !late) {
        if (cover_move(o, seen, &mx, &my)) {
            boost = me.energy > 10.0 && (mx != 0.0 || my != 0.0);
            new_mode = "cover";
        } else if (target) {
            std::tie(mx, my) = fight_move(o, target, seen, 1.0);
            new_mode = "cornered";
        } else {
            std::tie(mx, my) = travel(&me, zgx, zgy);
            if (npc_hurt > 0.0 && now - npc_hurt < 3.0 && mx == 0.0 && my == 0.0) {
                double side = (std::fmod(now, 3.0) > 1.5) ? -1.0 : 1.0;
                mx = -std::sin(npc_bearing) * side;
                my = std::cos(npc_bearing) * side;
            }
            new_mode = "flee";
        }
    } else if (!target && now - last_hurt < 2.5 && !late && p.ghost && hide_from_bearing(o, seen, &mx, &my)) {
        boost = me.energy > 30.0 && (mx != 0.0 || my != 0.0);
        new_mode = "cover";
    } else if (now < p.early_hide && exposed && !finishing && cover_move(o, seen, &mx, &my)) {
        boost = me.energy > 20.0 && (mx != 0.0 || my != 0.0);
        new_mode = "earlyhide";
    } else if (!foe && shy && !late && cover_move(o, seen, &mx, &my)) {
        boost = me.energy > 40.0 && (mx != 0.0 || my != 0.0);
        new_mode = "shy";
    } else if (p.evade && foe && !late && !finishing && foe->dist > p.engage_dist * 1.2 &&
               foe->mech.hp > 0.45 * foe->mech.max_hp && cover_move(o, seen, &mx, &my)) {
        boost = me.energy > 30.0 && (mx != 0.0 || my != 0.0);
        new_mode = "evade";
    } else if (foe) {
        bool ready = (gun && gun->ammo > 0.0 && gun->reload <= 0.25 && foe->dist <= gun->stats.range - 10.0);
        bool hot = (laser && laser->charge >= laser->stats.charge - 0.3 && foe->dist <= laser->stats.range - 5.0);
        if (hot || (light && foe->dist <= light->stats.range + 6.0 && me.energy >= light->stats.energy * 3.0)) {
            ready = true;
        }
        if (!p.peek && (light || laser)) ready = true;
        double want_los = ready ? 1.0 : -1.0;
        if (p.peek && !hot) {
            for (auto* t : seen) {
                if (t->seen == now && t->mech.charging &&
                    std::abs(ang_diff(t->mech.aim[0], std::atan2(y - t->mech.pos[1], x - t->mech.pos[0]))) < 0.3) {
                    want_los = -1.6;
                }
            }
        }
        double fin_hp = (p.finish_hp > 0.0) ? p.finish_hp : 0.38;
        if (p.finish > 0.0 && foe->mech.hp < fin_hp * foe->mech.max_hp && hp_frac > 0.42 && crowd <= 2) {
            Params keep = p;
            p.gun_range = p.finish;
            p.laser_range = p.finish;
            p.light_range = p.finish;
            std::tie(mx, my) = fight_move(o, foe, seen, want_los);
            p = keep;
            if (p.finish_rush && foe->dist > 2.0 * p.finish && me.energy > 30.0) boost = true;
        } else {
            std::tie(mx, my) = fight_move(o, foe, seen, want_los);
        }
        if (light && foe->dist > 50.0 && me.energy > 55.0 && want_los > 0.0) boost = true;
        new_mode = "fight";
        if (p.fight_boost > 0.0 && me.energy > p.fight_boost && (!laser || laser->charge <= 0.0) && (!light || me.energy > 60.0)) {
            boost = true;
        }
        if (p.fight_loot > 0.0) {
            double r = p.fight_loot;
            if (hp_frac <= 0.5) r *= 0.57;
            const Vec3* bc = nullptr;
            for (const auto& [_, c] : cubes) {
                double d = std::hypot(c.pos[0] - x, c.pos[1] - y);
                if (d < r) {
                    r = d;
                    bc = &c.pos;
                }
            }
            if (bc) {
                std::tie(mx, my) = travel(&me, (*bc)[0], (*bc)[1]);
                new_mode = "fight:cube";
            }
        }
    } else if (zone_should && zdist > 2.0) {
        std::tie(mx, my) = travel(&me, zgx, zgy);
        new_mode = "zone";
    } else {
        auto lc = choose_loot(o, hp_frac, danger);
        if (lc.has_value()) {
            new_mode = "loot:" + lc->kind;
            if (lc->kind == "npc") {
                auto it = npcs.find(lc->id);
                if (it != npcs.end() && now - it->second.seen < 1.0 && it->second.los && it->second.dist < 75.0) {
                    farm = &it->second;
                    std::tie(mx, my) = fight_move(o, farm, seen, 1.0);
                } else {
                    std::tie(mx, my) = travel(&me, lc->pos[0], lc->pos[1]);
                }
            } else if (lc->kind == "crate") {
                double d = std::hypot(lc->pos[0] - x, lc->pos[1] - y);
                farm_pos_val = Vec3{lc->pos[0], lc->pos[1], lc->pos[2] + cfg.crates.height * 0.5};
                if (d < 50.0 && w->clear({x, y, zf + st.muzzle_height}, farm_pos_val)) {
                    farm_pos = &farm_pos_val;
                    if (d < 12.0) {
                        mx = (x - lc->pos[0]) / std::max(d, 0.1);
                        my = (y - lc->pos[1]) / std::max(d, 0.1);
                    }
                } else {
                    std::tie(mx, my) = travel(&me, lc->pos[0], lc->pos[1]);
                }
            } else {
                std::tie(mx, my) = travel(&me, lc->pos[0], lc->pos[1]);
                if (lc->kind == "drop" && std::hypot(lc->pos[0] - x, lc->pos[1] - y) < 2.5) {
                    mx = 0.0;
                    my = 0.0;
                }
            }
        } else if (zdist > 3.0 && (!p.ghost || z.next_radius <= 30.0)) {
            std::tie(mx, my) = travel(&me, zgx, zgy);
            new_mode = "zone-walk";
        } else if (p.ghost) {
            auto [hx, hy, ok] = home(o);
            if (ok && std::hypot(hx - x, hy - y) > 3.0) {
                std::tie(mx, my) = travel(&me, hx, hy);
                if (!danger && now - last_hurt > 6.0 && !open_on) {
                    double q = std::min(1.0, 4.6 / st.walk_speed);
                    mx *= q;
                    my *= q;
                }
                new_mode = "home";
            }
        } else if (p.explore && !late && me.cubes < cube_cap() && hp_frac > 0.7 && !danger) {
            std::tie(mx, my) = explore_move(o);
            new_mode = "explore";
        }
    }

    if (esc_jump) act->jump = true;

    if (p.dodge && new_mode != "unstuck" && new_mode != "escape") {
        auto [dx, dy, lz] = dodge(o);
        if (dx != 0.0 || dy != 0.0) {
            mx = mx * 0.4 + dx * 0.9;
            my = my * 0.4 + dy * 0.9;
            double l = std::hypot(mx, my);
            if (l > 1.0) {
                mx /= l;
                my /= l;
            }
            if (lz && me.energy > 25.0) boost = true;
            if (p.dodge_boost > 0.0 && me.energy > p.dodge_boost) boost = true;
        }
    }
    if (p.threat_boost > 0.0 && me.energy > p.threat_boost && (foe || now - last_hurt < 2.5) && (!light || me.energy > 60.0)) {
        boost = true;
    }

    if (new_mode == "escape") {
        stuck_since = -1.0;
    } else if ((mx != 0.0 || my != 0.0) && std::hypot(me.vel[0], me.vel[1]) < 1.2 && me.grounded) {
        if (stuck_since < 0.0) {
            stuck_since = now;
        } else if (now - stuck_since > 0.7) {
            double a = rand_float() * 2.0 * M_PI;
            unstuck_dir = {std::cos(a), std::sin(a)};
            unstuck_until = now + 0.5;
            stuck_since = -1.0;
            path.clear();
            act->jump = true;
        }
    } else {
        stuck_since = -1.0;
    }

    Vec3 muzzle = {x + me.vel[0] * LAT, y + me.vel[1] * LAT, zf + st.muzzle_height};
    Vec2 aim = {me.aim[0], 0.0};
    bool have_aim = false;
    Vec3 tp{}, tv{};
    double tr = 0.0, th = 0.0;
    bool shootable = false;
    bool is_mech = false;
    bool defend = false;

    if (!target && npc_hurt > 0.0 && now - npc_hurt < 3.0) {
        Track* worst = nullptr;
        double best_off = 0.7;
        for (auto& [_, n] : npcs) {
            if (now - n.seen > 0.5 || !n.los || n.dist > 150.0) continue;
            double off = std::abs(ang_diff(std::atan2(n.mech.pos[1] - y, n.mech.pos[0] - x), npc_bearing));
            if (now - n.hit_me < 3.0) off = 0.0;
            if (off < best_off) {
                best_off = off;
                worst = &n;
            }
        }
        if (worst) {
            farm = worst;
            farm_pos = nullptr;
            defend = true;
        }
    }

    if (p.econ && !target && !farm && !farm_pos && gun && !retreat) {
        double reach_dist = 110.0;
        for (const auto& [_, t] : tracks) {
            if (now - t.seen < 4.0) reach_dist = 50.0;
        }
        for (const auto& [cid, c] : crates) {
            auto bit = bad.find(cid);
            if (bit != bad.end() && bit->second > now) continue;
            double d = std::hypot(c.pos[0] - x, c.pos[1] - y);
            Vec3 cp = {c.pos[0], c.pos[1], c.pos[2] + cfg.crates.height * 0.5};
            if (d < reach_dist && d > 6.0 && w->clear(muzzle, cp)) {
                reach_dist = d;
                farm_pos_val = cp;
                farm_pos = &farm_pos_val;
            }
        }
    }

    if (target) {
        double sc = scale_of(target->mech.cubes);
        tr = cfg.mech.radius * sc;
        th = cfg.mech.height * sc;
        tp = target->mech.pos;
        tv = target->mech.vel;
        tp[2] += th * 0.5;
        if (!w->clear(muzzle, tp)) {
            tp[2] = target->mech.pos[2] + th * 0.85;
        }
        shootable = true;
        is_mech = true;
    } else if (farm) {
        tr = cfg.npc.radius;
        th = cfg.npc.height;
        tp = farm->mech.pos;
        tv = farm->mech.vel;
        tp[2] += th * 0.5;
        shootable = true;
    } else if (farm_pos) {
        tr = cfg.crates.radius;
        th = cfg.crates.height;
        tp = *farm_pos;
        shootable = true;
    }

    if (!is_mech && !target && (retreat || hp_frac < 0.5) && !p.econ && !defend) {
        shootable = false;
    }

    if (shootable) {
        double dist = std::hypot(tp[0] - x, tp[1] - y);
        bool grounded = std::abs(tv[2]) < 0.5;
        double gy = 0.0, gp = 0.0;
        bool gun_ok = false;
        if (gun) {
            std::tie(gy, gp) = lead(muzzle, tp, tv, gun->stats.speed, grounded);
            gun_ok = (dist <= gun->stats.range * 0.96);
        }

        Vec3 dp = {tp[0] + tv[0] * (LAT + 0.05), tp[1] + tv[1] * (LAT + 0.05), tp[2]};
        double hy = std::atan2(dp[1] - muzzle[1], dp[0] - muzzle[0]);
        double hp = std::atan2(dp[2] - muzzle[2], std::hypot(dp[0] - muzzle[0], dp[1] - muzzle[1]));

        aim = {gy, gp};
        if (!gun) aim = {hy, hp};
        have_aim = true;

        double tol_y = std::atan2(tr * 0.75, std::max(dist, 1.0));
        double tol_p = std::atan2(th * 0.4, std::max(dist, 1.0));

        auto slew = [&](double want_y, double want_p) -> bool {
            double ey = std::max(0.0, std::abs(ang_diff(want_y, me.aim[0])) - st.turn_rate * 0.05);
            double ep = std::max(0.0, std::abs(want_p - me.aim[1]) - st.pitch_rate * 0.05);
            return ey < tol_y && ep < tol_p;
        };

        for (size_t i = 0; i < me.weapons.size() && i < 2; i++) {
            auto& weapon = me.weapons[i];
            if (!weapon) continue;

            if (weapon->kind == "gun") {
                if (gun_ok && weapon->ammo > 0.0 && weapon->reload <= 0.0 && slew(gy, gp)) {
                    act->fire[i] = true;
                }
            } else if (weapon->kind == "lightning") {
                double cone = weapon->stats.cone_deg * M_PI / 180.0;
                if (dist < weapon->stats.range - 1.5 && std::abs(ang_diff(hy, me.aim[0])) < cone * 0.5 - 0.05 &&
                    me.energy >= weapon->stats.energy) {
                    act->fire[i] = true;
                }
            } else if (weapon->kind == "laser") {
                if (!is_mech || dist > weapon->stats.range * 0.97) continue;
                double full = weapon->stats.charge;
                if (p.lethal && weapon->charge >= weapon->stats.min_charge && weapon->charge < full - 0.051) {
                    double dmg = weapon->stats.damage * (weapon->stats.min_frac + (1.0 - weapon->stats.min_frac) * weapon->charge / full) *
                                 (1.0 + cfg.cubes.damage_per_cube * static_cast<double>(std::min(me.cubes, cfg.cubes.stat_cap)));
                    if (target && holds(target->mech.weapons, "mortar")) dmg *= (1.0 + weapon->stats.cookoff);
                    double lk = (p.lethal_k > 0.0) ? p.lethal_k : 0.8;
                    if (p.backstab > 0.0 && target && shows_back(*target, x, y)) dmg *= rear_mult();
                    if (target && dmg * lk >= target->mech.hp && std::abs(ang_diff(hy, me.aim[0])) < tol_y * 0.9 &&
                        std::abs(hp - me.aim[1]) < tol_p) {
                        aim = {hy, hp};
                        act->fire[i] = false;
                        continue;
                    }
                }
                if (weapon->charge < full - 0.051) {
                    act->fire[i] = true;
                    if (weapon->charge > full * 0.45) aim = {hy, hp};
                } else {
                    aim = {hy, hp};
                    double ey = std::abs(ang_diff(hy, me.aim[0]));
                    double ep = std::abs(hp - me.aim[1]);
                    if (ey < tol_y * 0.9 && ep < tol_p) {
                        act->fire[i] = false;
                    } else {
                        act->fire[i] = true;
                    }
                }
            } else if (weapon->kind == "mortar") {
                if (!is_mech || weapon->cooldown > 0.25 || dist < 16.0 || dist > 200.0) continue;
                Vec3 tube = {muzzle[0], muzzle[1], zf + st.height + 0.5};
                Vec3 foot = {tp[0], tp[1], tp[2] - th * 0.5};
                auto [my2, mp, ok] = mortar(tube, foot, tv, weapon->stats.speed, weapon->stats.gravity, st);
                if (ok) {
                    if (!gun || gun->reload > 0.0 || gun->ammo == 0.0 || !gun_ok) {
                        aim = {my2, mp};
                    }
                    double ey = std::max(0.0, std::abs(ang_diff(my2, me.aim[0])) - st.turn_rate * 0.05);
                    double ep = std::max(0.0, std::abs(mp - me.aim[1]) - st.pitch_rate * 0.05);
                    if (ey < 0.04 && ep < 0.03) {
                        act->fire[i] = true;
                    }
                }
            }
        }
    }

    if (!target && foe) {
        for (size_t i = 0; i < me.weapons.size() && i < 2; i++) {
            auto& weapon = me.weapons[i];
            if (weapon && weapon->kind == "laser" && weapon->cooldown <= 0.05 && foe->dist < weapon->stats.range &&
                weapon->charge < weapon->stats.charge + weapon->stats.hold_s - 0.35) {
                act->fire[i] = true;
            }
        }
    }

    if (!have_aim) {
        Track* watch = nullptr;
        for (auto* t : seen) {
            if (t->engage || now - t->hit_me < 6.0) {
                if (!watch || t->dist < watch->dist) watch = t;
            }
        }
        if (watch) {
            aim[0] = std::atan2(watch->mech.pos[1] - y, watch->mech.pos[0] - x);
        } else if (npc_hurt > 0.0 && now - npc_hurt < 2.5) {
            aim[0] = npc_bearing;
        } else if (now - last_hurt < 2.5) {
            aim[0] = hurt_bearing;
        } else if (mx != 0.0 || my != 0.0) {
            aim[0] = std::atan2(my, mx) + 1.15 * std::sin(now * 1.3);
        } else {
            aim[0] = me.aim[0] + 0.35;
        }
        aim[1] = 0.0;
    }

    aim[1] = std::clamp(aim[1], st.min_pitch, st.max_pitch);
    act->aim = aim;

    if (gun && gun->reload <= 0.0 && gun->ammo < gun->stats.mag) {
        if (!target && !farm && !farm_pos && (gun->ammo <= gun->stats.mag * 0.6 || now - last_threat_at > 3.0)) {
            act->reload = true;
        }
    }

    std::string slot1 = "";
    if (me.weapons.size() > 1 && me.weapons[1]) {
        slot1 = me.weapons[1]->kind;
    }
    for (const auto& p_item : o->pickups) {
        if (std::hypot(p_item.pos[0] - x, p_item.pos[1] - y) > cfg.loot.pickup_radius - 0.3 ||
            std::abs(p_item.pos[2] - zf) > 3.6) {
            continue;
        }
        if (!want_pickup(&me, p_item.kind)) continue;
        act->take = p_item.id;
        if (!slot1.empty() && !me.weapons.empty() && me.weapons[0]) {
            if (slot1 == "laser" && me.weapons[1]->charge > 0.0) {
                act->take.reset();
                break;
            }
            act->drop = 1;
        }
        break;
    }

    act->move = {mx, my};
    act->boost = boost && (mx != 0.0 || my != 0.0);
    mode = new_mode;
}

bool Brain::escape(const Self* me, double* mx, double* my, bool* boost, bool* jump) {
    double x = me->pos[0], y = me->pos[1], zf = me->pos[2];
    if (me->grounded) {
        if (zf - w->ground_at(x, y) > 3.0 && w->obst[w->vidx(x, y)]) {
            esc_ok = false;
            esc_flying = false;
            return false;
        }
        if (!w->off_main(x, y)) {
            esc_ok = false;
            esc_flying = false;
            return false;
        }
        esc_flying = false;
        if (!esc_ok || now - esc_at > 6.0) {
            auto [launch, land, ok] = w->escape_plan(x, y);
            esc_launch = launch;
            esc_land = land;
            esc_ok = ok;
            esc_at = now;
            if (!esc_ok) return false;
        }
        if (std::hypot(esc_launch[0] - x, esc_launch[1] - y) > 2.5) {
            std::tie(*mx, *my) = travel(me, esc_launch[0], esc_launch[1]);
            return true;
        }
        if (me->energy < std::min(70.0, me->max_energy * 0.7)) {
            *mx = 0.0;
            *my = 0.0;
            return true;
        }
        esc_flying = true;
        *jump = true;
    } else if (!esc_flying) {
        return false;
    }

    double dx = esc_land[0] - x, dy = esc_land[1] - y;
    double d = std::hypot(dx, dy);
    if (d < 1.5) return true;
    *mx = dx / d;
    *my = dy / d;
    double need = -1e9;
    for (double t = 0.0; t <= std::min(d, 30.0); t += 1.0) {
        need = std::max(need, w->top_at(x + *mx * t, y + *my * t));
    }
    *boost = (zf < need + 2.5 && me->energy > 1.0);
    return true;
}

bool Brain::want_pickup(const Self* me, const std::string& kind) const {
    if (kind == "gun") {
        return !me->weapons.empty() && !me->weapons[0];
    }
    auto [idx, _] = has_weapon(me->weapons, kind);
    if (idx >= 0) return false;
    if (kind == "mortar" && p.no_mortar) return false;

    auto rank = [&](const std::string& k) -> int {
        if (p.laser_first && k == "laser") return 4;
        auto it = WEAPON_RANK.find(k);
        return (it != WEAPON_RANK.end()) ? it->second : 0;
    };
    int cur = 0;
    if (me->weapons.size() > 1 && me->weapons[1]) {
        cur = rank(me->weapons[1]->kind);
    }
    return rank(kind) > cur;
}

std::pair<double, double> Brain::lead(const Vec3& muzzle, const Vec3& tp, const Vec3& tv, double speed, bool grounded) const {
    if (speed <= 0.0) speed = 252.0;
    double t = 0.0;
    double px = tp[0], py = tp[1], pz = tp[2];
    for (int k = 0; k < 4; k++) {
        double tt = LAT + t;
        px = tp[0] + tv[0] * tt;
        py = tp[1] + tv[1] * tt;
        pz = tp[2];
        if (!grounded) pz += tv[2] * tt * 0.5;
        double d = std::sqrt((px - muzzle[0]) * (px - muzzle[0]) +
                             (py - muzzle[1]) * (py - muzzle[1]) +
                             (pz - muzzle[2]) * (pz - muzzle[2]));
        t = std::max(0.0, d - 3.0) / speed;
    }
    return {std::atan2(py - muzzle[1], px - muzzle[0]),
            std::atan2(pz - muzzle[2], std::hypot(px - muzzle[0], py - muzzle[1]))};
}

std::tuple<double, double, bool> Brain::mortar(const Vec3& tube, const Vec3& foot, const Vec3& tv,
                                               double v, double g, const MechStats& st) const {
    if (v <= 0.0 || g <= 0.0) return {0.0, 0.0, false};
    double t = 0.0;
    double pitch = 0.0, yaw = 0.0;
    for (int k = 0; k < 3; k++) {
        double px = foot[0] + tv[0] * (LAT + t);
        double py = foot[1] + tv[1] * (LAT + t);
        double dx = std::hypot(px - tube[0], py - tube[1]);
        double dz = foot[2] - tube[2];
        double disc = v * v * v * v - g * (g * dx * dx + 2.0 * dz * v * v);
        if (disc < 0.0 || dx < 1.0) return {0.0, 0.0, false};
        pitch = std::atan((v * v - std::sqrt(disc)) / (g * dx));
        yaw = std::atan2(py - tube[1], px - tube[0]);
        t = dx / (v * std::cos(pitch));
    }
    if (pitch < st.min_pitch || pitch > st.max_pitch) return {0.0, 0.0, false};

    double c = std::cos(pitch), s = std::sin(pitch);
    for (double tt = 0.1; tt < t * 0.9; tt += 0.1) {
        double d = v * c * tt;
        double px = tube[0] + std::cos(yaw) * d;
        double py = tube[1] + std::sin(yaw) * d;
        double pz = tube[2] + v * s * tt - 0.5 * g * tt * tt;
        if (w->solid(px, py, pz)) return {0.0, 0.0, false};
    }
    return {yaw, pitch, true};
}

bool Brain::dodge_shell(Obs* o, double* mx, double* my) {
    auto& me = o->self;
    double g = 22.0;
    auto it = cfg.weapons.find("mortar");
    if (it != cfg.weapons.end() && it->second.gravity > 0.0) g = it->second.gravity;
    double splash_r = 12.0;
    if (it != cfg.weapons.end()) splash_r = it->second.splash_radius;
    double rad = splash_r + me.stats.radius + 2.0;

    for (const auto& p_proj : o->projectiles) {
        if (p_proj.kind != "mortar") continue;
        double px = p_proj.pos[0], py = p_proj.pos[1], pz = p_proj.pos[2];
        double vz = p_proj.vel[2];
        for (double t = 0.0; t < 4.0; t += 0.05) {
            px += p_proj.vel[0] * 0.05;
            py += p_proj.vel[1] * 0.05;
            pz += vz * 0.05;
            vz -= g * 0.05;
            if (w->solid(px, py, pz)) {
                double d = std::hypot(px - me.pos[0], py - me.pos[1]);
                if (d < rad && t < 2.5) {
                    double dx = me.pos[0] - px, dy = me.pos[1] - py;
                    if (d < 0.5) {
                        dx = -p_proj.vel[1];
                        dy = p_proj.vel[0];
                        d = std::hypot(dx, dy);
                    }
                    dx /= d;
                    dy /= d;
                    for (double rot : std::array<double, 5>{{0.0, 0.7, -0.7, 1.4, -1.4}}) {
                        double c = std::cos(rot), s = std::sin(rot);
                        double ex = dx * c - dy * s, ey = dx * s + dy * c;
                        if (w->line_walkable(me.pos[0], me.pos[1], me.pos[0] + ex * 6.0, me.pos[1] + ey * 6.0)) {
                            *mx = ex;
                            *my = ey;
                            return true;
                        }
                    }
                }
                break;
            }
        }
    }
    return false;
}

std::pair<double, double> Brain::travel(const Self* me, double gx, double gy) {
    double x = me->pos[0], y = me->pos[1];
    double d = std::hypot(gx - x, gy - y);
    if (d < 0.8) return {0.0, 0.0};

    auto unit = [&](double tx, double ty) -> std::pair<double, double> {
        double l = std::hypot(tx - x, ty - y);
        if (l < 1e-6) return {0.0, 0.0};
        return {(tx - x) / l, (ty - y) / l};
    };

    if (me->pos[2] - w->ground_at(x, y) > 3.0 && w->obst[w->vidx(x, y)]) {
        return unit(gx, gy);
    }
    if (d < 45.0 && w->line_walkable(x, y, gx, gy)) {
        return unit(gx, gy);
    }
    if (path.empty() || std::hypot(gx - path_goal[0], gy - path_goal[1]) > 5.0 || now - path_at > 2.5) {
        auto [new_path, _] = w->path(x, y, gx, gy, 22000);
        path = new_path;
        path_goal = {gx, gy};
        path_at = now;
        path_i = 0;
    }
    if (path.empty()) return unit(gx, gy);

    int bi = path_i;
    double bd = std::numeric_limits<double>::infinity();
    for (int i = path_i; i < (int)path.size() && i < path_i + 10; i++) {
        auto [px, py] = w->cell_pos(path[i]);
        double dd = std::hypot(px - x, py - y);
        if (dd < bd) {
            bi = i;
            bd = dd;
        }
    }
    path_i = bi;
    if (bd > 12.0) {
        path.clear();
        return unit(gx, gy);
    }
    for (int i = std::min(bi + 14, (int)path.size() - 1); i > bi; i--) {
        auto [px, py] = w->cell_pos(path[i]);
        if (w->line_walkable(x, y, px, py)) {
            if (i == (int)path.size() - 1 && std::hypot(px - gx, py - gy) < 4.0 && w->line_walkable(x, y, gx, gy)) {
                return unit(gx, gy);
            }
            return unit(px, py);
        }
    }
    if (bi + 1 < (int)path.size()) {
        auto [px, py] = w->cell_pos(path[bi + 1]);
        return unit(px, py);
    }
    return unit(gx, gy);
}

double Brain::pref_range(const Self* me, const Track& t) const {
    auto [_, light] = has_weapon(me->weapons, "lightning");
    auto [__, laser] = has_weapon(me->weapons, "laser");
    double r = p.gun_range;
    if (light && me->energy > 12.0) r = p.light_range;
    else if (laser) r = p.laser_range;

    if (t.mech.kind == "npc") return 58.0;
    if (!light) {
        if (holds(t.mech.weapons, "lightning")) r = std::max(r, 64.0);
        if (holds(t.mech.weapons, "mortar")) r = std::max(r, 80.0);
    }
    return r;
}

std::pair<double, double> Brain::fight_move(Obs* o, Track* tg, const std::vector<Track*>& seen, double want_los) {
    auto& me = o->self;
    double x = me.pos[0], y = me.pos[1];
    double rp = pref_range(&me, *tg);
    double bx = tg->mech.pos[0] - x, by = tg->mech.pos[1] - y;
    double bd = std::hypot(bx, by) + 1e-9;
    double ux = bx / bd, uy = by / bd;

    if (now >= strafe_until) {
        if (rand_float() < 0.6) strafe = -strafe;
        strafe_until = now + 0.3 + rand_float() * 0.7;
    }
    double sx = -uy * strafe, sy = ux * strafe;
    Vec3 tc = center(*tg);
    double mh = me.stats.muzzle_height;

    const Known* cube = nullptr;
    for (const auto& [_, c] : cubes) {
        double d = std::hypot(c.pos[0] - x, c.pos[1] - y);
        if (d < 40.0 && (!cube || d < std::hypot(cube->pos[0] - x, cube->pos[1] - y)) &&
            std::abs(c.pos[2] - me.pos[2]) < 4.0) {
            cube = &c;
        }
    }

    double best = -std::numeric_limits<double>::infinity();
    double best_mx = 0.0, best_my = 0.0;
    bool blocked_side = false;
    int rings = p.peek ? 2 : 1;

    for (int k = -1; k < 16 * rings; k++) {
        double cx = x, cy = y, dx = 0.0, dy = 0.0, r = 0.0;
        if (k >= 0) {
            double a = static_cast<double>(k % 16) * M_PI / 8.0;
            r = 6.0 * static_cast<double>(1 + k / 16);
            dx = std::cos(a);
            dy = std::sin(a);
            cx = x + dx * r;
            cy = y + dy * r;
            if (!w->line_walkable(x, y, cx, cy) || !w->free_cell(cx, cy)) {
                if (k < 16 && dx * sx + dy * sy > 0.9) blocked_side = true;
                continue;
            }
        }
        double cz = w->walk_at(cx, cy);
        double d = std::hypot(tg->mech.pos[0] - cx, tg->mech.pos[1] - cy);
        double s = -1.1 * std::abs(d - rp) - r * 0.4;
        bool los = w->clear({cx, cy, cz + mh}, tc);
        if (los) s += 45.0 * want_los;

        if (p.peek && k >= 0 && k < 16 && (los == (want_los > 0.0))) {
            for (int q = 0; q < 16; q += 2) {
                double qx = cx + std::cos(static_cast<double>(q) * M_PI / 8.0) * 7.0;
                double qy = cy + std::sin(static_cast<double>(q) * M_PI / 8.0) * 7.0;
                if (w->free_cell(qx, qy) && w->clear({qx, qy, w->walk_at(qx, qy) + mh}, tc) != los) {
                    s += 8.0;
                    break;
                }
            }
        }

        Vec3 body = {cx, cy, cz + me.stats.height * 0.6};
        for (auto* e : seen) {
            if (e == tg || std::hypot(e->mech.pos[0] - cx, e->mech.pos[1] - cy) > 170.0) continue;
            if (w->clear(eye(*e), body)) s -= 30.0;
        }
        s -= zone_penalty(o->zone, cx, cy);
        if (cube) {
            s += 1.5 * (std::hypot(cube->pos[0] - x, cube->pos[1] - y) - std::hypot(cube->pos[0] - cx, cube->pos[1] - cy));
        }
        float cl = w->clearance[w->cell(cx, cy)];
        if (cl < 4.0f) s -= (4.0 - cl) * 2.5;
        if (want_los > 0.0) s += 9.0 * (dx * sx + dy * sy);
        if (k < 0) {
            s -= 8.0;
            if (want_los < 0.0 && !los) s += 14.0;
        }
        if (s > best) {
            best = s;
            best_mx = dx;
            best_my = dy;
        }
    }
    if (blocked_side) {
        strafe = -strafe;
        strafe_until = now + 0.5;
    }
    return {best_mx, best_my};
}

bool Brain::cover_move(Obs* o, const std::vector<Track*>& seen, double* mx, double* my) {
    auto& me = o->self;
    double x = me.pos[0], y = me.pos[1];
    std::vector<const Track*> threats;
    for (auto* t : seen) {
        if (std::hypot(t->mech.pos[0] - x, t->mech.pos[1] - y) < 230.0) threats.push_back(t);
    }
    if (threats.empty()) return false;
    if (threats.size() > 4) {
        std::sort(threats.begin(), threats.end(), [&](const Track* a, const Track* b) {
            return std::hypot(a->mech.pos[0] - x, a->mech.pos[1] - y) < std::hypot(b->mech.pos[0] - x, b->mech.pos[1] - y);
        });
        threats.resize(4);
    }

    auto hidden_fn = [&](double cx, double cy) -> bool {
        double cz = w->walk_at(cx, cy);
        for (auto* t : threats) {
            Vec3 e = eye(*t);
            if (w->clear(e, {cx, cy, cz + me.stats.height}) ||
                w->clear(e, {cx, cy, cz + me.stats.height * 0.5})) {
                return false;
            }
        }
        return true;
    };

    if (cover_ok && now - cover_at < 0.4) {
        std::tie(*mx, *my) = travel_cover(&me);
        return true;
    }
    cover_at = now;
    if (hidden_fn(x, y) && zone_penalty(o->zone, x, y) == 0.0) {
        cover_ok = true;
        cover_goal = {x, y};
        *mx = 0.0;
        *my = 0.0;
        return true;
    }

    int s = w->nearest_free(w->cell(x, y));
    if (s < 0) return false;

    w->gen++;
    uint32_t gen = w->gen;
    std::vector<int32_t> queue;
    queue.push_back(static_cast<int32_t>(s));
    w->stamp[s] = gen;
    w->g[s] = 0.0f;

    int best_c = -1;
    double best_s = std::numeric_limits<double>::infinity();
    int checked = 0;

    for (size_t h = 0; h < queue.size() && checked < 350; h++) {
        int c = queue[h];
        int ci = c % w->nnx, cj = c / w->nnx;
        double steps = static_cast<double>(w->g[c]);
        if (steps > 50.0 || (best_c >= 0 && steps * 2.0 > best_s + 30.0)) break;

        if ((ci + cj) % 2 == 0 && steps > 0.0) {
            auto [cx, cy] = w->cell_pos(c);
            checked++;
            if (hidden_fn(cx, cy)) {
                double sc = steps * 2.0 + zone_penalty(o->zone, cx, cy);
                double near_dist = std::numeric_limits<double>::infinity();
                for (auto* t : threats) {
                    near_dist = std::min(near_dist, std::hypot(t->mech.pos[0] - cx, t->mech.pos[1] - cy));
                }
                sc -= std::min(near_dist, 80.0) * 0.25;
                if (sc < best_s) {
                    best_c = c;
                    best_s = sc;
                }
            }
        }

        for (int k = 0; k < 8; k++) {
            int i = ci + NBRS[k][0], j = cj + NBRS[k][1];
            if (i < 0 || j < 0 || i >= w->nnx || j >= w->nny) continue;
            int nb = j * w->nnx + i;
            bool diag = (k >= 4);
            if (w->stamp[nb] == gen || !w->can_step(c, nb, diag)) continue;
            if (diag && (w->blocked[cj * w->nnx + i] || w->blocked[j * w->nnx + ci])) continue;
            w->stamp[nb] = gen;
            w->g[nb] = w->g[c] + 1.0f;
            queue.push_back(static_cast<int32_t>(nb));
        }
    }

    if (best_c < 0) {
        cover_ok = false;
        return false;
    }
    auto [gx, gy] = w->cell_pos(best_c);
    cover_ok = true;
    cover_goal = {gx, gy};
    std::tie(*mx, *my) = travel_cover(&me);
    return true;
}

std::pair<double, double> Brain::travel_cover(const Self* me) {
    if (std::hypot(cover_goal[0] - me->pos[0], cover_goal[1] - me->pos[1]) < 1.5) {
        return {0.0, 0.0};
    }
    return travel(me, cover_goal[0], cover_goal[1]);
}

std::optional<LootChoice> Brain::choose_loot(Obs* o, double hp_frac, bool danger) {
    auto& me = o->self;
    double x = me.pos[0], y = me.pos[1];
    auto& z = o->zone;
    Circle cur = cur_zone(z);
    std::optional<LootChoice> best;
    double best_u = 0.0;
    bool econ = p.econ;

    auto consider = [&](const std::string& kind, int id, const Vec3& pos, double value) {
        auto it = bad.find(id);
        if (it != bad.end() && it->second > now) return;
        double d = std::hypot(pos[0] - x, pos[1] - y);
        if (d > 260.0) return;
        if (std::hypot(pos[0] - cur.x, pos[1] - cur.y) > cur.r - 6.0) return;
        double dl = zone_deadline(z, pos[0], pos[1], 6.0);
        if (now + d * 1.4 / me.stats.walk_speed + 5.0 > dl) return;
        if (pos[2] - w->ground_at(pos[0], pos[1]) > 3.2) return;
        int nf = w->nearest_free(w->cell(pos[0], pos[1]));
        if (nf < 0 || w->comp[nf] != w->main_comp) return;

        double u = value / (d + 18.0);
        if (id == loot_id) u *= 1.35;
        if (econ) {
            u = value - 0.6 * d;
            if (id == loot_id) u += 30.0;
        }
        if (u > best_u) {
            best_u = u;
            best = LootChoice{kind, id, pos, value};
        }
    };

    if (econ) {
        bool mech_near = false;
        for (const auto& [_, t] : tracks) {
            if (t.seen == now) mech_near = true;
        }
        bool hurt = (hp_frac <= 0.45);
        bool near_only = false;
        for (const auto& [_, t] : tracks) {
            if (p.econ_safe > 0.0 && now - t.seen < p.econ_safe) near_only = true;
        }

        auto inner_consider = [&](const std::string& kind, int id, const Vec3& pos, double value) {
            if (near_only && std::hypot(pos[0] - x, pos[1] - y) > 60.0) return;
            consider(kind, id, pos, value);
        };

        for (const auto& [_, p_it] : pickups) {
            if (!want_pickup(&me, p_it.kind) || hurt) continue;
            double v = 150.0;
            if (me.weapons.size() > 1 && !me.weapons[1]) v = 260.0;
            if (p_it.kind == "laser") v = std::max(v, 270.0) + 20.0;
            inner_consider("pickup", p_it.id, p_it.pos, v);
        }
        for (const auto& [_, c] : cubes) {
            if (!hurt || std::hypot(c.pos[0] - x, c.pos[1] - y) < 35.0) {
                inner_consider("cube", c.id, c.pos, 110.0);
            }
        }
        for (const auto& [_, c] : crates) {
            if (!hurt || std::hypot(c.pos[0] - x, c.pos[1] - y) < 35.0) {
                inner_consider("crate", c.id, c.pos, 105.0);
            }
        }
        if (p.farm_npc && hp_frac > 0.6 && !mech_near) {
            for (const auto& [_, n] : npcs) {
                double v = (now - n.seen > 12.0) ? 155.0 : 170.0;
                inner_consider("npc", n.mech.id, n.mech.pos, v);
            }
        }
        for (const auto& d : o->drops) {
            if (p.use_drops && !hurt && std::hypot(d.pos[0] - x, d.pos[1] - y) / me.stats.walk_speed < d.lands_in + 25.0) {
                inner_consider("drop", d.id, d.pos, 170.0);
            }
        }

        if (!best.has_value()) {
            loot_id = -1;
            return std::nullopt;
        }
        if (best->id != loot_id) {
            loot_id = best->id;
            loot_since = now;
        } else if (double lim = 30.0; now - loot_since > lim ||
                   (best->kind == "crate" && now - loot_since > lim - 6.0 && std::hypot(best->pos[0] - x, best->pos[1] - y) < 50.0)) {
            bad[best->id] = now + 60.0;
            loot_id = -1;
            return std::nullopt;
        }
        return best;
    }

    for (const auto& [_, p_it] : pickups) {
        double rad = p.loot_radius;
        bool seek = (p_it.kind == "laser" && p.laser_seek > rad);
        if (seek) rad = p.laser_seek;
        if (want_pickup(&me, p_it.kind) && std::hypot(p_it.pos[0] - x, p_it.pos[1] - y) < rad) {
            double v = 60.0;
            if (me.weapons.size() > 1 && !me.weapons[1]) v = 130.0;
            if (seek) v = std::max(v, 150.0);
            consider("pickup", p_it.id, p_it.pos, v);
        }
    }
    double cube_v = (me.cubes >= cube_cap()) ? 25.0 : 75.0;
    for (const auto& [_, c] : cubes) {
        if (std::hypot(c.pos[0] - x, c.pos[1] - y) < std::max(60.0, p.loot_radius * 0.7)) {
            consider("cube", c.id, c.pos, cube_v);
        }
    }
    double farm_hp = (p.farm_hp > 0.0) ? p.farm_hp : 0.7;
    if (hp_frac > farm_hp && !danger && now < p.crate_until) {
        for (const auto& [_, c] : crates) {
            if (std::hypot(c.pos[0] - x, c.pos[1] - y) < p.loot_radius) {
                consider("crate", c.id, c.pos, cube_v * 0.6);
            }
        }
        if (p.farm_npc && me.cubes < cube_cap()) {
            for (const auto& [_, n] : npcs) {
                if (now - n.seen < 12.0 && std::hypot(n.mech.pos[0] - x, n.mech.pos[1] - y) < p.loot_radius) {
                    consider("npc", n.mech.id, n.mech.pos, 85.0);
                }
            }
        }
    }
    for (const auto& d : o->drops) {
        double dist = std::hypot(d.pos[0] - x, d.pos[1] - y);
        if (p.use_drops && dist / me.stats.walk_speed < d.lands_in + 25.0 && !danger) {
            consider("drop", d.id, d.pos, 260.0);
        }
    }
    if (!best.has_value()) {
        loot_id = -1;
        return std::nullopt;
    }
    if (best->id != loot_id) {
        loot_id = best->id;
        loot_since = now;
    } else if (now - loot_since > 30.0) {
        bad[best->id] = now + 60.0;
        loot_id = -1;
        return std::nullopt;
    }
    return best;
}

std::pair<double, double> Brain::explore_move(Obs* o) {
    auto& me = o->self;
    double x = me.pos[0], y = me.pos[1];
    auto& z = o->zone;
    if (now > explore_until || std::hypot(explore[0] - x, explore[1] - y) < 6.0) {
        for (int try_idx = 0; try_idx < 20; try_idx++) {
            double a = rand_float() * 2.0 * M_PI;
            double r = std::sqrt(rand_float()) * z.next_radius * 0.8;
            double px = z.next_center[0] + std::cos(a) * r;
            double py = z.next_center[1] + std::sin(a) * r;
            if (!w->in_bounds(px, py) || !w->free_cell(px, py)) continue;
            double d = std::hypot(px - x, py - y);
            if (d < 50.0 || d > 220.0) continue;
            explore = {px, py};
            explore_until = now + 30.0;
            break;
        }
    }
    if (now > explore_until) return {0.0, 0.0};
    return travel(&me, explore[0], explore[1]);
}

double Brain::home_cost(Obs* o, double px, double py) {
    auto& z = o->zone;
    double crowd = 0.0;
    for (const auto& [_, t] : tracks) {
        if (now - t.seen < 20.0) {
            crowd += std::max(0.0, 80.0 - std::hypot(t.mech.pos[0] - px, t.mech.pos[1] - py)) / 80.0;
        }
    }
    for (const auto& d : o->drops) {
        crowd += std::max(0.0, 60.0 - std::hypot(d.pos[0] - px, d.pos[1] - py)) / 60.0;
    }
    double edge = std::hypot(px - z.next_center[0], py - z.next_center[1]) / std::max(30.0, z.next_radius);
    return p.home_expo * w->exposure(px, py) + 0.25 * std::hypot(px - o->self.pos[0], py - o->self.pos[1]) +
           40.0 * crowd + 10.0 * edge;
}

std::tuple<double, double, bool> Brain::home(Obs* o) {
    auto& z = o->zone;
    bool out = !home_set || std::hypot(home_xy[0] - z.next_center[0], home_xy[1] - z.next_center[1]) > z.next_radius * 0.8;
    if (out || now - home_at > 12.0) {
        home_at = now;
        Vec2 best = {0.0, 0.0};
        double best_c = std::numeric_limits<double>::infinity();
        for (int k = 0; k < 40; k++) {
            double a = rand_float() * 2.0 * M_PI;
            double r = std::sqrt(rand_float()) * z.next_radius * 0.7;
            double px = z.next_center[0] + std::cos(a) * r;
            double py = z.next_center[1] + std::sin(a) * r;
            if (!w->in_bounds(px, py) || !w->reachable(px, py)) continue;
            double c = home_cost(o, px, py);
            if (c < best_c) {
                best = {px, py};
                best_c = c;
            }
        }
        if (!std::isinf(best_c) && (out || best_c < home_cost(o, home_xy[0], home_xy[1]) - 15.0)) {
            home_xy = best;
            home_set = true;
        }
    }
    return {home_xy[0], home_xy[1], home_set};
}

bool Brain::hide_from_bearing(Obs* o, const std::vector<Track*>& seen, double* mx, double* my) {
    auto& me = o->self;
    Track ghost;
    ghost.mech.pos = {me.pos[0] + std::cos(hurt_bearing) * 80.0, me.pos[1] + std::sin(hurt_bearing) * 80.0, me.pos[2]};
    std::vector<Track*> threats;
    threats.push_back(&ghost);
    for (auto* t : seen) threats.push_back(t);
    return cover_move(o, threats, mx, my);
}

std::tuple<double, double, bool> Brain::dodge(Obs* o) {
    auto& me = o->self;
    double cx = me.pos[0], cy = me.pos[1], cz = me.pos[2] + me.stats.height * 0.56;
    double reach_rad = me.stats.radius + 1.1;
    double dx = 0.0, dy = 0.0;
    bool laser = false;

    for (const auto& p_proj : o->projectiles) {
        if (p_proj.kind == "mortar") continue;
        double v2 = p_proj.vel[0] * p_proj.vel[0] + p_proj.vel[1] * p_proj.vel[1] + p_proj.vel[2] * p_proj.vel[2];
        if (v2 < 1.0) continue;
        double tc = ((cx - p_proj.pos[0]) * p_proj.vel[0] + (cy - p_proj.pos[1]) * p_proj.vel[1] + (cz - p_proj.pos[2]) * p_proj.vel[2]) / v2;
        if (tc <= 0.0 || tc > 0.7) continue;
        double mxx = p_proj.pos[0] + p_proj.vel[0] * tc - cx;
        double myy = p_proj.pos[1] + p_proj.vel[1] * tc - cy;
        if (std::hypot(mxx, myy) < reach_rad) {
            double vh = std::hypot(p_proj.vel[0], p_proj.vel[1]);
            if (vh < 1.0) continue;
            double px = -p_proj.vel[1] / vh, py = p_proj.vel[0] / vh;
            if (px * mxx + py * myy > 0.0) {
                px = -px;
                py = -py;
            }
            dx += px;
            dy += py;
        }
    }

    for (const auto& m : o->mechs) {
        if (m.kind != "mech" || !m.charging) continue;
        double to_me = std::atan2(cy - m.pos[1], cx - m.pos[0]);
        if (std::abs(ang_diff(m.aim[0], to_me)) > 0.15) continue;
        dx += std::cos(to_me + M_PI / 2.0 * strafe) * 1.5;
        dy += std::sin(to_me + M_PI / 2.0 * strafe) * 1.5;
        laser = true;
    }

    double l = std::hypot(dx, dy);
    if (l > 0.01) return {dx / l, dy / l, laser};
    return {0.0, 0.0, false};
}

double Brain::reach(const Self* me) const {
    double r = 0.0;
    for (const auto& w_item : me->weapons) {
        if (!w_item) continue;
        if (w_item->kind == "gun") r = std::max(r, std::min(w_item->stats.range - 10.0, 130.0));
        else if (w_item->kind == "laser") r = std::max(r, w_item->stats.range - 5.0);
        else if (w_item->kind == "lightning") r = std::max(r, w_item->stats.range);
    }
    return r;
}

double Brain::odds(const Self* me, const Track& t, double now_t, bool opening) const {
    int my_w = 0, th_w = (int)t.mech.weapons.size();
    for (const auto& w_item : me->weapons) {
        if (w_item) my_w++;
    }
    if (th_w == 0) th_w = 1;
    auto capc = [](int c) -> double { return std::min(static_cast<double>(c), 10.0); };
    double busy_me = 0.0, busy_them = 0.0;

    for (const auto& [_, u] : tracks) {
        if (u.mech.id == t.mech.id || now_t - u.seen > 2.5) continue;
        if (now_t - u.hit_me < 6.0) busy_me = 1.0;
        double br = std::atan2(u.mech.pos[1] - t.mech.pos[1], u.mech.pos[0] - t.mech.pos[0]);
        if (std::abs(ang_diff(t.mech.aim[0], br)) < 0.2 &&
            std::hypot(u.mech.pos[0] - t.mech.pos[0], u.mech.pos[1] - t.mech.pos[1]) < 160.0) {
            busy_them = 1.0;
        }
    }

    double z = 1.5093 * std::log(std::max(me->hp, 1.0) / std::max(t.mech.hp, 1.0)) +
               0.7049 * (capc(me->cubes) - capc(t.mech.cubes)) / 10.0 +
               0.9583 * static_cast<double>(my_w - th_w) - 0.5592 * (busy_me - busy_them);
    if (opening) {
        z += 0.0562 + 0.7475 * std::min(t.dist, 200.0) / 100.0;
        double to_me = std::atan2(me->pos[1] - t.mech.pos[1], me->pos[0] - t.mech.pos[0]);
        if (std::abs(ang_diff(t.mech.aim[0], to_me)) > 1.75) z += 0.8235;
    }
    return 1.0 / (1.0 + std::exp(-z));
}

int Brain::cube_cap() const {
    int c = cfg.cubes.stat_cap;
    if (static_cast<int>(p.cube_goal) > c) c = static_cast<int>(p.cube_goal);
    return c;
}

double Brain::rear_mult() const {
    return (cfg.mech.rear_mult > 1.0) ? cfg.mech.rear_mult : 1.0;
}

bool Brain::shows_back(const Track& t, double x, double y) const {
    double arc = (cfg.mech.front_arc_deg > 0.0) ? cfg.mech.front_arc_deg : 180.0;
    return std::abs(ang_diff(t.mech.aim[0], std::atan2(y - t.mech.pos[1], x - t.mech.pos[0]))) >
           arc * M_PI / 360.0 + 0.1;
}

} // namespace mech
