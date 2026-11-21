#include "world.hpp"
#include <fstream>
#include <sstream>
#include <iostream>
#include <queue>
#include <cstring>

namespace mech {

static const double STEP_UP = 1.2;
static const double NAV_RADIUS = 2.6;
static const double GEO_CELL = 16.0;
static const bool TRUNK_WALLS = false;

bool point_in_poly(const std::vector<double>& e, double x, double y) {
    bool in = false;
    for (size_t i = 0; i < e.size(); i += 4) {
        double x0 = e[i], y0 = e[i + 1], x1 = e[i + 2], y1 = e[i + 3];
        if ((y0 > y) != (y1 > y) && x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-15) + x0) {
            in = !in;
        }
    }
    return in;
}

double closest_on_edges(const std::vector<double>& e, double x, double y, double& cx, double& cy) {
    double best = std::numeric_limits<double>::infinity();
    for (size_t i = 0; i < e.size(); i += 4) {
        double x0 = e[i], y0 = e[i + 1];
        double ux = e[i + 2] - x0, uy = e[i + 3] - y0;
        double l2 = ux * ux + uy * uy;
        double p = 0.0;
        if (l2 > 1e-9) {
            p = ((x - x0) * ux + (y - y0) * uy) / l2;
        }
        p = std::clamp(p, 0.0, 1.0);
        double mx = x0 + ux * p, my = y0 + uy * p;
        double g = (mx - x) * (mx - x) + (my - y) * (my - y);
        if (g < best) {
            best = g;
            cx = mx;
            cy = my;
        }
    }
    return std::sqrt(best);
}

static std::pair<double, bool> ray_trunk(double cx, double cy, double r, double z0, double z1,
                                         double x, double y, double z, double dx, double dy, double dz, double tmax) {
    double px = x - cx, py = y - cy;
    double a = dx * dx + dy * dy;
    if (a < 1e-9) return {0.0, false};
    double b = 2.0 * (px * dx + py * dy);
    double c = px * px + py * py - r * r;
    double disc = b * b - 4.0 * a * c;
    if (disc < 0.0) return {0.0, false};
    double t = (-b - std::sqrt(disc)) / (2.0 * a);
    if (t < 0.0 || t >= tmax) return {0.0, false};
    double hz = z + dz * t;
    if (hz < z0 || hz > z1) return {0.0, false};
    return {t, true};
}

static std::tuple<double, double, bool> ray_crown(const Tree& tr, double x, double y, double z,
                                                  double dx, double dy, double dz) {
    double ox = (x - tr.cx) / tr.crown_r, oy = (y - tr.cy) / tr.crown_r, oz = (z - tr.cz) / tr.rz;
    double ux = dx / tr.crown_r, uy = dy / tr.crown_r, uz = dz / tr.rz;
    double a = ux * ux + uy * uy + uz * uz;
    if (a < 1e-9) return {0.0, 0.0, false};
    double b = 2.0 * (ox * ux + oy * uy + oz * uz);
    double c = ox * ox + oy * oy + oz * oz - 1.0;
    double disc = b * b - 4.0 * a * c;
    if (disc <= 0.0) return {0.0, 0.0, false};
    double s = std::sqrt(disc);
    double t0 = (-b - s) / (2.0 * a), t1 = (-b + s) / (2.0 * a);
    if (t1 < 0.0 || t0 > 1.0) return {0.0, 0.0, false};
    return {t0, t1, true};
}

