#pragma once

#include "types.hpp"
#include "world.hpp"
#include <random>
#include <map>
#include <memory>
#include <optional>

namespace mech {

struct Track {
    MechSeen mech;
    double seen = 0.0;
    double hit_me = -100.0;
    double dist = 0.0;
    bool los = false;
    double closing = 0.0;
    bool engage = false;
};

struct Known {
    int id = 0;
    std::string kind;
    Vec3 pos = {0, 0, 0};
    double hp = 0.0;
    double seen = 0.0;
};

struct Circle {
    double x = 0.0, y = 0.0, r = 0.0;
};

struct LootChoice {
    std::string kind;
    int id = 0;
    Vec3 pos = {0, 0, 0};
    double value = 0.0;
};

struct Params {
    double retreat_hp = 0.38;
    double recover_hp = 0.8;
    double gun_range = 85.0;
    double light_range = 28.0;
    double laser_range = 85.0;
    double engage_dist = 60.0;
    bool farm_npc = true;
    bool explore = false;
    bool ghost = true;
    double home_expo = 120.0;
    double loot_radius = 90.0;
    double crate_until = 150.0;
    bool use_drops = false;
    bool dodge = true;
    bool no_mortar = true;
    bool peek = true;
    bool laser_first = true;
    bool crowd_hide = true;
    double vulture = 0.0;
    double ambush = 0.0;
    double laser_seek = 0.0;
    bool lethal = false;
    double alert = 0.0;
    double shy = 0.0;
    double early_hide = 0.0;
    bool evade = false;
    double odds = 0.0;
    double odds_flee = 0.0;
    bool practice = true;
    double stick = 0.0;
    double hpw = 0.0;
    double low_bonus = 0.0;
    double max_target = 0.0;
    bool lose_rule = false;
    double fight_loot = 0.0;
    double farm_hp = 0.0;
    bool all_foes = false;
    double cube_goal = 0.0;
    bool econ = false;
    bool laser_up = false;
    double econ_safe = 0.0;
    bool opening = false;
    bool nano_up = false;
    double finish = 0.0;
    double finish_hp = 0.0;
    bool finish_rush = false;
    double pursue = 0.0;
    double fight_boost = 0.0;
    double dodge_boost = 0.0;
    double threat_boost = 0.0;
    bool speed_up = false;
    double backstab = 0.0;
    double lethal_k = 0.0;
};

Params default_params();
Params squad_params(Params p);

class Brain {
public:
    std::shared_ptr<World> w;
    Config cfg;
    int slot = 0;
    std::mt19937_64 rng;
    Params p;

    std::map<int, Track> tracks;
    std::map<int, Track> npcs;
    std::map<int, Known> crates;
    std::map<int, Known> cubes;
    std::map<int, Known> pickups;
    std::map<int, double> bad;

    double now = 0.0;

    std::vector<int32_t> path;
    Vec2 path_goal = {0, 0};
    double path_at = 0.0;
    int path_i = 0;

    double strafe = 1.0;
    double strafe_until = 0.0;

    bool retreat = false;
    double cover_at = 0.0;
    Vec2 cover_goal = {0, 0};
    bool cover_ok = false;

    double last_hurt = -100.0;
    double hurt_bearing = 0.0;
    bool hurt_seen_by = false;

    int loot_id = -1;
    double loot_since = 0.0;

    Circle hold;
    double hold_start = -1.0;

    Vec2 home_xy = {0, 0};
    double home_at = 0.0;
    bool home_set = false;
    Vec2 explore = {0, 0};
    double explore_until = 0.0;

    double stuck_since = -1.0;
    double unstuck_until = 0.0;
    Vec2 unstuck_dir = {0, 0};
    double last_threat_at = -100.0;
    Vec2 last_aim = {0, 0};
    double laser_held = 0.0;
    std::string mode = "idle";
    int panics = 0;

    Vec2 esc_launch = {0, 0}, esc_land = {0, 0};
    double esc_at = 0.0;
    bool esc_ok = false, esc_flying = false;
    double odds_flee_until = 0.0;
    Params base;
    bool base_set = false, prac_on = false;
    bool open_on = false;
    double npc_hurt = 0.0;
    double npc_bearing = 0.0;
    bool not_practice = false;
    int start_alive = 0, kills = 0;
    int other_dead = 0;
    int stick_id = 0;
    double stick_at = 0.0, lose_at = 0.0;

    Brain(const Hello& h, std::shared_ptr<World> world);

    Action act(Obs* o);
    void set_now(double t) { now = t; }
    std::pair<double, double> travel(const Self* me, double gx, double gy);

private:
    double scale_of(int cubes_count) const;
    Vec3 center(const Track& t) const;
    Vec3 eye(const Track& t) const;
    void observe(Obs* o);
    Circle zone_at(const Zone& z, double t) const;
    Circle cur_zone(const Zone& z) const;
    double zone_deadline(const Zone& z, double x, double y, double pad) const;
    double zone_penalty(const Zone& z, double x, double y) const;
    std::pair<double, double> zone_goal(const Zone& z, double x, double y) const;

    void step(Obs* o, Action* act);
    bool escape(const Self* me, double* mx, double* my, bool* boost, bool* jump);
    bool want_pickup(const Self* me, const std::string& kind) const;

    std::pair<double, double> lead(const Vec3& muzzle, const Vec3& tp, const Vec3& tv, double speed, bool grounded) const;
    std::tuple<double, double, bool> mortar(const Vec3& tube, const Vec3& foot, const Vec3& tv, double v, double g, const MechStats& st) const;
    bool dodge_shell(Obs* o, double* mx, double* my);

    double pref_range(const Self* me, const Track& t) const;
    std::pair<double, double> fight_move(Obs* o, Track* tg, const std::vector<Track*>& seen, double want_los);
    bool cover_move(Obs* o, const std::vector<Track*>& seen, double* mx, double* my);
    std::pair<double, double> travel_cover(const Self* me);

    std::optional<LootChoice> choose_loot(Obs* o, double hp_frac, bool danger);
    std::pair<double, double> explore_move(Obs* o);
    double home_cost(Obs* o, double px, double py);
    std::tuple<double, double, bool> home(Obs* o);
    bool hide_from_bearing(Obs* o, const std::vector<Track*>& seen, double* mx, double* my);
    std::tuple<double, double, bool> dodge(Obs* o);
    double reach(const Self* me) const;
    double odds(const Self* me, const Track& t, double now_t, bool opening) const;
    int cube_cap() const;
    double rear_mult() const;
    bool shows_back(const Track& t, double x, double y) const;
    double rand_float();
};

} // namespace mech
