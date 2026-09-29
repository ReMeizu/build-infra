# A new kernel-only environment; never claim identity with the accepted A4 image.
# kernel_run.py resolves ubuntu:20.04 to an immutable repository digest first.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential bc bison flex git ca-certificates python3 file binutils \
    libncurses5 libncurses5-dev libssl-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
CMD ["bash"]