std::shared_ptr<World> World::load(const std::string& dir) {
    std::string wj_path = dir + "/v2/world.json";
    std::ifstream wjf(wj_path);
    if (!wjf.is_open()) return nullptr;

    json j;
    try {
        wjf >> j;
    } catch (...) {
        return nullptr;
    }

    std::string tb_path = dir + "/v2/terrain.i16";
    std::ifstream tbf(tb_path, std::ios::binary | std::ios::ate);
    if (!tbf.is_open()) return nullptr;
    std::streamsize tb_size = tbf.tellg();
    tbf.seekg(0, std::ios::beg);

    auto w = std::make_shared<World>();
    auto& terrain_j = j["terrain"];
    w->min_x = terrain_j.value("minX", 0.0);
    w->min_y = terrain_j.value("minY", 0.0);
    w->nx = terrain_j.value("nx", 0);
    w->ny = terrain_j.value("ny", 0);
    int n = w->nx * w->ny;
    if (tb_size < n * 2 || n == 0) return nullptr;

    auto& bounds_j = j["bounds"];
    w->bx0 = bounds_j.value("minX", 0.0);
    w->bx1 = bounds_j.value("maxX", 0.0);
    w->by0 = bounds_j.value("minY", 0.0);
    w->by1 = bounds_j.value("maxY", 0.0);

    std::vector<int16_t> raw_terrain(n);
    tbf.read(reinterpret_cast<char*>(raw_terrain.data()), n * 2);

    w->ground.resize(n);
    for (int i = 0; i < n; i++) {
        w->ground[i] = static_cast<float>(raw_terrain[i]) * 0.01f;
    }

    std::vector<Prism> prisms;
    if (j.contains("prisms") && j["prisms"].is_array()) {
        for (const auto& pj : j["prisms"]) {
            Prism q;
            q.kind = pj.value("kind", "");
            q.base = pj.value("base", 0.0);
            q.top = pj.value("top", 0.0);
            q.min_x = std::numeric_limits<double>::infinity();
            q.min_y = std::numeric_limits<double>::infinity();
            q.max_x = -std::numeric_limits<double>::infinity();
            q.max_y = -std::numeric_limits<double>::infinity();

            std::vector<std::vector<double>> rings;
            if (pj.contains("ring")) rings.push_back(pj["ring"].get<std::vector<double>>());
            if (pj.contains("holes")) {
                for (const auto& hj : pj["holes"]) rings.push_back(hj.get<std::vector<double>>());
            }

            for (const auto& r : rings) {
                int m = (int)r.size() / 2;
                for (int a = 0; a < m; a++) {
                    int b = (a + 1) % m;
                    q.edges.push_back(r[a * 2]);
                    q.edges.push_back(r[a * 2 + 1]);
                    q.edges.push_back(r[b * 2]);
                    q.edges.push_back(r[b * 2 + 1]);
                    q.min_x = std::min(q.min_x, r[a * 2]);
                    q.max_x = std::max(q.max_x, r[a * 2]);
                    q.min_y = std::min(q.min_y, r[a * 2 + 1]);
                    q.max_y = std::max(q.max_y, r[a * 2 + 1]);
                }
            }
            prisms.push_back(q);
        }
    }

    std::vector<Tree> trees;
    if (j.contains("trees")) {
        auto& tj = j["trees"];
        std::vector<std::string> fields;
        if (tj.contains("fields")) fields = tj["fields"].get<std::vector<std::string>>();
        std::vector<double> data;
        if (tj.contains("data")) data = tj["data"].get<std::vector<double>>();

        int nf = (int)fields.size();
        if (nf > 0) {
            std::map<std::string, int> col;
            for (int i = 0; i < nf; i++) col[fields[i]] = i;
            auto get_val = [&](const std::vector<double>& row, const std::string& name, double def) -> double {
                auto it = col.find(name);
                return (it != col.end()) ? row[it->second] : def;
            };

            for (size_t k = 0; k + nf <= data.size(); k += nf) {
                std::vector<double> row(data.begin() + k, data.begin() + k + nf);
                Tree t;
                t.x = get_val(row, "x", 0.0);
                t.y = get_val(row, "y", 0.0);
                t.z = get_val(row, "z", 0.0);
                t.height = get_val(row, "height", 0.0);
                t.crown_r = get_val(row, "crownR", 1.0);
                t.crown_base = get_val(row, "crownBase", 0.0);
                t.trunk_r = get_val(row, "trunkR", 0.0);
                t.cx = get_val(row, "crownX", t.x);
                t.cy = get_val(row, "crownY", t.y);

                double cb = t.z + t.crown_base;
                double top = t.z + t.height;
                t.trunk_top = t.z + std::max(t.crown_base + 0.5 * (t.height - t.crown_base), 3.0);
                t.cz = (cb + top) / 2.0;
                t.rz = std::max((top - cb) / 2.0, 0.5);
                trees.push_back(t);
            }
        }
    }

    Rules rules;
    if (j.contains("rules")) {
        auto& rj = j["rules"];
        rules.max_step = rj.value("maxStep", 1.5);
        rules.max_slope_deg = rj.value("maxSlopeDeg", 50.0);
        rules.canopy_density = rj.value("canopyDensity", 0.35);
        rules.canopy_block_t = rj.value("canopyBlockT", 0.25);
    }
    if (rules.max_step == 0.0) rules.max_step = 1.5;

    w->init_geo(prisms, trees, rules);

    // Raster intervals onto cells
    std::map<int32_t, std::vector<Interval>> cells;
    if (j.contains("prisms") && j["prisms"].is_array()) {
        for (const auto& pj : j["prisms"]) {
            std::vector<std::vector<double>> rings;
            if (pj.contains("ring")) rings.push_back(pj["ring"].get<std::vector<double>>());
            if (pj.contains("holes")) {
                for (const auto& hj : pj["holes"]) rings.push_back(hj.get<std::vector<double>>());
            }
            if (rings.empty() || rings[0].empty()) continue;

            double minY = std::numeric_limits<double>::infinity();
            double maxY = -std::numeric_limits<double>::infinity();
            const auto& ring0 = rings[0];
            for (size_t k = 1; k < ring0.size(); k += 2) {
                minY = std::min(minY, ring0[k]);
                maxY = std::max(maxY, ring0[k]);
            }
            int j0 = static_cast<int>(std::ceil(minY - w->min_y));
            int j1 = static_cast<int>(std::floor(maxY - w->min_y));

            Interval iv;
            iv.base = static_cast<float>(pj.value("base", 0.0));
            iv.top = static_cast<float>(pj.value("top", 0.0));
            iv.bridge = (pj.value("kind", "") == "bridge");

            std::vector<double> xs;
            for (int jj = std::max(j0, 0); jj <= j1 && jj < w->ny; jj++) {
                double y = w->min_y + static_cast<double>(jj) + 1e-4;
                xs.clear();
                for (const auto& r : rings) {
                    int m = (int)r.size() / 2;
                    for (int a = 0; a < m; a++) {
                        int b = (a + 1) % m;
                        double x0 = r[a * 2], y0 = r[a * 2 + 1];
                        double x1 = r[b * 2], y1 = r[b * 2 + 1];
                        if ((y0 <= y) != (y1 <= y)) {
                            xs.push_back(x0 + (y - y0) / (y1 - y0) * (x1 - x0));
                        }
                    }
                }
                std::sort(xs.begin(), xs.end());
                for (size_t k = 0; k + 1 < xs.size(); k += 2) {
                    int i0 = static_cast<int>(std::ceil(xs[k] - w->min_x));
                    int i1 = static_cast<int>(std::floor(xs[k + 1] - w->min_x));
                    for (int ii = std::max(i0, 0); ii <= i1 && ii < w->nx; ii++) {
                        int32_t idx = static_cast<int32_t>(jj * w->nx + ii);
                        cells[idx].push_back(iv);
                    }
                }
            }
        }
    }

    w->top = w->ground;
    w->walk = w->ground;
    w->obst.assign(n, 0);
    w->low.assign(n, 0);
    w->has_slab.assign(n, 0);

    for (auto& [idx, ivs] : cells) {
        std::sort(ivs.begin(), ivs.end(), [](const Interval& a, const Interval& b) {
            return a.base < b.base;
        });
        float g = w->ground[idx];
        float top = g;
        float deck = -1e9f;
        bool low = false;

        for (const auto& iv : ivs) {
            if (iv.top <= top) continue;
            if (iv.base <= top + 1.5f) {
                top = iv.top;
                continue;
            }
            w->slabs[idx].push_back(Slab{iv.base, iv.top});
            w->has_slab[idx] = 1;
            if (iv.base - top < 10.5f) {
                if (iv.bridge && iv.top - g < 6.5f) {
                    deck = iv.top;
                } else {
                    low = true;
                }
            }
        }
        w->top[idx] = top;
        w->walk[idx] = top;
        if (deck > top) w->walk[idx] = deck;
        w->low[idx] = low ? 1 : 0;
        w->obst[idx] = (top - g > 1.2f || low) ? 1 : 0;
    }

    w->build_nav();
    return w;
}

std::shared_ptr<World> World::flat() {
    auto w = std::make_shared<World>();
    w->min_x = -513.0;
    w->min_y = -334.0;
    w->nx = 1070;
    w->ny = 724;
    w->bx0 = -512.0;
    w->bx1 = 555.0;
    w->by0 = -333.0;
    w->by1 = 388.0;
    int n = w->nx * w->ny;
    w->ground.assign(n, 0.0f);
    w->top.assign(n, 0.0f);
    w->walk.assign(n, 0.0f);
    w->obst.assign(n, 0);
    w->low.assign(n, 0);
    w->has_slab.assign(n, 0);
    w->init_geo({}, {}, Rules{1.5, 50.0, 0.35, 0.25});
    w->build_nav();
    return w;
}

int World::vidx(double x, double y) const {
    int i = static_cast<int>(std::round(x - min_x));
    int j = static_cast<int>(std::round(y - min_y));
    i = std::clamp(i, 0, nx - 1);
    j = std::clamp(j, 0, ny - 1);
    return j * nx + i;
}

bool World::in_bounds(double x, double y) const {
    return x > bx0 && x < bx1 && y > by0 && y < by1;
}

double World::ground_at(double x, double y) const {
    double fx = x - min_x;
    double fy = y - min_y;
    fx = std::clamp(fx, 0.0, static_cast<double>(nx - 1) - 1e-6);
    fy = std::clamp(fy, 0.0, static_cast<double>(ny - 1) - 1e-6);
    int i = static_cast<int>(fx);
    int j = static_cast<int>(fy);
    double tx = fx - i;
    double ty = fy - j;
    double a = ground[j * nx + i];
    double b = ground[j * nx + i + 1];
    double c = ground[(j + 1) * nx + i];
    double d = ground[(j + 1) * nx + i + 1];
    return (a * (1.0 - tx) + b * tx) * (1.0 - ty) + (c * (1.0 - tx) + d * tx) * ty;
}

