# Working across Mac and Windows

Use the same private GitHub repository on both laptops. The primary checkout is
`/Users/suhaill/Developement/brisbane-transport-resilience-lab` on the Mac; choose a
normal development folder on Windows and follow the PowerShell setup in `SETUP.md`.

## Hand off work

1. Finish a bounded task and record its files, checks and remaining issues under
   `docs/tasks/`.
2. Commit and push that task from the laptop that owns it.
3. Pull those changes on the other laptop before starting dependent work. Do not
   edit the same files concurrently across laptops.
4. Use the project agent profiles and current decision log. Architecture and
   analytical assumptions require the designated Max review before dependent code.

## Keep data separate from code

Raw feeds, local databases, recorded snapshots and experiment files are ignored by
Git. Pulling the repository does not copy the Mac's recording history to Windows.
The Mac currently owns scheduled morning collection. An additional laptop can run
its own development captures in a separate archive, but those receipts must not be
silently merged or treated as one continuous recording.

Transfer a verified reproduction pack when another laptop needs the exact archived
experiment inputs. A fresh download supplies current data, not a replacement for
an earlier recorded snapshot. Check the pack's hashes before recomputing results.

## Publication

Development stays private. Future morning coverage, three reviewed bundles,
publication conditions, checks and backend-independent demo verification must pass
before the repository, data assets or Pages demo are made public. The accepted plan
already authorizes publication when those checks are satisfied.
