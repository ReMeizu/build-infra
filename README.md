# ReMeizu build infrastructure

Manual, bounded CI for keeping older Meizu devices useful. The first Blacksmith
job measures CPU, memory, disk, Docker and access to public build-input endpoints.
A successful probe establishes runner availability; it is not a kernel or ROM build.

## Run the probe

Open [Blacksmith manual pilot](https://github.com/ReMeizu/build-infra/actions/workflows/blacksmith.yml),
choose **Run workflow**, and select `probe`. There are no push, pull-request,
schedule or repository-dispatch triggers. Jobs run sequentially; a new queued
request can replace an older pending request under GitHub's concurrency semantics.
Use a new manual dispatch to retry: re-run attempts are rejected before Blacksmith
runner allocation.

The probe has a five-minute timeout on `blacksmith-2vcpu-ubuntu-2404`.
Its JSON evidence is retained as a GitHub artifact for seven days. It installs no
packages, starts no build and reads no device archive or account credentials.
Runner labels and normalized-minute conversion follow the
[official Blacksmith documentation](https://docs.blacksmith.sh/blacksmith-runners/overview).

## Conservative usage reservations

A separate job on GitHub's standard public-repository runner reserves the full
Blacksmith job timeout plus three minutes before scheduling paid-provider compute.
The probe reserves **8 normalized x64 2-vCPU minutes**. The planned 16-vCPU,
60-minute kernel job reserves **504**. Reservations are never automatically
refunded, including failures, cancellations and shorter successful jobs.

The `blacksmith-budget` branch stores `ledger.json`. Updates use the GitHub
Contents API with the previous file SHA; a conflict or unavailable/malformed
ledger fails closed. The workflow also has one repository-wide concurrency group.
The token with write permission is limited to the budget job; the Blacksmith job
has read-only repository permission.

Support confirmed a 10,000-minute account credit. This repository stops at
**9,000 reserved minutes per UTC month and 9,000 across all recorded months**,
leaving headroom and avoiding an assumption that the coupon renews monthly.
A job whose full reservation could cross a month boundary is refused.
A future allowance change requires explicit verification and policy review.

This is a repository workflow guard, **not a provider-enforced billing cap**.
It does not account for jobs launched outside this controlled repository, changed
workflows or administrator overrides. The app was installed only for this repo,
and its Actions history was empty when the ledger was initialized. No card,
paid add-on, sticky disk or Docker-layer persistence is configured here.

## Kernel integration

Kernel work runs through the project's Forge ephemeral Docker launcher with
pinned source/compiler inputs and explicit image identity. A relocated image or
new runner is a new validation attempt. Compilation, a linked kernel, a packaged
boot image and hardware acceptance remain separate evidence levels.

The initial integration targets the previously compiled M5s Yassy panel object;
its public source/toolchain packaging is being prepared. Do not interpret the
runner probe as that kernel check passing. Full Android ROM jobs are not enabled
by this workflow.
