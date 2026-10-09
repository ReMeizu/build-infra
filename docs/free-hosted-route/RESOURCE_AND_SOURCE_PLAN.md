# Standard public GitHub runner: native intermediate continuation

FACT (primary docs checked 2026-10-09): public `ubuntu-24.04` standard runners
provide 4 CPUs, 16 GB memory and 14 GB SSD; standard public-repository compute
is free. Actual hardware/free capacity still require measurement; larger runners
have separate billing. [Runner specification](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

FACT: hosted jobs have a six-hour execution limit. This isolated route uses a
330-minute job, a 260-minute compile/setup step and a 40-minute retention step,
leaving 30 job minutes outside those bounds. Inside the compile/setup step,
source acquisition and Docker preparation consume the same absolute allowance:
the remaining compiler window is at most 250 minutes minus elapsed setup;
owned launcher/container cleanup and readonly verification have a 10-minute
reserve. The worker's frozen deadline never exceeds that remaining window.
[Execution limits](https://docs.github.com/en/actions/reference/limits)

FACT: free compute does not imply unlimited free Actions artifact storage.
No Actions artifact or cache upload occurs here. Output is GPG ciphertext in a
unique per-run GitHub prerelease, created only after actual public-source
admission, input after-witness and encryption completion. Forge output requires
actual compiler termination. The separate SETUP_FAILED scope retains only actual
terminated Docker setup-command evidence and never claims Forge execution.
Each asset stays below 2 GiB. The upload step alone receives the built-in token;
compilation never receives it, and no new secret is written. GitHub server digest
and complete remote ciphertext size/SHA readback are mandatory; the local task
private key must authenticate decryption before any extraction.
[Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions),
[Release asset limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

## Real measurements and rejected estimates

FACT: the historical audited b6 payload has 87 projects / 71 selected parts,
144,388 source files / 1,628,260,457 source bytes. Total expanded carrier is
5,197,848,888 bytes, archive 1,526,180,773 bytes, SHA256
`93c7cb5d391a12ed6aa4ac5c381f5fa1055452052ba06d2829c061928587e36b`.
The carrier was not publicly uploaded. It contains opaque history/freeze data
that does not belong in the new public route.

FACT: the new thin public source lock adds genuine libusb and describes
88 projects / 72 selected parts / 1,628,899,178 source bytes. Its SHA256 is
`b1155bfed25503b75b6ea9bf19e92601c94b064ae8e16bbc3e1ba1759f1a3e36`;
original GN inventory SHA256 is
`6e222d71be39e5ae6282ae6abca56d86be3aa0ac8af99f9f22a9428f71f53e6a`.
`PUBLIC_SOURCE_REVIEW.json` binds the 43,210,596-byte / 88-file thin source
export; functional preservation, public LFS and updater transport reviews are
stored alongside it. Full375, native compilation and hardware runtime remain
false at this preparation stage.

FACT: readonly projection of real Rust component manifests gives 58 host files /
246,695,249 bytes plus 27 AArch64 files / 102,313,666 bytes: 85 unique files /
349,008,915 bytes. The earlier 2.4 GiB Rust estimate is REJECTED. New source plus
Rust shadow floor is 1,977,908,093 bytes (~1.84 GiB). Other immutable tools remain
on disk, readonly-mounted; all source transformations, Rust projection, compiler
objects, cache, temporary files and generated images remain in a fresh 10 GiB
tmpfs. Actual disk admission reserves 12,579,983,649 bytes for source/tool inputs,
retained downloads/checkouts and Docker headroom.

FACT: original j6 worker/preparation requires 6 CPUs, 24/16 GiB memory and
16 GiB tmpfs and cannot run on this standard runner. The new real source
successor changes resource admission/parallelism to j2 and centrally binds its
final worker hash. It preserves original GN labels, SDK/Clang bytes, feature
flags, source patches, dependency checks and raw-image policy. The genuine
four-library completion is atomically checkpointed before image work, with no
full-product or runtime claim.

INFERENCE: the measured source/Rust floor permits trying four real libraries
within this smaller host; it does not certify compilation peak RSS or full375
fit. Runtime requires >=12 GiB actual MemAvailable/cgroup remainder at setup,
>=2 CPUs/quota and measured tmpfs capacity. Library and image phases have new
independent checks; images require >=5 GiB tmpfs free (historical 4 GiB floor
plus retention headroom) and >=3 GiB memory. A complete ciphertext must also fit
a conservative uncompressed-tar +2% +16 MiB bound. No assumed compression ratio
or 64 MiB-only check can admit an archive that may fill RAM.

## Acquisition, failure collection and publication

`acquire.py` anonymously fetches original project HEAD/tree and verifies every
admitted source file, all official prebuilt members and all offline wheels.
Git-LFS uses public original objects (ICU1 and ACE2); the exact declared global
`.gn` link is created. Git executable bits are checked, then historical declared
0644/0664/0755/0775 modes are materialized on immutable disk inputs. Thin public
source metadata supplies patches/headers; private Android donors, captures,
credentials, SSH keys, opaque bundles and private freeze records are excluded.

`free_native_run.py` uses unchanged Forge SHA256
`9a01d1c452ecf14674a9df1f7512176f30b1fe2949660e2ea743960e7d400bb8`,
unchanged official Dockerfile bytes, actual fresh Docker ID/health and an
immediate identity recheck. Its owned Popen receives SIGINT on timeout, giving
Forge its real cancellation/cleanup opportunity. Independent post-finalization
verifies exact invocation labels/full container IDs and readonly source/tool
inputs. Original failed Forge/state records remain unchanged. Inflight and
pre-finalization records let the retention consumer repeat bounded closure and
verification after an outer interruption; no after-flag is fabricated.

`retain_release.py` admits only explicit genuine native linked ELFs/images and
known public producer evidence, then calls the tested GPG helper. RAM shortage
rejects publication before sealing. Plaintext never enters a Release, artifact,
cache or public log. Ciphertext readback is required and cannot relabel a failed
native image build as success. The MDC authenticates encrypted content; it is
not a producer signature. Actual source/recipe provenance and asset digests
provide the producer binding.

Activation is an explicit push restricted to
`refs/heads/codex/free-native-20261009`, first run attempt, actual public
`ReMeizu/build-infra`. This avoids changing main merely to register a new manual
workflow; a later manual event is accepted only for the same branch. First push
allocates real standard compute, so root independent review must pass before
publication. [Dispatch/default-branch behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)

No workflow, Release, upload, paid allocation, ledger/cap mutation, hardware
flash or new GitHub secret was performed by this preparation. The original full
375-component phone image remains a separate required gate.

Verification: `python3 -B docs/free-hosted-route/test_route.py`;
`python3 -B -m unittest discover -s tests`; Python AST parse and source hashes.
The source controls include actual original worker preservation and a real
owned-process timeout/reap with retained RAM logs. Crypto owner independently
ran actual roundtrip/tamper/refusal controls. Live resource/compiler/output
acceptance still requires the reviewed first cloud run.


## Exact measured production successor

FACT: authenticated run37986122430 passed the original88/72 source/tool/image
admission, then GN requested relational_store:native_rdb. The new reviewed
successor adds13 pinned mandatory production providers, preserving all88 original
projects,144407 source rows and72 normalized part feature/syscap maps. Actual
source is101 projects /85 parts /174299 files /1843410795 source bytes; expanded
inputs5249408474 bytes. Source lockcd0fd17d93ddf0c7f4cd2da211fafb746cca9aaf8e16e8a9f4867e9700cce4c0
and GNIbc5b4da2894494c066978098d9e811cb208fca87588c1e73c0dea4f45e4d4e06
are admitted by exact guards, not an arbitrary count range. Rust layout, SDK,
wheels, original feature values, target labels, j2 and RAM floors are unchanged.

The [source/runtime guard state](MEASURED_COHORT_GUARD_STATE.a1.md) and its frozen
verification table bind the production witnesses and three independently passed
positive/refusal controls. Full GN closure, target compilation, full375 images
and hardware acceptance remain false until their real producer gates pass.
Historical source freezes above remain historical; this successor replaces
only the reviewed cohort execution admission.
