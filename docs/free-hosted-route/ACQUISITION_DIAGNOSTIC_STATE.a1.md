# Actual free-hosted acquisition frontier

DIAGNOSTIC, 2026-10-09. Actual run 37981972232 passed RAM/GPG preflight at
19:41:52 UTC. All 88 original Git HEAD/tree checks finished by 19:43:48 UTC;
no tool-download marker followed. At 19:43:55 UTC the source materialization/
verification stage raised ValueError, whose generic report hid the exact check.
This is source-acquisition failure, not GN, target compilation or a ready image.

FACT: independent audit of the locally retained exact original/provider pins
found matching Git executable bits, symlink kinds and owners for all 144,407
source rows. No executable-mode change or dependency/target suppression follows
from the available evidence. The first failing byte/link/member remains unknown.

`diagnostics.py` and the narrow acquire/free-run changes now report fixed codes
for byte/size/mode/link/owner/Git-executable checks, plus the canonical declared
source member. Root-controlled source function/line identity is bounded; arbitrary
exception text, subprocess stderr, URLs, query strings and token-looking values
are not published. Non-source ValueErrors receive an exact whitelist code or
UNCLASSIFIED_VALUE_ERROR. Source materialization has explicit begin/pass markers.
All acceptance guards and original SourceLock/GNI/tool/SDK/Forge bindings remain
unchanged. This patch adds evidence; it does not claim the cause is fixed.

Focused verification: three actual controls passed for member/hash mismatch,
untrusted-text/path suppression and fixed non-source classification. Python AST
and diff-check passed. `DIAGNOSTIC_VERIFICATION.a1.json` freezes these exact changed
bytes. Earlier SOURCE_VERIFICATION.json is the immutable historical pre-run
source freeze; this diagnostic receipt supersedes only its changed-file hashes.

Expected next marker: a reviewed diagnostic successor identifies the exact
source member and fixed rejection code, allowing a source-backed correction.
Rollback condition: any raw stderr/URL/token exposure or weaker source acceptance
rejects the patch. No new run, commit, push or artifact upload was performed by
this agent; root owns review/publication.
