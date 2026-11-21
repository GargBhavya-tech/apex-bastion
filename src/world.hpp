#pragma once

#include "types.hpp"
#include <vector>
#include <map>
#include <memory>
#include <string>
#include <cmath>
#include <algorithm>
#include <limits>
#include <functional>

namespace mech {

inline constexpr std::array<std::array<int, 2>, 8> NBRS = {{
    {1, 0}, {-1, 0}, {0, 1}, {0, -1},
    {1, 1}, {1, -1}, {-1, 1}, {-1, -1}
}};

struct Slab {
    float base = 0.0f;
    float top = 0.0f;
};

struct HeapItem {
    float f = 0.0f;
    int32_t idx = 0;
    bool operator>(const HeapItem& other) const { return f > other.f; }
};

struct Interval {
    float base = 0.0f;
    float top = 0.0f;
    bool bridge = false;
};

struct Prism {
    std::string kind;
    double base = 0.0;
    double top = 0.0;
    std::vector<double> edges;
    double min_x = 0.0;
    double min_y = 0.0;
    double max_x = 0.0;
    double max_y = 0.0;
};

struct Tree {
    double x = 0.0, y = 0.0, z = 0.0;
    double height = 0.0, crown_r = 0.0, crown_base = 0.0, trunk_r = 0.0;
    double cx = 0.0, cy = 0.0;
    double trunk_top = 0.0, cz = 0.0, rz = 0.0;
};

struct Rules {
    double max_step = 1.5;
    double max_slope_deg = 50.0;
    double canopy_density = 0.35;
    double canopy_block_t = 0.25;
};

struct Geo {
    std::vector<Prism> prisms;
    std::vector<Tree> trees;
    Rules rules;
    double max_slope_tan = 1.19175;
    double gx0 = 0.0, gy0 = 0.0;
    int gnx = 0, gny = 0;
    std::vector<std::vector<int32_t>> grid_p;
    std::vector<std::vector<int32_t>> grid_t;
    int bnx = 0, bny = 0;
    std::vector<float> block_max;
};

struct Hit {
    double t = 0.0;
    double x = 0.0, y = 0.0, z = 0.0;
    double nx = 0.0, ny = 0.0, nz = 0.0;
    std::string kind;
    int id = -1;
};

struct RayOpts {
    bool no_trunks = false;
    bool no_terrain = false;
    bool canopy = false;
};

struct MoveResult {
    double x = 0.0, y = 0.0, z = 0.0;
    bool grounded = false;
    bool stopped_z = false;
    int walls = 0;
};

class World {
public:
    double min_x = 0.0, min_y = 0.0;
    int nx = 0, ny = 0;
    std::vector<float> ground;
    std::vector<float> top;
    std::vector<float> walk;
    std::vector<uint8_t> obst;
    std::vector<uint8_t> low;
    std::vector<uint8_t> has_slab;
    std::map<int32_t, std::vector<Slab>> slabs;
    double bx0 = 0.0, bx1 = 0.0, by0 = 0.0, by1 = 0.0;

    double ns = 2.0;
    int nnx = 0, nny = 0;
    std::vector<uint8_t> blocked;
    std::vector<float> surf;
    std::vector<float> clearance;
    std::vector<int32_t> comp;
    int32_t main_comp = 0;
    std::vector<int32_t> main_near;

    Geo geo;

    std::vector<float> g;
    std::vector<int32_t> came;
    std::vector<uint32_t> stamp;
    std::vector<uint32_t> closed;
    uint32_t gen = 0;
    std::vector<HeapItem> heap;

    static std::shared_ptr<World> load(const std::string& dir);
    static std::shared_ptr<World> flat();

    int vidx(double x, double y) const;
    bool in_bounds(double x, double y) const;
    double ground_at(double x, double y) const;
    double stack(double x, double y, bool deck) const;
    std::pair<double, int> stack_kind(double x, double y, bool deck) const;
    double walk_at(double x, double y) const { return stack(x, y, true); }
    double top_at(double x, double y) const { return stack(x, y, false); }
    bool solid(double x, double y, double z) const;
    bool solid_raster(double x, double y, double z) const;
    bool clear(const Vec3& a, const Vec3& b) const { return shot_clear(a, b); }
    bool clear_raster(const Vec3& a, const Vec3& b) const;

    bool standable(double x, double y, double z, double r) const;
    bool wall_within(double x, double y, double z, double r, double h) const;
    void build_nav();

    int cell(double x, double y) const;
    std::pair<double, double> cell_pos(int c) const;
    bool free_cell(double x, double y) const;
    int nearest_free(int c) const;
    bool can_step(int a, int b, bool diag) const;

    std::pair<std::vector<int32_t>, bool> path(double sx, double sy, double gx, double gy, int max_expand);
    bool line_walkable(double x0, double y0, double x1, double y1) const;
    bool can_stand(double x, double y, double z, double r) const;

    int get_main_near(int c);
    bool off_main(double x, double y);
    std::tuple<Vec2, Vec2, bool> escape_plan(double x, double y);
    bool reachable(double x, double y) const;
    double exposure(double x, double y) const;

    void init_geo(std::vector<Prism> prisms, std::vector<Tree> trees, Rules rules);
    int cell_of(double x, double y) const;
    void for_cells(double x0, double y0, double x1, double y1, const std::function<void(int)>& f) const;
    void walk_cells(double x0, double y0, double x1, double y1, const std::function<double(int)>& f) const;
    void walk_cells_t(double x0, double y0, double x1, double y1, const std::function<double(int, double, double)>& f) const;

    std::pair<double, double> ground_gradient(double x, double y) const;
    double surface_at(double x, double y, double max_z) const;
    std::pair<double, int> surface_kind(double x, double y, double max_z) const;
    double ceiling_above(double x, double y, double z, double r) const;

    std::tuple<double, double, double, std::string, int> penetration(double x, double y, double z, double r, double h) const;
    bool is_walkable(double x, double y, double r, double max_z, double h) const;
    MoveResult move_and_slide(double x, double y, double z, double r, double h, double dx, double dy, double dz) const;

    std::pair<Hit, bool> ray_prism(int pi, double x, double y, double z, double dx, double dy, double dz, double tmax) const;
    std::pair<Hit, bool> ray_terrain(double x, double y, double z, double x1, double y1, double z1, double tmax) const;
    std::pair<Hit, bool> raycast(const Vec3& a, const Vec3& b, RayOpts o) const;
    double canopy_transmittance(const Vec3& a, const Vec3& b) const;
    double crown_meters(const Vec3& a, const Vec3& b, double limit) const;
    bool line_of_sight(const Vec3& a, const Vec3& b) const;
    bool shot_clear(const Vec3& a, const Vec3& b) const;
    bool any_hit(const Vec3& a, const Vec3& b, bool trunks) const;
    int in_canopy(double x, double y, double z) const;
    double support_at(double x, double y, double feet_z, double r) const;

private:
    void push_heap(HeapItem it);
    HeapItem pop_heap();
};

bool point_in_poly(const std::vector<double>& e, double x, double y);
double closest_on_edges(const std::vector<double>& e, double x, double y, double& cx, double& cy);

} // namespace mech
