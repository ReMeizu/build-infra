# Forge launcher provenance

`forge_ephemeral_build.py` is an unchanged copy of AndroidForge Build Station's
`scripts/forge_ephemeral_build.py` at commit
`7054746c782100d6bff4d72d9a64579ec3b408f4`.

SHA256: `9a01d1c452ecf14674a9df1f7512176f30b1fe2949660e2ea743960e7d400bb8`.
Existing notices are retained.

`scripts/kernel_forge.py` adds the kernel-only image contract. Source acquisition
and image preparation run before Forge; compilation runs through the launcher.
Read-only inputs, non-root execution, network isolation, image/source identity,
filesystem checks, leases, cleanup and artifact validation remain in force.
