# crDroid Android 9 for Meizu M6

The source cache contains 701 repositories from crDroid branch 9.0, manifest
b6d768250babf86854c5b0ff61547b111f05e48e. The M6 LOS16 device and kernel
revisions are pinned in inputs/crdroid9-m6.xml. Common device trees, matching
MediaTek/vendor inputs and the prebuilt kernel come from a verified private snapshot.

The current workflow requires manual approval, then restores the public source
cache and Android 9 container. n8n supplies an expiring download URL and a private
checkpoint encryption key through the existing authorized SSH identity.
No private inputs or keys enter public caches. All published build outputs are
AES-256-GCM encrypted; status.json contains only completion and integrity data.

The isolated product inherits crDroid branding and Launcher3QuickStep. Only
kernel-3.18 is exported from the kernel repository because its other directories
contain an unrelated Android BSP whose CleanSpec.mk is incompatible with Pie.
The complete pinned BSP is retained outside the build source tree.

Compilation runs through the preserved Forge launcher with immutable image ID,
non-root user, read-only sources, network disabled and separate 50 GiB ext4 scratch.
Git optional index refresh is disabled while source identity is checked.
A trial has at most 30 minutes of container time and reserves time for encrypted
checkpoint upload before CircleCI Free's one-hour job limit. A timeout or partial
compile is a failure. Completion requires boot.img, the crDroid ROM ZIP, hashes
and successful Forge validation. Hardware acceptance is a separate step.

Encrypted checkpoints retain logs, scratch output and source identity for diagnosis.
Warm continuation must verify source and image identity before reusing compiler output.
Cache storage uses included credits; no payment method or paid plan is added.

## Validated continuation

A later control handoff may supply the previous encrypted Circle artifact URL and
its SHA-256. The workflow authenticates AES-GCM before extracting a checkpoint.
It compares source provenance and the complete build contract (including immutable
image), allowing only timeout and invocation identity to change. Old container
metadata must confirm cleanup. Only compiler output, ccache and build home move
into the new scratch directory; the previous evidence is retained. Contract or
source changes reject continuation. Tests cover image/source mismatches, pending
cleanup and authenticated encryption tampering.

Compact live diagnostics are encrypted with the same private key before entering
CircleCI console output. Private logs are never printed in plaintext publicly.

## Source proof scheduling

Independent Git project snapshots may run concurrently inside each of the two
original Forge proof passes. The preserved algorithm still hashes and encodes
all paths in the same order, with identical source identities and original dirty
submodule/index checks. Results are never reused between passes. Tests compare
serial and parallel identities, including dirty tracked files, ignored payloads,
symlinks and rejected assume-unchanged index entries. This changes scheduling,
not the set of checked inputs. The vendored Forge file remains unchanged.
All project readers finish before root metadata traversal, so temporary Git/LFS
lock files cannot disappear between its inventory and hashing. The transient
lock regression and exact serial/parallel identity tests cover this ordering.
