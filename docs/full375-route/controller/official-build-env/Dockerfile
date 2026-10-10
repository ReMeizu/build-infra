FROM eclipse-temurin:8-jdk-focal

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    USE_CCACHE=1 \
    CCACHE_DIR=/srv/forge/cache/ccache \
    JACK_SERVER_VM_ARGUMENTS="-Dfile.encoding=UTF-8 -XX:+TieredCompilation -Xmx12g" \
    ANDROID_JACK_VM_ARGS="-Dfile.encoding=UTF-8 -XX:+TieredCompilation -Xmx12g"

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential bc bison flex gperf zip unzip curl wget git-core gnupg     ccache libncurses5 libncurses5-dev libssl-dev libxml2-utils xsltproc     schedtool pngcrush imagemagick lzop rsync cpio kmod file xz-utils     lz4 zstd sudo procps python3 python3-distutils python3-venv \
    python2 python2-minimal python2.7 python-is-python2 \
    gcc-multilib g++-multilib lib32z1-dev lib32ncurses5-dev \
    openjdk-8-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

RUN git config --system --add safe.directory '*' \
    && mkdir -p /srv/forge/cache/ccache /srv/forge/work/tmp \
    && ln -sf /usr/bin/python2.7 /usr/local/bin/python \
    && ln -sf /usr/bin/python3 /usr/local/bin/python3

COPY check-multilib.sh /usr/local/bin/forge-check-multilib
RUN chmod 0755 /usr/local/bin/forge-check-multilib

WORKDIR /srv/forge
CMD ["bash"]
