#!/usr/bin/env bash
set -euo pipefail
: "${TMPDIR:?Forge scratch required}"
probe=$(mktemp -d "$TMPDIR/multilib.XXXXXXXX")
printf '#include <stdio.h>\n#include <zlib.h>\nint main(){puts(zlibVersion());return sizeof(void*)!=4;}\n' > "$probe/check.c"
gcc -m32 "$probe/check.c" -o "$probe/check" -lz
"$probe/check"
printf '#include <iostream>\nint main(){std::cout<<sizeof(void*);return sizeof(void*)!=4;}\n' > "$probe/check.cpp"
g++ -m32 "$probe/check.cpp" -o "$probe/check-cpp"
"$probe/check-cpp"
echo FORGE_ANDROID9_MULTILIB_OK
