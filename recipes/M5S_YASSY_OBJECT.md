# First public kernel workload: M5s own Yassy panel object

Validated on Blacksmith in [run36553547835](https://github.com/ReMeizu/build-infra/actions/runs/36553547835): seven outputs rehashed; object and config match accepted A4 byte-for-byte. See [compact proof](../evidence/20260929-m5s-yassy.json). Invoke only after the workflow's budget admission:

```sh
sudo -n python3 -B scripts/kernel_run.py \
  --scratch-mount /mnt/forge \
  --receipt-dir "$RUNNER_TEMP/kernel-receipts"
```

The caller must supply a **distinct mounted ext4/xfs device**, not merely a directory or bind mount on the root filesystem. At least6GiB free is required. The script neither provisions/formats a disk nor erases earlier jobs. Root controls CI invocation and artifact retention. Upload the supplied receipt directory on success **and failure**.

## Inputs and small build target

- Public kernel: `https://github.com/nomorecoolnicknames/mtk-t-alps-release-q0-kernel-4.9-lc.git`, commit `e2a0b2e51b87ce7aca65775d92c9269df8f27201` (public A4 source; anonymous API200 verified29Sept2026).
- Public compiler: `https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9`, commit `7a28c220c2e9001825328dca6188ef0077a80a88`, tree `08369a4d09f1de92d6e5d35b5ecb33b94f735668`. Official Git refs were reachable during preparation; Gitiles JSON/archive returned503. Fetch uses exact Git SHA, bounded600seconds; failures stop without a replacement compiler.
- Compiler wrapper's only delta is the already accepted shebang `/usr/bin/python` → `/usr/bin/env python3`. Resulting wrapper, real compiler and linker must match pinned SHA256 values in `m5s-yassy-inputs.json`.
- `m5s_yassy_defconfig`, then only `drivers/misc/mediatek/lcm/ili9881_CA_hd720_dsi_vdo_yassy/ili9881_CA_hd720_dsi_vdo_yassy.o`, -j2. The new Forge container has600seconds total; defconfig90seconds and object command420seconds. Source download and image preparation precede Forge and are bounded separately; the workflow enforces its overall budget/timeout.

A direct leaf Kbuild target omits inherited parent `subdir-ccflags`. `KCFLAGS` explicitly carries the include directories and `-Werror` observed in the accepted A4 object's actual command. There is no kernel/config patch. The generated `.config` must equal accepted A4 SHA256 `f9b7eb86f827e3ef04a72c9d74f16cf142acb2454b8326b1e93f6e9dc808de73`.

The own panel driver has a GPL-2.0 SPDX notice and preserves source provenance. This workload imports **public source and public compiler inputs only**, adds no private stock image, modem firmware, vendor ROM, credentials or device captures, and compiles only the selected source object plus required Kbuild preparation. The inherited public MediaTek BSP retains its existing per-file notices/material; the whole repository is **not** asserted entirely blob-free or universally eligible for every provider's OSS program. No full BSP/ROM binary is produced or uploaded.

## Existing Forge contract retained

The exact reviewed launcher is vendored unchanged (SHA256 `9a01d1c452ecf14674a9df1f7512176f30b1fe2949660e2ea743960e7d400bb8`). `kernel_forge.py` adds only the explicit `kernel-gcc49` metadata contract; it does not disable source provenance, image pins, non-root mapping, no-network compilation, filesystem checks, leases, artifact hashes, cleanup or SUCCESS gates.

The old accepted image was local-only. This adapter builds a **new** small Ubuntu20.04/GCC9 host-tools image, resolves the base tag to a digest, records that digest, Dockerfile hash and actual immutable image ID, then uses only that ID in Forge. It requires new runner validation; it does not reuse or impersonate the old image digest. No Android/JDK environment is installed or claimed.

Forge emits six required outputs, plus an early diagnostic configuration copy: object, original Kbuild command/dependencies, generated config, build log, compiled-table proof and package versions. SUCCESS+manifest are rehashed again by the caller. Actual ELF64/AArch64 relocatable object and both panel command tables (192+5 rows,72bytes/row) are compared against pinned source; own panel descriptor must exist. Byte equality to historical object `2e5164dc...` is reported, not required on a new image/command environment. Source/config/table gates remain mandatory.

No full kernel, DTB, boot image, flash or runtime acceptance follows from this test. A5r's accepted warm full-link remains separate and requires its preserved private compiled cache; this small public workload deliberately starts without that cache.

Local validation: `python3 -B scripts/kernel_tests.py` plus parsing the accepted A4 object with the new ELF/table checker. No local compilation, CI launch or cloud mutation occurred while preparing this integration.
