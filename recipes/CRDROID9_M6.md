# crDroid Pie source preparation for M6

Upstream manifest: crdroidandroid/android branch 9.0, pinned to
`b6d768250babf86854c5b0ff61547b111f05e48e` (Android 9 / crDroid 5 generation).
Official instructions: https://github.com/crdroidandroid/android/tree/9.0

This job downloads the public platform, M6 LOS16 device configuration and M6
kernel source. Source checkout is shallow, Linux only. It stops syncing after
30 minutes or below 35 GiB free, then saves partial progress to a one-day cache.
Rerunning this branch restores the most recent cache for the same local manifest.
The final step fails visibly if source synchronization did not finish.
No device/vendor sources are published as artifacts; artifacts contain status,
public-source fetch logs and, on success, resolved revisions only.

VM: CircleCI Free large, verified 4 CPUs / ~15 GiB RAM / ~135 GiB free ext4.
One job may run at most one hour. This is source preparation, not a completed ROM.
Cache storage uses included credits; no paid plan or payment method is added.

`repo-launcher` is the official Google git-repo launcher downloaded from
https://storage.googleapis.com/git-repo-downloads/repo . SHA-256:
`1211b57b57e4122a9c546295a59b37d24068f1164d0e87bef096d5323c413e4f`.
Git LFS downloads are deferred and must be hydrated and verified before building.

The published M6 product is `lineage_meizu_m6-userdebug` at
`device/meizu/meizu_m6`. The kernel repository contains `kernel-3.18` at its root.
The common device tree, matching LOS16 vendor/MTK inputs and prebuilt kernel
still need to be selected. The published vendor repository has no LOS16 branch;
do not silently substitute its Oreo branch. crDroid uses `vendor/lineage`, but
the M6 product hardcodes Lineage version strings and packages such as Trebuchet;
review those against the actual crDroid product definitions before graph/build.

## M6 ROM trial

`export_m6_private.py` freezes the matching M6 common trees, MediaTek sources,
vendor snapshot and prebuilt kernel on n8n. Its archive and file hashes remain
private. Stale stock app-JNI symlinks are materialized from the corresponding
libraries already present in that vendor snapshot; the active LOS16 tree is untouched.

After the public source-cache upload finishes, `crdroid9_prepare.py` verifies the
private archive, hydrates Git LFS, and adapts the isolated M6 product. PROPER-FIX:
remove the hardcoded LOS16 version so crDroid's common product controls branding;
select Launcher3QuickStep, the actual module in crDroidHome's pinned Android.mk.
No hardware feature is disabled by this adaptation. Roll back the overlay if the
product reports a different device, Android version, or launcher module.

`crdroid9_launch.py` uses the preserved Forge launcher, an immutable Android 9
container image, non-root execution, offline compilation, read-only sources and
a separate 60 GiB ext4 scratch filesystem. One trial runs for at most 20 minutes
of container time; all scratch output and evidence are then archived for private
retrieval to n8n. A timeout is not ROM success. Acceptance requires the Forge
SUCCESS marker, boot.img, ROM ZIP and matching SHA256SUMS. Checkpoint reuse must
also verify source/image/recipe identity before another invocation.

Bootstrap commands are not part of the source-download workflow. Do not add
private inputs to its public cache or public artifacts. Runtime graph acceptance
and the first ROM compilation remain pending until recorded in the progress file.
