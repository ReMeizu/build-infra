# ROM build worker

The manual `rom` mode allocates a 16-vCPU worker with a 600-GiB ext4 scratch
filesystem on its ephemeral disk. The full four-hour job reserves 1,944
normalized minutes before allocation. The monthly and total limits still apply.

The `rom-short` mode uses the same runner and scratch volume with a three-hour
job cap and a 1,464-minute reservation. Its session expires after 165 minutes,
leaving the same 15-minute setup and cleanup allowance. Earlier reservations
remain charged to the ledger; the 9,000-minute monthly and 18,000-minute
lifetime caps stay in place.

The `rom-90` mode uses this same private-input ROM worker with a 90-minute
job limit and a 744-minute reservation. Its session expires after 75 minutes;
the enclosing process is bounded to 78 minutes. It retains the 15-minute
setup and cleanup allowance and changes neither cap. Source/input readiness
must be checked before spending the final remaining reservation.

This is an SSH-operated build worker. Dispatch alone does not build a ROM.
Only the triggering GitHub account can connect using its registered SSH key;
the connection command appears in the provider's runner setup log.

1. Connect and read `/mnt/forge/rom-session/ready.json` for the actual deadline.
2. Transfer pinned source exports and matching device/vendor inputs over SSH.
   Do not put credentials or private vendor archives in the repository or Actions artifacts.
3. Touch `/mnt/forge/rom-session/activity` during transfer and active work.
   An idle worker expires after 35 minutes; activity cannot extend the
   225-minute session deadline or the workflow's four-hour limit.
4. Provision the matching Android container image. Run graph and full-ROM jobs
   through Forge with read-only source, a separate output directory, a non-root
   build user, and the remaining session time as the upper bound.
5. Retrieve the complete build logs, Forge receipts, generated images and ROM
   packages over SSH. Verify their hashes and inspect package metadata before
   reporting a successful build. Hardware testing is a separate step.
6. After retrieval, atomically write `finished.json` in the session directory:

```json
{"status": "completed", "artifacts_collected": true}
```

Use `failed` or `blocked` when applicable. A completion marker releases the
worker; it does not certify any ROM. Local evidence must distinguish compilation,
packaging and hardware results. Only scratch and session metadata are uploaded
to public Actions artifacts. Provider persistent storage and paid cache add-ons
are not used.