double World::stack(double x, double y, bool deck) const {
    auto [z, _] = stack_kind(x, y, deck);
    return z;
}

std::pair<double, int> World::stack_kind(double x, double y, bool deck) const {
    double g = ground_at(x, y);
    double z = g;
    int id = -1;
    int c = cell_of(x, y);
    if (c < 0) return {z, id};

    const auto& ps = geo.grid_p[c];
    for (int pass = 0; pass < 8; pass++) {
        bool moved = false;
        for (int32_t pi : ps) {
            const auto& p = geo.prisms[pi];
            if (p.top <= z || x < p.min_x || x > p.max_x || y < p.min_y || y > p.max_y) continue;
            if (!(p.base <= z + 1.5 || (deck && p.kind == "bridge" && p.top - g < 6.5))) continue;
            if (point_in_poly(p.edges, x, y)) {
                z = p.top;
                id = static_cast<int>(pi);
                moved = true;
            }
        }
        if (!moved) break;
    }
    return {z, id};
}

bool World::solid(double x, double y, double z) const {
    if (z < ground_at(x, y)) return true;
    int c = cell_of(x, y);
    if (c < 0) return false;
    for (int32_t pi : geo.grid_p[c]) {
        const auto& p = geo.prisms[pi];
        if (z > p.base && z < p.top && x >= p.min_x && x <= p.max_x && y >= p.min_y && y <= p.max_y &&
            point_in_poly(p.edges, x, y)) {
            return true;
        }
    }
    return false;
}

bool World::solid_raster(double x, double y, double z) const {
    int idx = vidx(x, y);
    if (z < static_cast<double>(top[idx]) - 0.05) return true;
    if (has_slab[idx]) {
        auto it = slabs.find(idx);
        if (it != slabs.end()) {
            for (const auto& s : it->second) {
                if (z > static_cast<double>(s.base) && z < static_cast<double>(s.top)) return true;
            }
        }
    }
    return false;
}

bool World::clear_raster(const Vec3& a, const Vec3& b) const {
    double dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
    double d = std::sqrt(dx * dx + dy * dy + dz * dz);
    int n = static_cast<int>(d / 1.0) + 1;
    double inv = 1.0 / static_cast<double>(n);
    for (int k = 1; k < n; k++) {
        double t = static_cast<double>(k) * inv;
        if (solid_raster(a[0] + dx * t, a[1] + dy * t, a[2] + dz * t)) return false;
    }
    return true;
}

bool World::standable(double x, double y, double z, double r) const {
    if (x < bx0 + r || x > bx1 - r || y < by0 + r || y > by1 - r) return false;
    return !wall_within(x, y, z, r, 9.0);
}

bool World::wall_within(double x, double y, double z, double r, double h) const {
    double lo = z + STEP_UP, hi = z + h;
    double r2 = r * r;
    bool found = false;
    for_cells(x - r, y - r, x + r, y + r, [&](int c) {
        if (found) return;
        for (int32_t pi : geo.grid_p[c]) {
            const auto& p = geo.prisms[pi];
            if (p.top <= lo || p.base >= hi || x + r < p.min_x || x - r > p.max_x || y + r < p.min_y || y - r > p.max_y) continue;
            const auto& e = p.edges;
            for (size_t i = 0; i < e.size(); i += 4) {
                double x0 = e[i], y0 = e[i + 1];
                double ux = e[i + 2] - x0, uy = e[i + 3] - y0;
                double l2 = ux * ux + uy * uy;
                double t = 0.0;
                if (l2 > 1e-9) {
                    t = std::clamp(((x - x0) * ux + (y - y0) * uy) / l2, 0.0, 1.0);
                }
                double mx = x0 + ux * t - x, my = y0 + uy * t - y;
                if (mx * mx + my * my < r2) {
                    found = true;
                    return;
                }
            }
            if (point_in_poly(e, x, y)) {
                found = true;
                return;
            }
        }
    });
    return found;
}

void World::build_nav() {
    ns = 2.0;
    nnx = (nx + 1) / 2;
    nny = (ny + 1) / 2;
    int n = nnx * nny;
    blocked.assign(n, 0);
    surf.assign(n, 0.0f);

    for (int c = 0; c < n; c++) {
        auto [x, y] = cell_pos(c);
        auto [z, id] = stack_kind(x, y, true);
        surf[c] = static_cast<float>(z);

        bool roof = id >= 0 && geo.prisms[id].kind != "bridge" && (z - ground_at(x, y) > 1.5);
        blocked[c] = (roof || !standable(x, y, z, NAV_RADIUS)) ? 1 : 0;
    }

    clearance.assign(n, 1e9f);
    std::vector<int32_t> q;
    q.reserve(n);
    for (int c = 0; c < n; c++) {
        if (blocked[c]) {
            clearance[c] = 0.0f;
            q.push_back(static_cast<int32_t>(c));
        }
    }

    for (size_t h = 0; h < q.size(); h++) {
        int c = q[h];
        float d = clearance[c] + static_cast<float>(ns);
        if (d > 20.0f) continue;
        int ci = c % nnx, cj = c / nnx;
        for (const auto& o : std::array<std::array<int, 2>, 4>{{ {1, 0}, {-1, 0}, {0, 1}, {0, -1} }}) {
            int i = ci + o[0], j = cj + o[1];
            if (i < 0 || j < 0 || i >= nnx || j >= nny) continue;
            int nb = j * nnx + i;
            if (clearance[nb] > d) {
                clearance[nb] = d;
                q.push_back(static_cast<int32_t>(nb));
            }
        }
    }
    for (int c = 0; c < n; c++) {
        if (clearance[c] > 20.0f) clearance[c] = 20.0f;
    }

    comp.assign(n, 0);
    int32_t label = 0, best_label = 0;
    int best_size = 0;
    for (int c0 = 0; c0 < n; c0++) {
        if (blocked[c0] || comp[c0] != 0) continue;
        label++;
        comp[c0] = label;
        q.clear();
        q.push_back(static_cast<int32_t>(c0));
        for (size_t h = 0; h < q.size(); h++) {
            int c = q[h];
            int ci = c % nnx, cj = c / nnx;
            for (const auto& o : std::array<std::array<int, 2>, 4>{{ {1, 0}, {-1, 0}, {0, 1}, {0, -1} }}) {
                int i = ci + o[0], j = cj + o[1];
                if (i < 0 || j < 0 || i >= nnx || j >= nny) continue;
                int nb = j * nnx + i;
                if (comp[nb] == 0 && can_step(c, nb, false) && can_step(nb, c, false)) {
                    comp[nb] = label;
                    q.push_back(static_cast<int32_t>(nb));
                }
            }
        }
        if ((int)q.size() > best_size) {
            best_size = (int)q.size();
            best_label = label;
        }
    }
    main_comp = best_label;

    g.assign(n, 0.0f);
    came.assign(n, 0);
    stamp.assign(n, 0);
    closed.assign(n, 0);
}

int World::cell(double x, double y) const {
    int ci = static_cast<int>(std::round((x - min_x) / ns));
    int cj = static_cast<int>(std::round((y - min_y) / ns));
    ci = std::clamp(ci, 0, nnx - 1);
    cj = std::clamp(cj, 0, nny - 1);
    return cj * nnx + ci;
}

