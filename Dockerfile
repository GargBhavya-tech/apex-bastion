FROM gcc:14-bookworm AS build
WORKDIR /src
COPY src /src
RUN g++ -O3 -std=c++20 -static -pthread -Wall -Wextra -I/src -o /mechbot /src/main.cpp /src/world.cpp /src/brain.cpp

FROM scratch
ENV HOME=/tmp TMPDIR=/tmp
COPY --from=build /mechbot /mechbot
ENTRYPOINT ["/mechbot"]
