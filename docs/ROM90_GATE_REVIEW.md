# Bounded ROM90 gate change

PROPER-FIX: the existing 180-minute private ROM worker reserves 1,464 normalized
minutes. The actual 2026-10-09 ledger leaves only 744 October minutes and 746
lifetime minutes, so that mode is correctly denied. A distinct `rom-90` mode
uses the same real private-input ROM path, 16-vCPU runner, scratch admission,
SSH endpoint handling, exact policy validation, ledger CAS and completion gate.
This does not run a native ROM through the unrelated kernel mode.

FACT: the source base is build-infra commit
`d414bf0d943a0d51884454447da43493500785cd`. The read-only ledger snapshot has
Git blob `84434575058c29226502a175dd0aedb8805fe7a9` and is retained in
`tests/fixtures/blacksmith-ledger-20261009.json`. Monthly reservations are
8,256 and lifetime reservations are 17,254. Cost is `(90 + 3) * (16 / 2) = 744`;
one admitted reservation would reach 9,000 monthly and 17,998 lifetime. All
existing caps, reservation rows and no-refund semantics remain unchanged.

The unchanged ROM worker expression reserves 15 job minutes outside the
session: 75 minutes of actual session, 78 minutes for its enclosing process,
90 minutes for the runner job. The existing 1-to-345-minute session guard
accepts 75; heartbeat cannot extend its hard deadline. Existing artifact
collection and rejection of incomplete collection remain unchanged.

Files: workflow dispatch options and all four ROM conditions include `rom-90`;
`scripts/budget.py` and `config/blacksmith-policy.json` bind its exact reviewed
cost; budget tests use the actual prior ledger, check preserved history and a
subsequent denied write; session tests check the 75-minute deadline. README
now reflects the already-reviewed 18,000 lifetime cap instead of its stale
9,000 text. No cap is increased by this change.

Expected next marker: after independent source review and publication, a new
manual ROM90 dispatch may reserve exactly 744 and expose the same authenticated
private-input session. This preparation is not a dispatch, reservation, ROM
build result or guarantee that the remaining GUI source graph can finish.

Rollback condition: any unexpected change to caps, historical reservations,
private artifact handling, runner identity or session deadline rejects this
change. Remaining source and private-input admission must pass before spending
the final reservation; no duplicate dispatch is justified.

Verification: `python3 -m unittest discover -s tests`; `git diff --check`.
Both passed with 50 tests on 2026-10-09. No live ledger write, paid allocation,
push, workflow dispatch or image publication was performed by this preparation.
