#pragma once

#include <string>
#include <vector>
#include <map>
#include <array>
#include <memory>
#include <optional>
#include <cmath>
#include "json.hpp"

namespace mech {

using nlohmann::json;
using Vec3 = std::array<double, 3>;
using Vec2 = std::array<double, 2>;

struct MechStats {
    double radius = 1.6;
    double height = 4.2;
    double eye_height = 3.6;
    double muzzle_height = 2.4;
    double hp = 1000.0;
    double walk_speed = 14.0;
    double boost_speed = 24.0;
    double ground_accel = 60.0;
    double air_accel = 12.0;
    double gravity = 25.0;
    double jump_speed = 12.0;
    double jet_accel = 30.0;
    double max_rise_speed = 16.0;
    double step_up = 1.2;
    double max_slope_deg = 50.0;
    double energy = 100.0;
    double energy_regen = 25.0;
    double energy_regen_delay = 0.8;
    double boost_drain = 35.0;
    double jet_drain = 45.0;
    double turn_rate = 4.0;
    double pitch_rate = 3.0;
    double min_pitch = -0.9;
    double max_pitch = 0.9;
    double regen_delay = 6.0;
    double regen_per_s = 20.0;
    double charge_move_mult = 0.6;
    double self_damage_mult = 0.5;
    double armor = 0.0;
    double rear_mult = 1.5;
    double front_arc_deg = 180.0;
    double near_range_bonus = 0.0;
    double vision_bonus = 0.0;
    double hearing = 1.0;
};

inline void from_json(const json& j, MechStats& s) {
    s.radius = j.value("radius", s.radius);
    s.height = j.value("height", s.height);
    s.eye_height = j.value("eye_height", s.eye_height);
    s.muzzle_height = j.value("muzzle_height", s.muzzle_height);
    s.hp = j.value("hp", s.hp);
    s.walk_speed = j.value("walk_speed", s.walk_speed);
    s.boost_speed = j.value("boost_speed", s.boost_speed);
    s.ground_accel = j.value("ground_accel", s.ground_accel);
    s.air_accel = j.value("air_accel", s.air_accel);
    s.gravity = j.value("gravity", s.gravity);
    s.jump_speed = j.value("jump_speed", s.jump_speed);
    s.jet_accel = j.value("jet_accel", s.jet_accel);
    s.max_rise_speed = j.value("max_rise_speed", s.max_rise_speed);
    s.step_up = j.value("step_up", s.step_up);
    s.max_slope_deg = j.value("max_slope_deg", s.max_slope_deg);
    s.energy = j.value("energy", s.energy);
    s.energy_regen = j.value("energy_regen", s.energy_regen);
    s.energy_regen_delay = j.value("energy_regen_delay", s.energy_regen_delay);
    s.boost_drain = j.value("boost_drain", s.boost_drain);
    s.jet_drain = j.value("jet_drain", s.jet_drain);
    s.turn_rate = j.value("turn_rate", s.turn_rate);
    s.pitch_rate = j.value("pitch_rate", s.pitch_rate);
    s.min_pitch = j.value("min_pitch", s.min_pitch);
    s.max_pitch = j.value("max_pitch", s.max_pitch);
    s.regen_delay = j.value("regen_delay", s.regen_delay);
    s.regen_per_s = j.value("regen_per_s", s.regen_per_s);
    s.charge_move_mult = j.value("charge_move_mult", s.charge_move_mult);
    s.self_damage_mult = j.value("self_damage_mult", s.self_damage_mult);
    s.armor = j.value("armor", s.armor);
    s.rear_mult = j.value("rear_mult", s.rear_mult);
    s.front_arc_deg = j.value("front_arc_deg", s.front_arc_deg);
    s.near_range_bonus = j.value("near_range_bonus", s.near_range_bonus);
    s.vision_bonus = j.value("vision_bonus", s.vision_bonus);
    s.hearing = j.value("hearing", s.hearing);
}

struct WeaponStats {
    double damage = 0.0;
    double cooldown = 0.0;
    double speed = 0.0;
    double range = 0.0;
    double spread_deg = 0.0;
    double mag = 0.0;
    double reload = 0.0;
    double splash = 0.0;
    double splash_radius = 0.0;
    double splash_edge = 0.0;
    double gravity = 0.0;
    double ttl = 0.0;
    double knock = 0.0;
    double knock_up = 0.0;
    double drain = 0.0;
    double charge = 0.0;
    double min_charge = 0.0;
    double min_frac = 0.0;
    double hold_s = 0.0;
    double pierce = 0.0;
    double cookoff = 0.0;
    double cone_deg = 0.0;
    double chain = 0.0;
    double chain_range = 0.0;
    double chain_falloff = 0.0;
    double energy = 0.0;
    double short_s = 0.0;
};

inline void from_json(const json& j, WeaponStats& w) {
    w.damage = j.value("damage", 0.0);
    w.cooldown = j.value("cooldown", 0.0);
    w.speed = j.value("speed", 0.0);
    w.range = j.value("range", 0.0);
    w.spread_deg = j.value("spread_deg", 0.0);
    w.mag = j.value("mag", 0.0);
    w.reload = j.value("reload", 0.0);
    w.splash = j.value("splash", 0.0);
    w.splash_radius = j.value("splash_radius", 0.0);
    w.splash_edge = j.value("splash_edge", 0.0);
    w.gravity = j.value("gravity", 0.0);
    w.ttl = j.value("ttl", 0.0);
    w.knock = j.value("knock", 0.0);
    w.knock_up = j.value("knock_up", 0.0);
    w.drain = j.value("drain", 0.0);
    w.charge = j.value("charge", 0.0);
    w.min_charge = j.value("min_charge", 0.0);
    w.min_frac = j.value("min_frac", 0.0);
    w.hold_s = j.value("hold_s", 0.0);
    w.pierce = j.value("pierce", 0.0);
    w.cookoff = j.value("cookoff", 0.0);
    w.cone_deg = j.value("cone_deg", 0.0);
    w.chain = j.value("chain", 0.0);
    w.chain_range = j.value("chain_range", 0.0);
    w.chain_falloff = j.value("chain_falloff", 0.0);
    w.energy = j.value("energy", 0.0);
    w.short_s = j.value("short_s", 0.0);
}

struct ZonePhase {
    double hold_s = 0.0;
    double shrink_s = 0.0;
    double radius = 0.0;
    double dps = 0.0;
};

inline void from_json(const json& j, ZonePhase& z) {
    z.hold_s = j.value("hold_s", 0.0);
    z.shrink_s = j.value("shrink_s", 0.0);
    z.radius = j.value("radius", 0.0);
    z.dps = j.value("dps", 0.0);
}

struct UpgradeEffect {
    std::string path;
    std::optional<double> mul;
    std::optional<double> add;
};

inline void from_json(const json& j, UpgradeEffect& u) {
    u.path = j.value("path", "");
    if (j.contains("mul") && !j["mul"].is_null()) u.mul = j["mul"].get<double>();
    if (j.contains("add") && !j["add"].is_null()) u.add = j["add"].get<double>();
}

struct Upgrade {
    std::string id;
    std::string name;
    std::string desc;
    std::string req;
    int max = 0;
    std::vector<UpgradeEffect> effects;
};

inline void from_json(const json& j, Upgrade& u) {
    u.id = j.value("id", "");
    u.name = j.value("name", "");
    u.desc = j.value("desc", "");
    u.req = j.value("requires", "");
    u.max = j.value("max", 0);
    if (j.contains("effects")) u.effects = j["effects"].get<std::vector<UpgradeEffect>>();
}

struct Config {
    struct {
        double tick_hz = 20.0;
        int decide_every = 1;
        double duration_s = 300.0;
    } match;
    struct {
        double tick_budget_ms = 50.0;
    } bot;
    MechStats mech;
    struct {
        double range = 180.0;
        double fov_deg = 120.0;
        double near_range = 15.0;
        double memory_s = 4.0;
    } vision;
    std::map<std::string, WeaponStats> weapons;
    struct {
        double pickup_radius = 2.5;
        double hp_per_cube = 15.0;
        double damage_per_cube = 0.03;
        int stat_cap = 10;
        int death_drop_extra = 2;
        double size_per_cube = 0.02;
        std::vector<int> upgrade_thresholds;
    } cubes;
    struct {
        int count = 20;
        double hp = 100.0;
        double radius = 1.0;
        double height = 1.5;
    } crates;
    struct {
        double pickup_radius = 2.5;
        double equip_s = 0.5;
        int floor_count = 15;
        double crate_weapon_chance = 0.4;
    } loot;
    struct {
        int count = 10;
        double hp = 250.0;
        double radius = 1.5;
        double height = 3.0;
        double aggro_range = 60.0;
        double deaggro_range = 80.0;
        double damage = 18.0;
        double cooldown = 0.8;
        double projectile_speed = 70.0;
        double spread_deg = 3.0;
        int cubes = 3;
    } npc;
    struct {
        std::vector<double> times;
        double fall_s = 8.0;
        double radius = 4.0;
        double capture_s = 6.0;
        int cubes = 10;
    } drops;
    struct {
        Vec2 start_center = {0.0, 0.0};
        double start_radius = 250.0;
        std::vector<ZonePhase> phases;
    } zone;
    std::vector<Upgrade> upgrades;
};

inline void from_json(const json& j, Config& c) {
    if (j.contains("match")) {
        c.match.tick_hz = j["match"].value("tick_hz", 20.0);
        c.match.decide_every = j["match"].value("decide_every", 1);
        c.match.duration_s = j["match"].value("duration_s", 300.0);
    }
    if (j.contains("bot")) {
        c.bot.tick_budget_ms = j["bot"].value("tick_budget_ms", 50.0);
    }
    if (j.contains("mech")) c.mech = j["mech"].get<MechStats>();
    if (j.contains("vision")) {
        c.vision.range = j["vision"].value("range", 180.0);
        c.vision.fov_deg = j["vision"].value("fov_deg", 120.0);
        c.vision.near_range = j["vision"].value("near_range", 15.0);
        c.vision.memory_s = j["vision"].value("memory_s", 4.0);
    }
    if (j.contains("weapons")) {
        for (auto& [k, v] : j["weapons"].items()) {
            c.weapons[k] = v.get<WeaponStats>();
        }
    }
    if (j.contains("cubes")) {
        c.cubes.pickup_radius = j["cubes"].value("pickup_radius", 2.5);
        c.cubes.hp_per_cube = j["cubes"].value("hp_per_cube", 15.0);
        c.cubes.damage_per_cube = j["cubes"].value("damage_per_cube", 0.03);
        c.cubes.stat_cap = j["cubes"].value("stat_cap", 10);
        c.cubes.death_drop_extra = j["cubes"].value("death_drop_extra", 2);
        c.cubes.size_per_cube = j["cubes"].value("size_per_cube", 0.02);
        if (j["cubes"].contains("upgrade_thresholds")) {
            c.cubes.upgrade_thresholds = j["cubes"]["upgrade_thresholds"].get<std::vector<int>>();
        }
    }
    if (j.contains("crates")) {
        c.crates.count = j["crates"].value("count", 20);
        c.crates.hp = j["crates"].value("hp", 100.0);
        c.crates.radius = j["crates"].value("radius", 1.0);
        c.crates.height = j["crates"].value("height", 1.5);
    }
    if (j.contains("loot")) {
        c.loot.pickup_radius = j["loot"].value("pickup_radius", 2.5);
        c.loot.equip_s = j["loot"].value("equip_s", 0.5);
        c.loot.floor_count = j["loot"].value("floor_count", 15);
        c.loot.crate_weapon_chance = j["loot"].value("crate_weapon_chance", 0.4);
    }
    if (j.contains("npc")) {
        c.npc.count = j["npc"].value("count", 10);
        c.npc.hp = j["npc"].value("hp", 250.0);
        c.npc.radius = j["npc"].value("radius", 1.5);
        c.npc.height = j["npc"].value("height", 3.0);
        c.npc.aggro_range = j["npc"].value("aggro_range", 60.0);
        c.npc.deaggro_range = j["npc"].value("deaggro_range", 80.0);
        c.npc.damage = j["npc"].value("damage", 18.0);
        c.npc.cooldown = j["npc"].value("cooldown", 0.8);
        c.npc.projectile_speed = j["npc"].value("projectile_speed", 70.0);
        c.npc.spread_deg = j["npc"].value("spread_deg", 3.0);
        c.npc.cubes = j["npc"].value("cubes", 3);
    }
    if (j.contains("drops")) {
        if (j["drops"].contains("times")) c.drops.times = j["drops"]["times"].get<std::vector<double>>();
        c.drops.fall_s = j["drops"].value("fall_s", 8.0);
        c.drops.radius = j["drops"].value("radius", 4.0);
        c.drops.capture_s = j["drops"].value("capture_s", 6.0);
        c.drops.cubes = j["drops"].value("cubes", 10);
    }
    if (j.contains("zone")) {
        if (j["zone"].contains("start_center")) c.zone.start_center = j["zone"]["start_center"].get<Vec2>();
        c.zone.start_radius = j["zone"].value("start_radius", 250.0);
        if (j["zone"].contains("phases")) c.zone.phases = j["zone"]["phases"].get<std::vector<ZonePhase>>();
    }
    if (j.contains("upgrades")) c.upgrades = j["upgrades"].get<std::vector<Upgrade>>();
}

struct Hello {
    std::string type;
    int slot = 0;
    uint64_t seed = 0;
    struct {
        std::string dir = "/arena";
    } map;
    Config config;
};

inline void from_json(const json& j, Hello& h) {
    h.type = j.value("type", "");
    h.slot = j.value("slot", 0);
    h.seed = j.value("seed", (uint64_t)0);
    if (j.contains("map") && j["map"].contains("dir")) {
        h.map.dir = j["map"]["dir"].get<std::string>();
    }
    if (j.contains("config")) {
        h.config = j["config"].get<Config>();
    }
}

struct WeaponState {
    std::string kind;
    double cooldown = 0.0;
    double ammo = 0.0;
    double reload = 0.0;
    double charge = 0.0;
    WeaponStats stats;
};

inline void from_json(const json& j, WeaponState& w) {
    w.kind = j.value("kind", "");
    w.cooldown = j.value("cooldown", 0.0);
    w.ammo = j.value("ammo", 0.0);
    w.reload = j.value("reload", 0.0);
    w.charge = j.value("charge", 0.0);
    if (j.contains("stats")) w.stats = j["stats"].get<WeaponStats>();
}

struct Self {
    int id = 0;
    Vec3 pos = {0, 0, 0};
    Vec3 vel = {0, 0, 0};
    Vec2 aim = {0, 0};
    double hp = 1000.0;
    double max_hp = 1000.0;
    double energy = 100.0;
    double max_energy = 100.0;
    bool grounded = true;
    int cubes = 0;
    std::vector<std::string> upgrades;
    bool in_zone = true;
    std::vector<std::shared_ptr<WeaponState>> weapons;
    MechStats stats;
};

inline void from_json(const json& j, Self& s) {
    s.id = j.value("id", 0);
    if (j.contains("pos")) s.pos = j["pos"].get<Vec3>();
    if (j.contains("vel")) s.vel = j["vel"].get<Vec3>();
    if (j.contains("aim")) s.aim = j["aim"].get<Vec2>();
    s.hp = j.value("hp", 1000.0);
    s.max_hp = j.value("max_hp", 1000.0);
    s.energy = j.value("energy", 100.0);
    s.max_energy = j.value("max_energy", 100.0);
    s.grounded = j.value("grounded", true);
    s.cubes = j.value("cubes", 0);
    if (j.contains("upgrades")) s.upgrades = j["upgrades"].get<std::vector<std::string>>();
    s.in_zone = j.value("in_zone", true);
    if (j.contains("weapons") && j["weapons"].is_array()) {
        s.weapons.clear();
        for (const auto& item : j["weapons"]) {
            if (item.is_null()) {
                s.weapons.push_back(nullptr);
            } else {
                auto ws = std::make_shared<WeaponState>();
                *ws = item.get<WeaponState>();
                s.weapons.push_back(ws);
            }
        }
    }
    if (j.contains("stats")) s.stats = j["stats"].get<MechStats>();
}

struct MechSeen {
    int id = 0;
    std::string kind = "mech";
    Vec3 pos = {0, 0, 0};
    Vec3 vel = {0, 0, 0};
    Vec2 aim = {0, 0};
    double hp = 1000.0;
    double max_hp = 1000.0;
    int cubes = 0;
    std::vector<std::string> weapons;
    bool charging = false;
};

inline void from_json(const json& j, MechSeen& m) {
    m.id = j.value("id", 0);
    m.kind = j.value("kind", "mech");
    if (j.contains("pos")) m.pos = j["pos"].get<Vec3>();
    if (j.contains("vel")) m.vel = j["vel"].get<Vec3>();
    if (j.contains("aim")) m.aim = j["aim"].get<Vec2>();
    m.hp = j.value("hp", 1000.0);
    m.max_hp = j.value("max_hp", 1000.0);
    m.cubes = j.value("cubes", 0);
    if (j.contains("weapons")) m.weapons = j["weapons"].get<std::vector<std::string>>();
    m.charging = j.value("charging", false);
}

struct Proj {
    int id = 0;
    std::string kind;
    Vec3 pos = {0, 0, 0};
    Vec3 vel = {0, 0, 0};
};

inline void from_json(const json& j, Proj& p) {
    p.id = j.value("id", 0);
    p.kind = j.value("kind", "");
    if (j.contains("pos")) p.pos = j["pos"].get<Vec3>();
    if (j.contains("vel")) p.vel = j["vel"].get<Vec3>();
}

struct Item {
    int id = 0;
    std::string kind;
    Vec3 pos = {0, 0, 0};
    double hp = 0.0;
};

inline void from_json(const json& j, Item& it) {
    it.id = j.value("id", 0);
    it.kind = j.value("kind", "");
    if (j.contains("pos")) it.pos = j["pos"].get<Vec3>();
    it.hp = j.value("hp", 0.0);
}

struct Event {
    std::string type;
    double amount = 0.0;
    std::string weapon;
    std::optional<double> bearing;
    std::optional<int> by;
    bool rear = false;
    int target = 0;
    std::string effect;
    std::string kind;
    std::string reason;
    int cubes = 0;
};

inline void from_json(const json& j, Event& e) {
    e.type = j.value("type", "");
    e.amount = j.value("amount", 0.0);
    e.weapon = j.value("weapon", "");
    if (j.contains("bearing") && !j["bearing"].is_null()) e.bearing = j["bearing"].get<double>();
    if (j.contains("by") && !j["by"].is_null()) e.by = j["by"].get<int>();
    e.rear = j.value("rear", false);
    e.target = j.value("target", 0);
    e.effect = j.value("effect", "");
    e.kind = j.value("kind", "");
    e.reason = j.value("reason", "");
    e.cubes = j.value("cubes", 0);
}

struct Drop {
    int id = 0;
    Vec3 pos = {0, 0, 0};
    double radius = 0.0;
    double lands_in = 0.0;
    double capture_s = 0.0;
    double progress = 0.0;
    std::optional<int> holder;
};

inline void from_json(const json& j, Drop& d) {
    d.id = j.value("id", 0);
    if (j.contains("pos")) d.pos = j["pos"].get<Vec3>();
    d.radius = j.value("radius", 0.0);
    d.lands_in = j.value("lands_in", 0.0);
    d.capture_s = j.value("capture_s", 0.0);
    d.progress = j.value("progress", 0.0);
    if (j.contains("holder") && !j["holder"].is_null()) d.holder = j["holder"].get<int>();
}

struct Zone {
    Vec2 center = {0, 0};
    double radius = 250.0;
    Vec2 next_center = {0, 0};
    double next_radius = 250.0;
    double shrink_start = 0.0;
    double shrink_end = 0.0;
    double dps = 0.0;
};

inline void from_json(const json& j, Zone& z) {
    if (j.contains("center")) z.center = j["center"].get<Vec2>();
    z.radius = j.value("radius", 250.0);
    if (j.contains("next_center")) z.next_center = j["next_center"].get<Vec2>();
    z.next_radius = j.value("next_radius", 250.0);
    z.shrink_start = j.value("shrink_start", 0.0);
    z.shrink_end = j.value("shrink_end", 0.0);
    z.dps = j.value("dps", 0.0);
}

struct OfferChoice {
    std::string id;
    std::string name;
    std::string desc;
};

inline void from_json(const json& j, OfferChoice& oc) {
    oc.id = j.value("id", "");
    oc.name = j.value("name", "");
    oc.desc = j.value("desc", "");
}

struct Offer {
    int id = 0;
    double expires = 0.0;
    std::vector<OfferChoice> choices;
};

inline void from_json(const json& j, Offer& o) {
    o.id = j.value("id", 0);
    o.expires = j.value("expires", 0.0);
    if (j.contains("choices")) o.choices = j["choices"].get<std::vector<OfferChoice>>();
}

struct Obs {
    std::string type;
    int tick = 0;
    double t = 0.0;
    int alive = 16;
    Self self;
    std::vector<MechSeen> mechs;
    std::vector<Proj> projectiles;
    std::vector<Item> crates;
    std::vector<Item> cubes;
    std::vector<Item> pickups;
    std::vector<Event> events;
    std::vector<Drop> drops;
    Zone zone;
    std::shared_ptr<Offer> offer = nullptr;
};

inline void from_json(const json& j, Obs& o) {
    o.type = j.value("type", "");
    o.tick = j.value("tick", 0);
    o.t = j.value("t", 0.0);
    o.alive = j.value("alive", 16);
    if (j.contains("self")) o.self = j["self"].get<Self>();
    if (j.contains("mechs")) o.mechs = j["mechs"].get<std::vector<MechSeen>>();
    if (j.contains("projectiles")) o.projectiles = j["projectiles"].get<std::vector<Proj>>();
    if (j.contains("crates")) o.crates = j["crates"].get<std::vector<Item>>();
    if (j.contains("cubes")) o.cubes = j["cubes"].get<std::vector<Item>>();
    if (j.contains("pickups")) o.pickups = j["pickups"].get<std::vector<Item>>();
    if (j.contains("events")) o.events = j["events"].get<std::vector<Event>>();
    if (j.contains("drops")) o.drops = j["drops"].get<std::vector<Drop>>();
    if (j.contains("zone")) o.zone = j["zone"].get<Zone>();
    if (j.contains("offer") && !j["offer"].is_null()) {
        o.offer = std::make_shared<Offer>();
        *o.offer = j["offer"].get<Offer>();
    } else {
        o.offer = nullptr;
    }
}

struct Action {
    int tick = 0;
    Vec2 move = {0.0, 0.0};
    bool boost = false;
    bool jump = false;
    std::optional<Vec2> aim;
    std::array<bool, 2> fire = {false, false};
    bool reload = false;
    std::optional<int> pick;
    std::optional<int> take;
    std::optional<int> drop;
};

inline void to_json(json& j, const Action& a) {
    j = json{
        {"tick", a.tick},
        {"move", a.move},
        {"boost", a.boost},
        {"jump", a.jump},
        {"fire", a.fire},
        {"reload", a.reload}
    };
    if (a.aim.has_value()) {
        j["aim"] = a.aim.value();
    }
    if (a.pick.has_value()) {
        j["pick"] = a.pick.value();
    }
    if (a.take.has_value()) {
        j["take"] = a.take.value();
    }
    if (a.drop.has_value()) {
        j["drop"] = a.drop.value();
    }
}

} // namespace mech
