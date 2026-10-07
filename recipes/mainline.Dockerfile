ARG BASE_IMAGE
FROM ${BASE_IMAGE}
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 make gcc-13 g++-13 gcc-13-aarch64-linux-gnu binutils-aarch64-linux-gnu \
    clang-18 lld-18 llvm-18 flex bison bc libssl-dev libelf-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*