std::pair<double, double> World::cell_pos(int c) const {
    return {min_x + static_cast<double>(c % nnx) * ns, min_y + static_cast<double>(c / nnx) * ns};
}

bool World::free_cell(double x, double y) const {
    return !blocked[cell(x, y)];
}

int World::nearest_free(int c) const {
    if (!blocked[c]) return c;
    int ci = c % nnx, cj = c / nnx;
    int best = -1, best_d = std::numeric_limits<int>::max();
    for (int r = 1; r <= 20; r++) {
        for (int dj = -r; dj <= r; dj++) {
            for (int di = -r; di <= r; di++) {
                if (std::max(std::abs(di), std::abs(dj)) != r) continue;
                int i = ci + di, j = cj + dj;
                if (i < 0 || j < 0 || i >= nnx || j >= nny) continue;
                if (!blocked[j * nnx + i]) {
                    int d = di * di + dj * dj;
                    if (d < best_d) {
                        best = j * nnx + i;
                        best_d = d;
                    }
                }
            }
        }
        if (best >= 0) return best;
    }
    return -1;
}

bool World::can_step(int a, int b, bool diag) const {
    if (blocked[b]) return false;
    float rise = surf[b] - surf[a];
    float lim = diag ? 3.1f : 2.2f;
    return rise <= lim;
}

void World::push_heap(HeapItem it) {
    heap.push_back(it);
    size_t i = heap.size() - 1;
    while (i > 0) {
        size_t p = (i - 1) / 2;
        if (heap[p].f <= heap[i].f) break;
        std::swap(heap[p], heap[i]);
        i = p;
    }
}

HeapItem World::pop_heap() {
    HeapItem top = heap[0];
    size_t last = heap.size() - 1;
    heap[0] = heap[last];
    heap.pop_back();
    last--;
    size_t i = 0;
    while (true) {
        size_t l = 2 * i + 1, r = 2 * i + 2;
        size_t m = i;
        if (l <= last && heap[l].f < heap[m].f) m = l;
        if (r <= last && heap[r].f < heap[m].f) m = r;
        if (m == i) break;
        std::swap(heap[m], heap[i]);
        i = m;
    }
    return top;
}

std::pair<std::vector<int32_t>, bool> World::path(double sx, double sy, double gx, double gy, int max_expand) {
    int s = nearest_free(cell(sx, sy));
    int g_idx = nearest_free(cell(gx, gy));
    if (s < 0 || g_idx < 0) return {{}, false};
    if (s == g_idx) return {{static_cast<int32_t>(s)}, true};

    gen++;
    heap.clear();
    int gi = g_idx % nnx, gj = g_idx / nnx;
    auto heuristic = [&](int c) -> float {
        double dx = static_cast<double>(std::abs(c % nnx - gi));
        double dy = static_cast<double>(std::abs(c / nnx - gj));
        double mn = std::min(dx, dy), mx = std::max(dx, dy);
        return static_cast<float>((mx + 0.4142 * mn) * ns * 1.15);
    };

    g[s] = 0.0f;
    came[s] = -1;
    stamp[s] = gen;
    push_heap(HeapItem{heuristic(s), static_cast<int32_t>(s)});

    int best = s;
    float best_h = heuristic(s);
    bool found = false;

    for (int n = 0; !heap.empty() && n < max_expand; n++) {
        HeapItem it = pop_heap();
        int c = it.idx;
        if (closed[c] == gen) continue;
        closed[c] = gen;
        if (c == g_idx) {
            found = true;
            best = c;
            break;
        }
        float hc = heuristic(c);
        if (hc < best_h) {
            best = c;
            best_h = hc;
        }
        int ci = c % nnx, cj = c / nnx;
        for (int k = 0; k < 8; k++) {
            int i = ci + NBRS[k][0], j = cj + NBRS[k][1];
            if (i < 0 || j < 0 || i >= nnx || j >= nny) continue;
            int nb = j * nnx + i;
            bool diag = (k >= 4);
            if (closed[nb] == gen || !can_step(c, nb, diag)) continue;
            float step = static_cast<float>(ns);
            if (diag) {
                if (blocked[cj * nnx + i] || blocked[j * nnx + ci]) continue;
                step *= 1.4142f;
            }
            float cl = clearance[nb];
            if (cl < 4.0f) {
                step *= 1.0f + (4.0f - cl) * 0.15f;
            }
            float ng = g[c] + step;
            if (stamp[nb] != gen || ng < g[nb]) {
                g[nb] = ng;
                came[nb] = static_cast<int32_t>(c);
                stamp[nb] = gen;
                push_heap(HeapItem{ng + heuristic(nb), static_cast<int32_t>(nb)});
            }
        }
    }

    std::vector<int32_t> result;
    for (int c = best; c >= 0; c = came[c]) {
        result.push_back(static_cast<int32_t>(c));
        if (c == s) break;
    }
    std::reverse(result.begin(), result.end());
    return {result, found};
}

bool World::line_walkable(double x0, double y0, double x1, double y1) const {
    double dx = x1 - x0, dy = y1 - y0;
    double d = std::hypot(dx, dy);
    int n = static_cast<int>(d / 1.0) + 1;
    int prev = cell(x0, y0);
    for (int k = 1; k <= n; k++) {
        double t = static_cast<double>(k) / static_cast<double>(n);
        int c = cell(x0 + dx * t, y0 + dy * t);
        if (c == prev) continue;
        if (blocked[c] || surf[c] - surf[prev] > 3.1f) return false;
        prev = c;
    }
    return true;
}

bool World::can_stand(double x, double y, double z, double r) const {
    if (x < bx0 + r || x > bx1 - r || y < by0 + r || y > by1 - r) return false;
    return !wall_within(x, y, z, r, 9.0);
}

int World::get_main_near(int c) {
    if (main_near.empty()) {
        int n = nnx * nny;
        main_near.assign(n, -1);
        std::vector<uint8_t> depth(n, 0);
        std::vector<int32_t> q;
        q.reserve(n);
        for (int i = 0; i < n; i++) {
            if (!blocked[i] && comp[i] == main_comp) {
                main_near[i] = static_cast<int32_t>(i);
                q.push_back(static_cast<int32_t>(i));
            }
        }
        for (size_t h = 0; h < q.size(); h++) {
            int curr = q[h];
            if (depth[curr] >= 20) continue;
            int ci = curr % nnx, cj = curr / nnx;
            for (const auto& o : NBRS) {
                int i = ci + o[0], j = cj + o[1];
                if (i < 0 || j < 0 || i >= nnx || j >= nny) continue;
                int nb = j * nnx + i;
                if (main_near[nb] < 0) {
                    main_near[nb] = main_near[curr];
                    depth[nb] = depth[curr] + 1;
                    q.push_back(static_cast<int32_t>(nb));
                }
            }
        }
    }
    return main_near[c];
}

bool World::off_main(double x, double y) {
    int c = nearest_free(cell(x, y));
    return c < 0 || comp[c] != main_comp;
}

