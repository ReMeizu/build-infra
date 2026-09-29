# ReMeizu build infrastructure

Manual CI for kernel development on older Meizu phones. Jobs use pinned public
inputs, bounded execution and the Forge Docker launcher.

## Run a job

Open the [workflow](https://github.com/ReMeizu/build-infra/actions/workflows/blacksmith.yml),
choose **Run workflow**, and select a mode:

| Mode | Workload | Runner | Job limit | Reserved minutes |
|---|---|---|---|---|
| `probe` | CPU, memory, disk, Docker and public endpoint checks | 2 vCPU | 5 minutes | 8 |
| `kernel` | [M5s Yassy panel object](recipes/M5S_YASSY_OBJECT.md) | 16 vCPU | 60 minutes | 504 |

There are no automatic triggers. Jobs run sequentially; GitHub may replace an
older pending request with a newer queued request. Use a new dispatch to retry:
workflow reruns are rejected before runner allocation. Logs and artifacts are
kept for seven days, including failed jobs. Full Android ROM builds are not enabled.

## Budget limits

The standard GitHub runner reserves each job's full timeout plus three minutes
before allocating Blacksmith compute. Reservations use normalized 2-vCPU minutes
and are not refunded for shorter, failed or cancelled jobs.

[Policy](config/blacksmith-policy.json) limits reservations to **9,000 minutes per
UTC month and 9,000 total**, below the confirmed 10,000-minute monthly allowance.
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

The kernel recipe builds a container image and records its immutable identity.
Forge compilation runs without network access, as a non-root user, against
read-only inputs. The orchestration deadline is 50 minutes with 90 seconds for
cleanup; the object build uses two jobs and a 600-second Forge limit.

[Project build status](https://github.com/nomorecoolnicknames/remeizu/blob/docs/project-status/BUILD_INFRASTRUCTURE.md)
records the successful probe and kernel-object run. An object build does not
establish a working boot image or device support.
