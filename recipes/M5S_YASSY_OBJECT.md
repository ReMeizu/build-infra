# M5s Yassy panel-object build

This workload builds the M5s panel driver against Linux 4.9 from pinned public
source and compiler inputs. Select `kernel` in the manual workflow. After budget
admission, the workflow invokes:

```sh
sudo -n python3 -B scripts/kernel_run.py \
  --scratch-mount /mnt/forge \
  --receipt-dir "$RUNNER_TEMP/kernel-receipts"
```

The caller must supply a **distinct mounted ext4/xfs filesystem**, with at least
6 GiB free, rather than a directory or bind mount on the root filesystem.
`kernel_run.py` neither provisions storage nor erases earlier jobs. Keep the
receipt directory on both success and failure; the workflow uploads it.

## Inputs

Exact commits, file hashes and expected outputs are in
[m5s-yassy-inputs.json](m5s-yassy-inputs.json). The kernel input remains pinned to
`e2a0b2e51b87ce7aca65775d92c9269df8f27201`; renaming or advancing its public branch
does not change this recipe. The compiler comes from Android's public GCC 4.9
prebuilt repository. Its wrapper uses `/usr/bin/env python3`; wrapper, compiler
and linker hashes are checked before compilation. Fetch failures stop the job.

The target is `m5s_yassy_defconfig`, followed by
`drivers/misc/mediatek/lcm/ili9881_CA_hd720_dsi_vdo_yassy/ili9881_CA_hd720_dsi_vdo_yassy.o`
with two make jobs. The direct leaf target needs explicit parent include paths
and `-Werror` through `KCFLAGS`. No kernel or config patch is applied. The
resulting `.config` must match the pinned expected hash.

Forge has a 600-second limit; defconfig and object commands are bounded at 90
and 420 seconds. Source fetching and container-image preparation have separate
limits inside the workflow's overall deadline.

## Environment and output checks

The [Dockerfile](kernel-gcc49.Dockerfile) supplies Ubuntu 20.04/GCC 9 host tools;
the pinned GCC 4.9 cross-compiler builds the target. Image preparation records the
base digest, Dockerfile hash and immutable image ID. Compilation uses the
[preserved Forge launcher](../vendor/forge/PROVENANCE.md) through a kernel-only
adapter, with read-only source, no network, non-root execution and bounded cleanup.

Required outputs include the object, Kbuild command/dependencies, configuration,
build log, panel-table check and package versions. An early configuration copy
is also retained. The caller rechecks the success marker and artifact manifest.
The ELF must be an AArch64 relocatable object with the expected panel descriptor
and both command tables matching source. Historical byte equality is reported;
source, config and table checks are mandatory.

Run local interface tests with `python3 -B scripts/kernel_tests.py`. Current
[build results](https://github.com/nomorecoolnicknames/remeizu/blob/docs/project-status/BUILD_INFRASTRUCTURE.md)
are recorded with the project documentation.

The inherited BSP keeps its per-file notices; public availability does not change
those licenses. This job imports no private device firmware and produces no full
kernel, DTB, boot image or ROM. Hardware testing remains a separate step.
