ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential bc bison flex git ca-certificates python3 file binutils \
    libncurses5 libncurses5-dev libssl-dev zlib1g-dev device-tree-compiler \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
CMD ["bash"]
