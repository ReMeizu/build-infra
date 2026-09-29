# Preserved Forge launcher

`forge_ephemeral_build.py` is copied byte-for-byte from the project's Build Station launcher, source checkpoint `7054746c782100d6bff4d72d9a64579ec3b408f4`.

SHA256: `9a01d1c452ecf14674a9df1f7512176f30b1fe2949660e2ea743960e7d400bb8`.
Original source commit: `7054746c782100d6bff4d72d9a64579ec3b408f4`.
Original project path: `scripts/forge_ephemeral_build.py` in AndroidForge Build Station. Existing notices are retained; no third-party license is invented here. Project owner authorized infrastructure publication.

The separate adapter `scripts/kernel_forge.py` adds one metadata contract for a kernel-only image. Read-only source mounts, non-root container, no network during compilation, immutable image identity, distinct filesystem checks, complete source provenance, leases, bounded cleanup, required-artifact hashes and SUCCESS semantics remain unchanged. Source acquisition/image build happen before Forge; all kernel compilation goes through this launcher.
