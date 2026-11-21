# Apex Bastion (C++)

A bot for the Builders Buildathon **Mech Royale** track (`mechfight/1` protocol): 16 mechs, one zone,
last mech standing. Score = mean of (16 - place) over 48 practice matches.

This branch (`cpp-bot`) is a C++20 port of the Go bot on `main`, which scored **6.19** on the practice
board (commit `f71b902`). It builds to one static binary in a `scratch` image (about 5 MB).

## Layout

| Path | What it does |
| --- | --- |
| `src/main.cpp` | stdin/stdout loop. A reader thread queues lines, and the main loop answers only the newest observation (the protocol's newest-observation rule). Bad lines are skipped. If anything throws, it still answers the tick with an empty action. |
| `src/world.cpp`, `src/world.hpp` | Map model from `/arena` (`world.json` buildings and trees, `terrain.i16` heights), line of sight, nav grid and A* pathfinding. Falls back to a flat map if `/arena` can't be read. |
| `src/brain.cpp`, `src/brain.hpp` | Decisions: enemy tracking, target odds, preferred range per weapon, cover and hiding, shell dodging, zone deadline, pickups and upgrades, aiming and firing. |
| `src/types.hpp` | Protocol message types and JSON conversion. |
| `src/json.hpp` | nlohmann/json, single header (MIT). |

## Build and check

```sh
docker build --platform linux/amd64 -t apex-cpp .
```

Run the kit's conformance check exactly the way the scorer starts the bot (from the unpacked `mechfight-kit/`):

```sh
python3 check/check.py --map-dir /arena -- docker run --rm -i --network none --cpus 1 --memory 512m \
  --read-only --tmpfs /tmp:rw,size=64m --user 65534:65534 -v "$PWD/arena:/arena:ro" apex-cpp
```

Last result (2026-11-22): **PASS**, 300/300 observations answered in time, p50 about 1.6 ms, max 10 ms
(budget 50 ms).

To build locally without Docker: `make` (needs g++ with C++20).

## Runtime limits it is built for

1 CPU, 512 MB, no network, read-only filesystem except `/tmp` (64 MB), uid 65534, map at `/arena`.
The bot writes no files. The build image is pinned by digest, because finalists are rebuilt.

## Changelog

- **2026-11-22:** fixed a crash in the A* priority queue. `World::pop_heap` read past the end of the heap when it
  popped the last item, which crashed the bot (SIGSEGV) on its first move order, so `check.py` failed.
  Pinned the `gcc` base image by digest.
- **6e98ee5:** C++20 port of the 6.19 Go bot.

## Submitting a specific commit

The track page scores the newest commit on the **default branch** (`main`) unless you paste a commit hash
into the *Commit* field. To score this branch, paste its commit hash there.