std::tuple<Vec2, Vec2, bool> World::escape_plan(double x, double y) {
    int s = nearest_free(cell(x, y));
    if (s < 0) return {{0, 0}, {0, 0}, false};

    gen++;
    std::vector<int32_t> q;
    q.push_back(static_cast<int32_t>(s));
    stamp[s] = gen;
    g[s] = 0.0f;

    int best = -1;
    double best_s = std::numeric_limits<double>::infinity();

    for (size_t h = 0; h < q.size() && h < 60000; h++) {
        int c = q[h];
        int ci = c % nnx, cj = c / nnx;
        int m = get_main_near(c);
        if (m >= 0) {
            auto [cx, cy] = cell_pos(c);
            auto [mx, my] = cell_pos(m);
            double sc = static_cast<double>(g[c]) * ns + 4.0 * std::hypot(mx - cx, my - cy);
            if (sc < best_s) {
                best = c;
                best_s = sc;
            }
        }
        for (int k = 0; k < 8; k++) {
            int i = ci + NBRS[k][0], j = cj + NBRS[k][1];
            if (i < 0 || j < 0 || i >= nnx || j >= nny) continue;
            int nb = j * nnx + i;
            bool diag = (k >= 4);
            if (stamp[nb] == gen || !can_step(c, nb, diag)) continue;
            if (diag && (blocked[cj * nnx + i] || blocked[j * nnx + ci])) continue;
            stamp[nb] = gen;
            g[nb] = g[c] + 1.0f;
            q.push_back(static_cast<int32_t>(nb));
        }
    }
    if (best < 0) return {{0, 0}, {0, 0}, false};

    auto [lx, ly] = cell_pos(best);
    auto [mx, my] = cell_pos(get_main_near(best));
    double d = std::hypot(mx - lx, my - ly);
    if (d > 0.1) {
        double ex = mx + (mx - lx) / d * 5.0;
        double ey = my + (my - ly) / d * 5.0;
        if (in_bounds(ex, ey) && reachable(ex, ey)) {
            mx = ex;
            my = ey;
        }
    }
    return {{lx, ly}, {mx, my}, true};
}

bool World::reachable(double x, double y) const {
    int c = cell(x, y);
    return !blocked[c] && comp[c] == main_comp;
}

double World::exposure(double x, double y) const {
    double z = walk_at(x, y) + 7.0;
    double total = 0.0;
    for (int k = 0; k < 24; k++) {
        double a = static_cast<double>(k) * M_PI / 12.0;
        double c = std::cos(a), s = std::sin(a);
        double d = 2.5;
        for (; d < 200.0; d += 2.5) {
            double px = x + c * d, py = y + s * d;
            if (!in_bounds(px, py) || solid_raster(px, py, z)) break;
        }
        total += d;
    }
    return total / (24.0 * 200.0);
}

void World::init_geo(std::vector<Prism> prisms, std::vector<Tree> trees, Rules rules) {
    geo.prisms = std::move(prisms);
    geo.trees = std::move(trees);
    geo.rules = rules;
    if (geo.rules.max_slope_deg == 0.0) geo.rules.max_slope_deg = 50.0;
    if (geo.rules.canopy_density == 0.0) {
        geo.rules.canopy_density = 0.35;
        geo.rules.canopy_block_t = 0.25;
    }
    geo.max_slope_tan = std::tan(geo.rules.max_slope_deg * M_PI / 180.0);
    geo.gx0 = bx0 - GEO_CELL;
    geo.gy0 = by0 - GEO_CELL;
    geo.gnx = static_cast<int>(std::ceil((bx1 - bx0) / GEO_CELL)) + 3;
    geo.gny = static_cast<int>(std::ceil((by1 - by0) / GEO_CELL)) + 3;

    int total_cells = geo.gnx * geo.gny;
    geo.grid_p.assign(total_cells, {});
    geo.grid_t.assign(total_cells, {});

    for (size_t i = 0; i < geo.prisms.size(); i++) {
        const auto& p = geo.prisms[i];
        for_cells(p.min_x, p.min_y, p.max_x, p.max_y, [&](int c) {
            geo.grid_p[c].push_back(static_cast<int32_t>(i));
        });
    }

    for (size_t i = 0; i < geo.trees.size(); i++) {
        const auto& t = geo.trees[i];
        double r = t.crown_r;
        for_cells(std::min(t.cx - r, t.x - t.trunk_r), std::min(t.cy - r, t.y - t.trunk_r),
                  std::max(t.cx + r, t.x + t.trunk_r), std::max(t.cy + r, t.y + t.trunk_r),
                  [&](int c) {
                      geo.grid_t[c].push_back(static_cast<int32_t>(i));
                  });
    }

    geo.bnx = (nx + 7) / 8;
    geo.bny = (ny + 7) / 8;
    int btotal = geo.bnx * geo.bny;
    std::vector<float> bm(btotal, -std::numeric_limits<float>::infinity());
    for (int j = 0; j < ny; j++) {
        for (int i = 0; i < nx; i++) {
            int b = (j / 8) * geo.bnx + i / 8;
            float h = ground[j * nx + i];
            if (h > bm[b]) bm[b] = h;
        }
    }
    geo.block_max.assign(btotal, -std::numeric_limits<float>::infinity());
    for (int j = 0; j < geo.bny; j++) {
        for (int i = 0; i < geo.bnx; i++) {
            float v = bm[j * geo.bnx + i];
            if (i + 1 < geo.bnx) v = std::max(v, bm[j * geo.bnx + i + 1]);
            if (j + 1 < geo.bny) v = std::max(v, bm[(j + 1) * geo.bnx + i]);
            if (i + 1 < geo.bnx && j + 1 < geo.bny) v = std::max(v, bm[(j + 1) * geo.bnx + i + 1]);
            geo.block_max[j * geo.bnx + i] = v;
        }
    }
}

int World::cell_of(double x, double y) const {
    int i = static_cast<int>(std::floor((x - geo.gx0) / GEO_CELL));
    int j = static_cast<int>(std::floor((y - geo.gy0) / GEO_CELL));
    if (i < 0 || j < 0 || i >= geo.gnx || j >= geo.gny) return -1;
    return j * geo.gnx + i;
}

void World::for_cells(double x0, double y0, double x1, double y1, const std::function<void(int)>& f) const {
    int i0 = std::max(0, static_cast<int>(std::floor((x0 - geo.gx0) / GEO_CELL)));
    int i1 = std::min(geo.gnx - 1, static_cast<int>(std::floor((x1 - geo.gx0) / GEO_CELL)));
    int j0 = std::max(0, static_cast<int>(std::floor((y0 - geo.gy0) / GEO_CELL)));
    int j1 = std::min(geo.gny - 1, static_cast<int>(std::floor((y1 - geo.gy0) / GEO_CELL)));
    for (int j = j0; j <= j1; j++) {
        for (int i = i0; i <= i1; i++) {
            f(j * geo.gnx + i);
        }
    }
}

void World::walk_cells(double x0, double y0, double x1, double y1, const std::function<double(int)>& f) const {
    walk_cells_t(x0, y0, x1, y1, [&](int c, double, double) { return f(c); });
}

