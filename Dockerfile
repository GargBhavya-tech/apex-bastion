# Pinned by digest: finalists are rebuilt, so the compiler must not drift.
FROM gcc:14-bookworm@sha256:5e927c284bf55a7dc796262e311a0703344f62f41f5621eb56843111b1d37e15 AS build
WORKDIR /src
COPY src /src
RUN g++ -O3 -std=c++20 -static -pthread -Wall -Wextra -I/src -o /mechbot /src/main.cpp /src/world.cpp /src/brain.cpp

FROM scratch
ENV HOME=/tmp TMPDIR=/tmp
COPY --from=build /mechbot /mechbot
ENTRYPOINT ["/mechbot"]
