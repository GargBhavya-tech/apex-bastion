#include "types.hpp"
#include "world.hpp"
#include "brain.hpp"

#include <iostream>
#include <string>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <queue>
#include <vector>

class LineQueue {
public:
    void push(std::string line) {
        std::unique_lock<std::mutex> lock(mutex_);
        queue_.push(std::move(line));
        cond_.notify_one();
    }

    void close() {
        std::unique_lock<std::mutex> lock(mutex_);
        closed_ = true;
        cond_.notify_all();
    }

    bool pop_batch(std::vector<std::string>& batch) {
        std::unique_lock<std::mutex> lock(mutex_);
        cond_.wait(lock, [this]() { return !queue_.empty() || closed_; });
        if (queue_.empty() && closed_) return false;
        while (!queue_.empty()) {
            batch.push_back(std::move(queue_.front()));
            queue_.pop();
        }
        return true;
    }

private:
    std::mutex mutex_;
    std::condition_variable cond_;
    std::queue<std::string> queue_;
    bool closed_ = false;
};

int main() {
    std::ios_base::sync_with_stdio(false);
    std::cin.tie(nullptr);

    LineQueue lq;
    std::thread reader([&lq]() {
        std::string line;
        while (std::getline(std::cin, line)) {
            if (!line.empty()) {
                lq.push(std::move(line));
            }
        }
        lq.close();
    });

    auto send = [](const mech::json& j) {
        std::cout << j.dump() << "\n" << std::flush;
    };

    std::unique_ptr<mech::Brain> brain;
    std::vector<std::string> batch;

    while (lq.pop_batch(batch)) {
        std::string latest_obs_raw;

        for (const auto& raw : batch) {
            mech::json probe;
            try {
                probe = mech::json::parse(raw);
            } catch (...) {
                continue;
            }

            std::string type = probe.value("type", "");
            if (type == "hello") {
                mech::Hello h;
                try {
                    h = probe.get<mech::Hello>();
                } catch (const std::exception& e) {
                    std::cerr << "hello error: " << e.what() << "\n";
                }
                std::string dir = h.map.dir;
                auto w = mech::World::load(dir);
                if (!w && dir != "/arena") {
                    w = mech::World::load("/arena");
                }
                if (!w) {
                    std::cerr << "map load failed, playing on flat map\n";
                    w = mech::World::flat();
                }
                brain = std::make_unique<mech::Brain>(h, w);
                send(mech::json{{"type", "ready"}, {"name", "apex-bastion"}});
            } else if (type == "obs") {
                latest_obs_raw = raw;
            } else if (type == "end") {
                if (reader.joinable()) reader.detach();
                return 0;
            }
        }
        batch.clear();

        if (latest_obs_raw.empty()) continue;

        try {
            mech::json obs_json = mech::json::parse(latest_obs_raw);
            if (!brain) {
                int tick = obs_json.value("tick", 0);
                send(mech::json{{"tick", tick}});
                continue;
            }
            mech::Obs o = obs_json.get<mech::Obs>();
            mech::Action act = brain->act(&o);
            mech::json act_json = act;
            send(act_json);
        } catch (...) {
            try {
                mech::json t_json = mech::json::parse(latest_obs_raw);
                int tick = t_json.value("tick", 0);
                send(mech::json{{"tick", tick}});
            } catch (...) {
                // ignore
            }
        }
    }

    if (reader.joinable()) reader.join();
    return 0;
}