void World::walk_cells_t(double x0, double y0, double x1, double y1,
                         const std::function<double(int, double, double)>& f) const {
    double dx = x1 - x0, dy = y1 - y0;
    int ci = static_cast<int>(std::floor((x0 - geo.gx0) / GEO_CELL));
    int cj = static_cast<int>(std::floor((y0 - geo.gy0) / GEO_CELL));
    int ei = static_cast<int>(std::floor((x1 - geo.gx0) / GEO_CELL));
    int ej = static_cast<int>(std::floor((y1 - geo.gy0) / GEO_CELL));
    int si = (dx > 0) ? 1 : -1;
    int sj = (dy > 0) ? 1 : -1;

    double inf = std::numeric_limits<double>::infinity();
    double tdx = inf, tdy = inf, tmx = inf, tmy = inf;

    if (std::abs(dx) > 1e-9) {
        tdx = GEO_CELL / std::abs(dx);
        if (dx > 0) tmx = (static_cast<double>(ci + 1) * GEO_CELL + geo.gx0 - x0) / std::abs(dx);
        else tmx = (x0 - (static_cast<double>(ci) * GEO_CELL + geo.gx0)) / std::abs(dx);
    }
    if (std::abs(dy) > 1e-9) {
        tdy = GEO_CELL / std::abs(dy);
        if (dy > 0) tmy = (static_cast<double>(cj + 1) * GEO_CELL + geo.gy0 - y0) / std::abs(dy);
        else tmy = (y0 - (static_cast<double>(cj) * GEO_CELL + geo.gy0)) / std::abs(dy);
    }

    double best = inf;
    double tin = 0.0;
    for (int k = 0; k < 4096; k++) {
        if (ci >= 0 && cj >= 0 && ci < geo.gnx && cj < geo.gny) {
            best = f(cj * geo.gnx + ci, tin, std::min(1.0, std::min(tmx, tmy)));
        }
        if (ci == ei && cj == ej) return;
        double t;
        if (tmx < tmy) {
            t = tmx;
            tmx += tdx;
            ci += si;
        } else {
            t = tmy;
            tmy += tdy;
            cj += sj;
        }
        if (t > 1.0 || best < t) return;
        tin = t;
    }
}

std::pair<double, double> World::ground_gradient(double x, double y) const {
    return {(ground_at(x + 1.0, y) - ground_at(x - 1.0, y)) / 2.0,
            (ground_at(x, y + 1.0) - ground_at(x, y - 1.0)) / 2.0};
}

double World::surface_at(double x, double y, double max_z) const {
    auto [z, _] = surface_kind(x, y, max_z);
    return z;
}

std::pair<double, int> World::surface_kind(double x, double y, double max_z) const {
    double z = ground_at(x, y);
    int id = -1;
    int c = cell_of(x, y);
    if (c < 0) return {z, id};
    for (int32_t pi : geo.grid_p[c]) {
        const auto& p = geo.prisms[pi];
        if (p.top > max_z || p.top <= z || x < p.min_x || x > p.max_x || y < p.min_y || y > p.max_y ||
            !point_in_poly(p.edges, x, y)) {
            continue;
        }
        z = p.top;
        id = static_cast<int>(pi);
    }
    return {z, id};
}

double World::ceiling_above(double x, double y, double z, double r) const {
    double best = std::numeric_limits<double>::infinity();
    for_cells(x - r, y - r, x + r, y + r, [&](int c) {
        for (int32_t pi : geo.grid_p[c]) {
            const auto& p = geo.prisms[pi];
            if (p.base < z - 0.01 || p.base >= best || x < p.min_x || x > p.max_x || y < p.min_y || y > p.max_y) continue;
            if (point_in_poly(p.edges, x, y)) {
                best = p.base;
            }
        }
    });
    return best;
}

std::tuple<double, double, double, std::string, int> World::penetration(double x, double y, double z, double r, double h) const {
    std::string kind = "terrain";
    int id = -1;
    double depth = 0.0, nx_out = 0.0, ny_out = 0.0;
    double lo = z + STEP_UP, hi = z + h;

    auto put = [&](double d, double ax, double ay, const std::string& k, int i) {
        if (d > depth) {
            depth = d;
            nx_out = ax;
            ny_out = ay;
            kind = k;
            id = i;
        }
    };

    for_cells(x - r, y - r, x + r, y + r, [&](int c) {
        for (int32_t pi : geo.grid_p[c]) {
            const auto& p = geo.prisms[pi];
            if (p.top <= lo || p.base >= hi || x + r < p.min_x || x - r > p.max_x || y + r < p.min_y || y - r > p.max_y) continue;
            double cx, cy;
            double d = closest_on_edges(p.edges, x, y, cx, cy);
            if (point_in_poly(p.edges, x, y)) {
                double ux = cx - x, uy = cy - y;
                double l = std::hypot(ux, uy);
                if (l == 0.0) l = 1e-9;
                put(l + r, ux / l, uy / l, p.kind, static_cast<int>(pi));
            } else if (d < r) {
                double l = d;
                if (l == 0.0) l = 1e-9;
                put(r - d, (x - cx) / l, (y - cy) / l, p.kind, static_cast<int>(pi));
            }
        }
        if (TRUNK_WALLS) {
            for (int32_t ti : geo.grid_t[c]) {
                const auto& t = geo.trees[ti];
                if (t.trunk_top <= lo || t.z - 1.0 >= hi) continue;
                double ux = x - t.x, uy = y - t.y;
                double d = std::hypot(ux, uy);
                double f = r + t.trunk_r;
                if (d < f) {
                    if (d > 1e-9) put(f - d, ux / d, uy / d, "trunk", static_cast<int>(ti));
                    else put(f - d, 1.0, 0.0, "trunk", static_cast<int>(ti));
                }
            }
        }
    });

    if (ground_at(x, y) > lo) {
        auto [gx, gy] = ground_gradient(x, y);
        double n = std::hypot(gx, gy);
        if (n > 0.001) {
            double ux = -gx / n, uy = -gy / n;
            double l = 0.0;
            while (l < 2.0 * r && ground_at(x + ux * l, y + uy * l) > lo) {
                l += 0.25;
            }
            put(std::max(l, 0.05), ux, uy, "terrain", -1);
        }
    }

    put(bx0 + r - x, 1.0, 0.0, "terrain", -2);
    put(x + r - bx1, -1.0, 0.0, "terrain", -2);
    put(by0 + r - y, 0.0, 1.0, "terrain", -2);
    put(y + r - by1, 0.0, -1.0, "terrain", -2);

    return {depth, nx_out, ny_out, kind, id};
}

bool World::is_walkable(double x, double y, double r, double max_z, double h) const {
    if (x - r < bx0 || x + r > bx1 || y - r < by0 || y + r > by1) return false;
    if (std::isnan(max_z)) max_z = ground_at(x, y) + STEP_UP;
    double z = surface_at(x, y, max_z);
    if (z <= ground_at(x, y) + 0.01) {
        auto [gx, gy] = ground_gradient(x, y);
        if (std::hypot(gx, gy) > geo.max_slope_tan) return false;
    }
    auto [d, _nx, _ny, _k, _id] = penetration(x, y, z, r, h);
    return d <= 0.001;
}

