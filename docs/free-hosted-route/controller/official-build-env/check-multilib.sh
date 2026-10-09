#!/usr/bin/env bash
# Execute inside a Forge recipe; all generated files stay in its scratch TMPDIR.
set -Eeuo pipefail
trap 'printf "Forge Android 9 multilib check failed at line %s\n" "$LINENO" >&2' ERR

: "${TMPDIR:?Run this check through Forge with an explicit scratch TMPDIR}"
test -d "$TMPDIR"
probe_dir=$(mktemp -d "$TMPDIR/forge-android9-multilib.XXXXXXXX")
printf 'Forge Android 9 multilib scratch: %s\n' "$probe_dir"

cat > "$probe_dir/host32.c" <<'EOF'
#include <stdio.h>
#include <zlib.h>
#include <curses.h>
#undef curses_version
int main(void) {
    printf("C host pointer bits=%zu zlib=%s ncurses=%s\n",
           sizeof(void *) * 8, zlibVersion(), curses_version());
    return sizeof(void *) == 4 ? 0 : 1;
}
EOF

cat > "$probe_dir/host32.cpp" <<'EOF'
#include <iostream>
#include <string>
#include <zlib.h>
#include <curses.h>
#undef curses_version
int main() {
    const std::string version(zlibVersion());
    std::cout << "C++ host pointer bits=" << sizeof(void *) * 8
              << " zlib=" << version << " ncurses=" << curses_version() << '\n';
    return sizeof(void *) == 4 ? 0 : 1;
}
EOF

gcc -m32 "$probe_dir/host32.c" -o "$probe_dir/host32-c" -lz -lncurses
g++ -m32 "$probe_dir/host32.cpp" -o "$probe_dir/host32-cpp" -lz -lncurses
"$probe_dir/host32-c"
"$probe_dir/host32-cpp"
file "$probe_dir/host32-c" "$probe_dir/host32-cpp"
sha256sum "$probe_dir/host32-c" "$probe_dir/host32-cpp"
printf 'FORGE_ANDROID9_MULTILIB_OK\n'
