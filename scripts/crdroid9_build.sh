#!/usr/bin/env bash
# PROPER-FIX: run crDroid's own product/version and bacon target on the M6 tree.
set -eo pipefail
cd /workspace/src
export BUILD_DATETIME=1790700000
export TZ=UTC
export USE_CCACHE=1 CCACHE_MAXSIZE=6G
export JAVA_TOOL_OPTIONS=-Xmx6g
forge-check-multilib
source build/envsetup.sh
lunch lineage_meizu_m6-userdebug
test "$(get_build_var PLATFORM_VERSION)" = 9
test "$(get_build_var TARGET_DEVICE)" = meizu_m6
test "$(get_build_var TARGET_BUILD_VARIANT)" = userdebug
get_build_var LINEAGE_VERSION | tee /workspace/out/rom-version.txt
grep -q crDroid /workspace/out/rom-version.txt
printf 'CRDROID_M6_COMPILATION_START\n'
m -j4 bacon
product="$OUT_DIR/target/product/meizu_m6"
test -s "$product/boot.img"
cp "$product/boot.img" /workspace/out/boot.img
mapfile -t roms < <(find "$product" -maxdepth 1 -name 'crDroidAndroid-*.zip')
test "${#roms[@]}" = 1
cp "${roms[0]}" /workspace/out/rom.zip
cd /workspace/out
sha256sum boot.img rom.zip > SHA256SUMS