MoveResult World::move_and_slide(double x, double y, double z, double r, double h, double dx, double dy, double dz) const {
    double ox = x, oy = y, oz = z;
    int n = std::max(1, static_cast<int>(std::ceil(std::hypot(dx, dy) / (r * 0.4))));
    double sx = dx / static_cast<double>(n), sy = dy / static_cast<double>(n);
    double ms = STEP_UP;
    int walls = 0;
    std::array<int, 8> seen{};

    for (int k = 0; k < n; k++) {
        x += sx;
        y += sy;
        for (int it = 0; it < 4; it++) {
            auto [d, nx, ny, _kind, id] = penetration(x, y, z, r, h);
            if (d <= 1e-4) break;
            x += nx * (d + 0.001);
            y += ny * (d + 0.001);
            bool dup = false;
            for (int i = 0; i < walls && i < (int)seen.size(); i++) {
                if (seen[i] == id) dup = true;
            }
            if (!dup && walls < (int)seen.size()) {
                seen[walls] = id;
                walls++;
            }
        }
        double s = surface_at(x, y, z + ms);
        if (s > z && dz <= 0.0) z = s;
    }

    MoveResult res;
    res.x = x;
    res.y = y;
    res.walls = walls;

    double surf_h = surface_at(x, y, z + ms);
    double nz = z + dz;
    if (dz > 0.0) {
        double c = ceiling_above(x, y, z + h, r);
        if (nz + h > c) {
            nz = c - h;
            res.stopped_z = true;
        }
    }
    if (nz <= surf_h + 1e-4) {
        nz = surf_h;
        res.grounded = true;
        res.stopped_z = res.stopped_z || (dz < 0.0);
    } else if (dz <= 0.0 && nz - surf_h <= 0.75 && oz - surface_at(ox, oy, oz + 0.01) < 0.05) {
        nz = surf_h;
        res.grounded = true;
    }
    res.z = nz;
    return res;
}

std::pair<Hit, bool> World::ray_prism(int pi, double x, double y, double z,
                                      double dx, double dy, double dz, double tmax) const {
    const auto& p = geo.prisms[pi];
    double t0 = 0.0, t1 = tmax;

    auto slab = [&](double o, double d, double lo, double hi) -> bool {
        if (std::abs(d) < 1e-9) return o >= lo && o <= hi;
        double a = (lo - o) / d, b = (hi - o) / d;
        if (a > b) std::swap(a, b);
        t0 = std::max(t0, a);
        t1 = std::min(t1, b);
        return t0 <= t1;
    };

    if (!slab(x, dx, p.min_x, p.max_x) || !slab(y, dy, p.min_y, p.max_y) || !slab(z, dz, p.base, p.top)) {
        return {Hit{}, false};
    }

    if (z >= p.base && z <= p.top && point_in_poly(p.edges, x, y)) {
        double l = std::sqrt(dx * dx + dy * dy + dz * dz) + 1e-300;
        Hit h;
        h.t = 0.0;
        h.x = x;
        h.y = y;
        h.z = z;
        h.nx = -dx / l;
        h.ny = -dy / l;
        h.nz = -dz / l;
        h.kind = p.kind;
        h.id = pi;
        return {h, true};
    }

    Hit h;
    bool ok = false;
    double best = tmax;
    const auto& e = p.edges;

    for (size_t i = 0; i < e.size(); i += 4) {
        double ex = e[i + 2] - e[i], ey = e[i + 3] - e[i + 1];
        double den = dx * ey - dy * ex;
        if (std::abs(den) < 1e-9) continue;
        double px = e[i] - x, py = e[i + 1] - y;
        double t = (px * ey - py * ex) / den;
        double s = (px * dy - py * dx) / den;
        if (t < 0.0 || t >= best || s < 0.0 || s > 1.0) continue;
        double hz = z + dz * t;
        if (hz < p.base || hz > p.top) continue;
        double l = std::hypot(ex, ey);
        best = t;
        h.t = t;
        h.x = x + dx * t;
        h.y = y + dy * t;
        h.z = hz;
        h.nx = ey / l;
        h.ny = -ex / l;
        h.nz = 0.0;
        h.kind = p.kind;
        h.id = pi;
        ok = true;
    }

    if (std::abs(dz) > 1e-9) {
        for (const auto& cap : std::array<std::pair<double, double>, 2>{{ {p.top, 1.0}, {p.base, -1.0} }}) {
            double t = (cap.first - z) / dz;
            if (t < 0.0 || t >= best || (cap.second > 0.0 && dz > 0.0) || (cap.second < 0.0 && dz < 0.0)) continue;
            double hx = x + dx * t, hy = y + dy * t;
            if (point_in_poly(e, hx, hy)) {
                best = t;
                h.t = t;
                h.x = hx;
                h.y = hy;
                h.z = cap.first;
                h.nx = 0.0;
                h.ny = 0.0;
                h.nz = cap.second;
                h.kind = p.kind;
                h.id = pi;
                ok = true;
            }
        }
    }
    return {h, ok};
}

std::pair<Hit, bool> World::ray_terrain(double x, double y, double z,
                                       double x1, double y1, double z1, double tmax) const {
    double dx = x1 - x, dy = y1 - y, dz = z1 - z;
    double hl = std::hypot(dx, dy);
    const double blk = 8.0;

    auto above = [&](double t) -> double {
        return z + dz * t - ground_at(x + dx * t, y + dy * t);
    };

    if (above(0.0) < 0.0) {
        Hit h;
        h.t = 0.0;
        h.x = x;
        h.y = y;
        h.z = z;
        h.nx = 0.0;
        h.ny = 0.0;
        h.nz = 1.0;
        h.kind = "terrain";
        h.id = -1;
        return {h, true};
    }

    double step = 1.0;
    if (hl > 1e-9) step = 0.5 / hl;

    double t = 0.0;
    for (int it = 0; t < tmax; it++) {
        if (it > 100000) return {Hit{}, false};
        double px = x + dx * t, py = y + dy * t;
        int bi = static_cast<int>(std::floor((px - min_x) / blk));
        int bj = static_cast<int>(std::floor((py - min_y) / blk));
        bool inb = (bi >= 0 && bj >= 0 && bi < geo.bnx && bj < geo.bny);
        double tb = tmax;
        if (hl > 1e-9) {
            double ex = min_x + static_cast<double>(bi) * blk;
            double ey = min_y + static_cast<double>(bj) * blk;
            double nx_val = std::numeric_limits<double>::infinity();
            double ny_val = std::numeric_limits<double>::infinity();
            if (dx > 1e-9) nx_val = (ex + blk - px) / dx;
            else if (dx < -1e-9) nx_val = (ex - px) / dx;
            if (dy > 1e-9) ny_val = (ey + blk - py) / dy;
            else if (dy < -1e-9) ny_val = (ey - py) / dy;
            tb = std::min(t + std::max(0.0, std::min(nx_val, ny_val)) + 1e-6, tmax);
        }
        if (inb && std::min(z + dz * t, z + dz * tb) > static_cast<double>(geo.block_max[bj * geo.bnx + bi])) {
            t = tb;
            continue;
        }
        double s = std::min(t + step, tmax);
        if (above(s) < 0.0) {
            double lo = t, hi = s;
            for (int k = 0; k < 20; k++) {
                double m = (lo + hi) / 2.0;
                if (above(m) < 0.0) hi = m;
                else lo = m;
            }
            double hx = x + dx * hi, hy = y + dy * hi;
            auto [gx, gy] = ground_gradient(hx, hy);
            double l = std::sqrt(gx * gx + gy * gy + 1.0);
            Hit h;
            h.t = hi;
            h.x = hx;
            h.y = hy;
            h.z = ground_at(hx, hy);
            h.nx = -gx / l;
            h.ny = -gy / l;
            h.nz = 1.0 / l;
            h.kind = "terrain";
            h.id = -1;
            return {h, true};
        }
        if (s >= tmax) break;
        t = s;
    }
    return {Hit{}, false};
}

