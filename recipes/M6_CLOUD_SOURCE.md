# M6 public source preparation

This branch prepares the 701 exact Android 9 public revisions on CircleCI. The
workflow has a manual approval and is restricted to `m6-circle-cloud-only`.
It does not compile Android. The source controller also rejects execution outside
the admitted CircleCI organization/project/branch.

The resolved manifest SHA256 is
`5d415160af39512a9d708def634244cb9707a90704880d4f176aa7c92eb7baa1`.
The controller always syncs these revisions, verifies the actual project list and
HEADs, then hydrates and verifies public LFS. It stops preparation 35 minutes
after the first checkout step, retaining the remaining Free job time for cache
storage and evidence. The filesystem reserve is 35 GiB.

Only public Git sources enter the new cache namespace. Private hydration,
source corrections, output, Ninja state and acceptance proofs are excluded.
Foreign root paths, extra manifests, changed manifest links/copies and dirty
project worktrees reject caching. Partial public downloads can be cached, but
the final job check fails until all 701 revisions and LFS are verified.

The nine retained public corrections are included as immutable raw input files
for the later full build. `m6_cache_policy.py` adds a separately verified policy
correction to the exact pinned `ccache.mk`: preprocessing checks, compiler byte
hashes and empty sloppiness. Its Linux test verifies effective Make exports
against conflicting inherited and command line settings. The original Forge
is unchanged. No old output checkpoint, container image or private compiler
cache is published by this workflow.

Before approving a source job, inspect current cloud account balance and active
jobs. Full compilation still requires a fresh cloud capacity admission, exact
private inputs/image, source proof, an empty output directory on a distinct
ext4 filesystem, and an evidence-based ART correction. Source-job success is
not ROM acceptance.
