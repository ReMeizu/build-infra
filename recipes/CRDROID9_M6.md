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