std::pair<Hit, bool> World::raycast(const Vec3& a, const Vec3& b, RayOpts o) const {
    double x = a[0], y = a[1], z = a[2];
    double dx = b[0] - x, dy = b[1] - y, dz = b[2] - z;
    Hit best;
    bool found = false;

    auto tmax = [&]() -> double {
        return found ? best.t : 1.0;
    };

    std::vector<int32_t> seen_p, seen_t;
    seen_p.reserve(64);
    seen_t.reserve(64);

    auto has = [](const std::vector<int32_t>& s, int32_t v) -> bool {
        return std::find(s.begin(), s.end(), v) != s.end();
    };

    walk_cells(x, y, b[0], b[1], [&](int c) -> double {
        for (int32_t pi : geo.grid_p[c]) {
            if (has(seen_p, pi)) continue;
            seen_p.push_back(pi);
            auto [h, ok] = ray_prism(static_cast<int>(pi), x, y, z, dx, dy, dz, tmax());
            if (ok) {
                best = h;
                found = true;
            }
        }
        for (int32_t ti : geo.grid_t[c]) {
            if (has(seen_t, ti)) continue;
            seen_t.push_back(ti);
            const auto& tr = geo.trees[ti];
            if (!o.no_trunks) {
                auto [t, ok] = ray_trunk(tr.x, tr.y, tr.trunk_r, tr.z - 1.0, tr.trunk_top, x, y, z, dx, dy, dz, tmax());
                if (ok) {
                    best = Hit{t, x + dx * t, y + dy * t, z + dz * t, 0, 0, 0, "trunk", static_cast<int>(ti)};
                    found = true;
                }
            }
            if (o.canopy) {
                auto [t0, _, ok] = ray_crown(tr, x, y, z, dx, dy, dz);
                if (ok && t0 < tmax()) {
                    double t = std::max(t0, 0.0);
                    best = Hit{t, x + dx * t, y + dy * t, z + dz * t, 0, 0, 0, "canopy", static_cast<int>(ti)};
                    found = true;
                }
            }
        }
        return tmax();
    });

    if (!o.no_terrain) {
        auto [h, ok] = ray_terrain(x, y, z, b[0], b[1], b[2], tmax());
        if (ok) {
            best = h;
            found = true;
        }
    }
    return {best, found};
}

double World::canopy_transmittance(const Vec3& a, const Vec3& b) const {
    return std::exp(-geo.rules.canopy_density * crown_meters(a, b, std::numeric_limits<double>::infinity()));
}

double World::crown_meters(const Vec3& a, const Vec3& b, double limit) const {
    double x = a[0], y = a[1], z = a[2];
    double dx = b[0] - x, dy = b[1] - y, dz = b[2] - z;
    double l = std::sqrt(dx * dx + dy * dy + dz * dz);
    double sum = 0.0;
    walk_cells_t(x, y, b[0], b[1], [&](int c, double c0, double c1) -> double {
        for (int32_t ti : geo.grid_t[c]) {
            auto [t0, t1, ok] = ray_crown(geo.trees[ti], x, y, z, dx, dy, dz);
            if (ok) {
                t0 = std::max(t0, c0);
                t1 = std::min(t1, c1);
                if (t1 > t0) sum += (t1 - t0) * l;
            }
        }
        if (sum > limit) return -1.0;
        return 1.0;
    });
    return sum;
}

bool World::line_of_sight(const Vec3& a, const Vec3& b) const {
    if (any_hit(a, b, true)) return false;
    double lim = -std::log(geo.rules.canopy_block_t) / geo.rules.canopy_density;
    return crown_meters(a, b, lim) <= lim;
}

bool World::shot_clear(const Vec3& a, const Vec3& b) const {
    return !any_hit(a, b, false);
}

bool World::any_hit(const Vec3& a, const Vec3& b, bool trunks) const {
    double x = a[0], y = a[1], z = a[2];
    double dx = b[0] - x, dy = b[1] - y, dz = b[2] - z;

    std::vector<int32_t> seen_p, seen_t;
    seen_p.reserve(64);
    seen_t.reserve(64);
    bool hit = false;

    auto has = [](const std::vector<int32_t>& s, int32_t v) -> bool {
        return std::find(s.begin(), s.end(), v) != s.end();
    };

    walk_cells(x, y, b[0], b[1], [&](int c) -> double {
        for (int32_t pi : geo.grid_p[c]) {
            if (has(seen_p, pi)) continue;
            seen_p.push_back(pi);
            auto [_, ok] = ray_prism(static_cast<int>(pi), x, y, z, dx, dy, dz, 1.0);
            if (ok) {
                hit = true;
                return -1.0;
            }
        }
        if (trunks) {
            for (int32_t ti : geo.grid_t[c]) {
                if (has(seen_t, ti)) continue;
                seen_t.push_back(ti);
                const auto& tr = geo.trees[ti];
                auto [_, ok] = ray_trunk(tr.x, tr.y, tr.trunk_r, tr.z - 1.0, tr.trunk_top, x, y, z, dx, dy, dz, 1.0);
                if (ok) {
                    hit = true;
                    return -1.0;
                }
            }
        }
        return 1.0;
    });

    if (hit) return true;
    auto [_, ok] = ray_terrain(x, y, z, b[0], b[1], b[2], 1.0);
    return ok;
}

int World::in_canopy(double x, double y, double z) const {
    int c = cell_of(x, y);
    if (c < 0) return -1;
    for (int32_t ti : geo.grid_t[c]) {
        const auto& t = geo.trees[ti];
        double a = (x - t.cx) / t.crown_r;
        double b = (y - t.cy) / t.crown_r;
        double d = (z - t.cz) / t.rz;
        if (a * a + b * b + d * d <= 1.0) return static_cast<int>(ti);
    }
    return -1;
}

double World::support_at(double x, double y, double feet_z, double r) const {
    double z0 = surface_at(x, y, feet_z + STEP_UP);
    double z = z0;
    double lim = feet_z + 0.05;
    double re = r + 0.02;
    for_cells(x - re, y - re, x + re, y + re, [&](int c) {
        for (int32_t pi : geo.grid_p[c]) {
            const auto& p = geo.prisms[pi];
            if (p.top <= z || p.top > lim || p.top <= z0 + STEP_UP ||
                x + re < p.min_x || x - re > p.max_x || y + re < p.min_y || y - re > p.max_y) {
                continue;
            }
            double cx, cy;
            double d = closest_on_edges(p.edges, x, y, cx, cy);
            if (d <= re || point_in_poly(p.edges, x, y)) {
                z = p.top;
            }
        }
    });
    return z;
}

} // namespace mech
