# ReMeizu build infrastructure

CI for kernel development, Android ROM workers and public OpenHarmony native
intermediate builds for older Meizu phones. Builds use bounded execution and
the Forge Docker launcher.

## Run a job

Open the [workflow](https://github.com/ReMeizu/build-infra/actions/workflows/blacksmith.yml),
choose **Run workflow**, and select a mode:

| Mode | Workload | Runner | Job limit | Reserved minutes |
|---|---|---|---|---|
| `probe` | CPU, memory, disk, Docker and public endpoint checks | 2 vCPU | 5 minutes | 8 |
| `kernel` | [M5s Yassy panel object](recipes/M5S_YASSY_OBJECT.md) | 16 vCPU | 60 minutes | 504 |
| `rom` | [Private-input ROM worker](recipes/ROM_WORKER.md) | 16 vCPU | 240 minutes | 1,944 |
| `rom-90` | [Private-input ROM worker](recipes/ROM_WORKER.md), 75-minute session | 16 vCPU | 90 minutes | 744 |
| `component` | Complete pinned board kernel (3.18 or 4.9) | Standard GitHub Ubuntu | 90 minutes | No Blacksmith reservation |

The component job uses a standard GitHub-hosted runner in this public repository.
It keeps the source commit/tree, compiler hashes, actual generated configuration,
compiled board DTB, linked kernel, selected driver objects and Forge receipts.
Compilation runs without network access, under an unprivileged UID, with bounded
CPU, memory and time. This job produces a kernel, not a ROM or a flashable boot
image; hardware testing remains a separate step. Its outputs expire after three
days. Only reviewed public source profiles are accepted. Select `component_profile`
for a device (`m5c-cpu-stats`, `mx6-sync-fence`, `m5s-native`, `m2note-native`,
`u20-native`, `u10-native`); distinct profiles can run concurrently, while each profile serializes
its own requests. Every profile binds its own configuration, DTB and driver objects.
A shared BSP directory name does not identify the physical chipset.
The component scratch volume is 12 GiB, with at least 2 GiB of host disk headroom;
it uses a new file on the disposable runner and leaves existing storage untouched.

The Blacksmith workflow has no automatic triggers. Its jobs run sequentially;
GitHub may replace an older pending request with a newer queued request. Use a new dispatch to retry:
workflow reruns are rejected before runner allocation. Logs and artifacts are
kept for seven days, including failed jobs. ROM mode uploads only worker metadata;
the operator retrieves ROMs and private build logs over SSH before releasing it.

## Public OpenHarmony native intermediate

The [public native route](docs/free-hosted-route/RESOURCE_AND_SOURCE_PLAN.md)
uses a standard GitHub runner, anonymous pinned public sources, two compiler
jobs and RAM build outputs. Its push trigger accepts only
`codex/free-native-20261009`; the first reviewed run uses 88 source projects and
72 selected parts. The current reviewed successor has 101 projects /85 parts,
adding the genuinely required database/framework providers while preserving all
prior source, feature and SDK bindings. See the
[measured cohort](docs/free-hosted-route/MEASURED_COHORT_GUARD_STATE.a1.md).
The job allows 330 minutes including bounded acquisition,
compilation and encrypted Release retention. It has no Blacksmith reservation.

This is an intermediate build. The full 375-component GUI phone profile,
complete flashable image and hardware runtime remain unverified. Only explicit
public native output and separately admitted setup-failure evidence are retained
as ciphertext; private Android inputs are excluded. See the linked plan for actual source tests and acceptance gates.

## Budget limits

The standard GitHub runner reserves each job's full timeout plus three minutes
before allocating Blacksmith compute. Reservations use normalized 2-vCPU minutes
and are not refunded for shorter, failed or cancelled jobs.

[Policy](config/blacksmith-policy.json) limits reservations to **9,000 minutes per
UTC month and 18,000 total**, below the confirmed 10,000-minute monthly allowance.
The `blacksmith-budget` branch stores `ledger.json`; updates require its current
file SHA. Missing, malformed or conflicting state rejects the job. Reservations
that could cross a month boundary are also rejected. Only the budget job has
repository write permission.

This guards this repository's workflow, not provider billing or jobs launched
elsewhere. Changing either cap requires a policy change. Runner sizing follows
the [Blacksmith documentation](https://docs.blacksmith.sh/blacksmith-runners/overview).

## Build environment

Kernel jobs create an exclusive 8-GiB sparse file in the runner's temporary
directory and mount it as a separate ext4 scratch filesystem. Existing files
and devices are never formatted; provider persistent storage is not used.
ROM workers use a separate 600-GiB file on the same ephemeral runner storage.

The kernel recipe builds a container image and records its immutable identity.
Forge compilation runs without network access, as a non-root user, against
read-only inputs. The orchestration deadline is 50 minutes with 90 seconds for
cleanup; the object build uses two jobs and a 600-second Forge limit.

[Project build status](https://github.com/nomorecoolnicknames/remeizu/blob/main/BUILD_INFRASTRUCTURE.md)
records the successful probe and kernel-object run. An object build does not
establish a working boot image or device support.
