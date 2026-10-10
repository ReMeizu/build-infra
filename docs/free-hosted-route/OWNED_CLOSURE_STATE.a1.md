# Native owned-container closure refusal correction

An owned synthetic refusal control demonstrated that the prior helper accepted a known container ID's absence even when the unchanged Forge ownership guard returned cleanup_needed=true and the Docker client was unreaped. This bypassed the real launcher's late-creation protection. The control executed no Docker command; it does not invalidate prior normal attached A6–A8 attempts.

The known-ID branch now requires both an explicit completed cleanup result and client_reaped=true, before its independent full-ID absence check. Ownership label/recipe binding, producer JSON preservation, actual absence proof and the no-ID late-creation branch remain intact. Completed cleanup may be independently proven while the original producer JSON still records the earlier pending state; producer history is not rewritten.

Five focused controls pass: normal reaped/absent completion, completed cleanup preserving pending producer bytes, unreaped-client refusal, unresolved late-creation cleanup refusal, and a still-existing known-container refusal. These are helper refusal tests, not runtime build evidence. All eleven frozen SDK source files and the official Forge launcher remain byte-identical. No provider, target, flag, source inventory, image definition or retention crypto changes accompany this correction.
