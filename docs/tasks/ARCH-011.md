# ARCH-011

- Title: reject original malformed ZIP names across Windows normalization
- Status: implementation and local regression checks complete; fresh Windows CI pending
- Owner: ARCH-011 independent diagnosis agent
- Reviewer: root coordinator

## Model and reasoning

- Requested model: GPT-6.1 Sol, retained from the independent review tasks.
- Requested reasoning: max.
- Actual exposed configuration: inherited parent session; serving identity and reasoning effort are not independently introspectable. No further agent was created.

## Approved specification and decisions

- Coordinator escalates the repeated Windows ZIP-path regression under Decision 28 and authorizes only deployment verifier/test boundary changes.
- Reject malformed raw ZIP names on every platform before extraction. Preserve existing unsafe-path rejection messages and the assertions that failed verification creates no output directory.
- Do not modify source data, engine code, analytical packs, static site bytes, workflow, primary results or existing evidence. Root owns the new candidate revision and fresh CI.

## Required inputs and dependencies

- First Windows evidence: `data/runtime/release-2026-10-22/windows-candidate-39a836c.log`. Lines 337–352 show the malformed backslash case reached the manifest-file-set check rather than an unsafe-path check; Windows reported one failure, 202 passes and two skips.
- Second Windows evidence: `data/runtime/release-2026-10-22/windows-candidate-119620470339.log`. Lines 324–340 show that, after preserving raw member spelling while writing, the fixture's `path in archive.namelist()` assertion failed on Windows reading; again one failure, 202 passes and two skips.
- Inspected the installed Python standard library's `ZipInfo.__init__`: it stores `orig_filename` before replacing the host directory separator in `filename`, and before NUL truncation. This accounts for both failures. Actual Windows evidence uses Python 3.11.9.
- Python standard library and the existing pytest suite. No Windows shell/runtime is available to this agent; the fresh hosted Windows job remains necessary for final CI acceptance.

## Files owned

- `scripts/verify_deployment.py`
- `tests/integration/test_deployment_integrity.py`
- `docs/tasks/ARCH-011.md`

## Expected output

- `_check_file_entry` validates `ZipInfo.orig_filename` before the normalized `filename`, then requires their safe canonical spellings to agree. Host normalization can no longer hide raw backslashes or NUL suffixes from the verifier.
- The real-ZIP fixture continues preserving the deliberately malformed member spelling while writing and now confirms that spelling through `orig_filename` when reading. It does not expect Windows' normalized `namelist()` to preserve backslashes.
- Explicit normalized-`ZipInfo` regressions run on every host: raw `site/a\b` versus normalized `site/a/b`, and raw `site/index.html` plus a NUL suffix versus its truncated filename. Both must fail the unsafe-path check even when the normalized name looks safe.

## Acceptance checks

- PASS: `.venv/bin/python -m pytest tests/integration/test_deployment_integrity.py -q` → **34 passed in 0.15s** on macOS, 22 October 2026.
- PASS: all 32 pre-existing valid-package and corruption cases still pass. Original unsafe-path message regexes and no-output assertions remain unchanged.
- PASS: both new all-host simulated-normalization cases reject at the original unsafe-path check. These exercise the Windows read-side behavior without changing host filesystem behavior or weakening the archive fixture.
- PASS: `git diff --check -- scripts/verify_deployment.py tests/integration/test_deployment_integrity.py` returned exit 0.
- Scope inspection confirms no changes to gate names/typing, attestation hashes, archive size limits, source/engine behavior, static frontend files or extraction destinations.
- PENDING: root freezes the new candidate and obtains an actually passing hosted Windows CI result. Local checks and standard-library analysis are not presented as a fresh Windows runtime pass.

## Escalation issues

- Root escalated after two unsuccessful attempts. This independent diagnosis used both actual failure logs and the standard-library normalization sequence; it did not retry the same fixture-only repair.
- The defect affected validation as well as the fixture: checking normalized `filename` alone could conceal malformed raw member bytes on Windows. Validating `orig_filename` preserves the cross-platform security boundary, while the fixture change observes the correct raw field.
- No unresolved local failure remains. Root owns fresh CI, candidate/release evidence renewal and publication. No commit was created by this task.
