# Declared LFS materialization postcondition

PROPER-FIX: actual run 37983424862 rejected ICU
`third_party/icu/tools/multi/proj/icu4cscan/old-xmls.tar.bz2` with
SOURCE_BYTES_MISMATCH before tools/GN/compilation. Original HEAD
`e7dc850c25fc69109275ee2f80f6e68c05c6dd47` contains a 129-byte LFS pointer,
SHA256 `eb234fb843bcef80721a89b5711ac1b753da2f332b8fffa9ee6339eefc0de8c1`.
The unchanged lock/inventory requires its actual 9,713-byte object, SHA256
`215e9cc66b7962f53a08db564558553366f06f64eb6d8508a3ff2dac47c90cb6`.

FACT: local fresh ordinary Git-LFS fetch/checkout can materialize this member
correctly despite its pinned text:auto attribute. The attributes-only explanation
is REJECTED; the precise CI-version/environment cause remains unproven. We do
not lower hashes, alter attributes or claim generic checkout always fails.

The new materializer checks the three existing declared objects only (ICU1,
ACE2; each <=8 MiB). HEAD blob SHA, strict pointer OID/size, original remote
and HEAD/tree must match the lock. Correct actual material is left unchanged.
Only an exact committed pointer can be replaced: explicit existing git-lfs
smudge receives that pointer, canonical original endpoint and empty credential
helper; GIT_LFS_SKIP_SMUDGE is removed only in the child environment. Unknown
working bytes are rejected with safe actual SHA/size. No signed URL or stderr
is printed. Original SHA/size/mode checks still run before source copying.

Fresh source-only reproduction verified the exact ICU pointer-to-object path
and a second exact-material no-op, with unchanged parent environment/HEAD/tree.
`LFS_MATERIALIZER_REPRO.a1.json` records this evidence; no target compilation
occurred. Four focused controls passed for pointer/OID/size tampering, declared
capture bounds, safe mismatch fields and real descendant timeout cancellation.
Popen has its own session; timeout kills that owned process group and uses a
bounded final communicate. No custom stream/timer framework was added.

Expected next marker: actual cloud acquisition reports the exact declared LFS
materialization, then continues unchanged source verification. Rollback: any
undeclared object, pointer/origin/HEAD/tree drift, material mismatch, unknown
working bytes or unsafe diagnostic exposure rejects the change. No source pin,
SDK, dependency, official Forge, acceptance guard or full375 boundary changed.
Root owns commit/push and the next real diagnostic/build run.
