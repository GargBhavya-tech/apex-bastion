# Apex Bastion (C++ Edition)

Autonomous combat bot engineered for the Builders Buildathon **Mech Royale** (`mechfight/1`) track.
Re-architected in modern standard C++20 with static linking, zero GC overhead, and sub-5ms decision latency.

## Architecture Highlights
- **Deterministic Sub-5ms Decision Latency**: Zero garbage collection pauses or runtime interpreter spikes. Guarantees safe responses well under the 50 ms tick budget on 1 vCPU.
- **3D Spatial & Geometry Engine**: 3D raymarching across 259 building prisms, tree canopies, and terrain elevation grids (`terrain.i16`).
- **Dynamic NavGrid & A* Pathfinding**: Real-time clearance distance transforms, connected component tracking, and smooth path following.
- **Closed-Form Ballistic Fire Control**: Quadratic lead solver for the Arm Gun and parabolic arc solver for Mortar trajectories.
- **Lethal Laser Release & Fire Control**: Predictive charge evaluation and lethal threshold releases.
- **Tactical Utility & Evasion**: Adaptive ring-based combat kiting, BFS multi-threat cover finding, and projectile/beam dodging.

## Building and Running
To build the static scratch container:
```sh
docker build --platform linux/amd64 -t bot .
```
