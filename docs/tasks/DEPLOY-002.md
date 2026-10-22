# DEPLOY-002: pinned GitHub Pages deployment workflow

- **Task ID:** DEPLOY-002
- **Status:** workflow implementation complete; coordinator release review pending
- **Owner:** bounded implementation
- **Reviewer:** root coordinator

## Model and reasoning

- Requested model: GPT-6 Luna
- Reasoning effort: max
- The serving identity is not independently introspectable. Work stayed within the
  workflow and handoff paths assigned to this task.

## Approved specification and decisions

Implemented the deployment boundary approved by Decision 28. The manually triggered
workflow accepts a release tag and archive SHA-256, checks out the dispatched
`github.sha`, resolves the release's Git tag object chain to its commit, and requires
that commit to equal the checked-out candidate. It locates exactly one
`github-pages-site.zip` asset on that same repository release and downloads it via
the authenticated GitHub REST API into `RUNNER_TEMP`.

The workflow passes the pinned archive and candidate SHA to the standard-library
`scripts/verify_deployment.py`. Only the validator's verified `site/` directory is
uploaded as the Pages artifact and deployed. API inputs are passed through environment
variables to Python; the bearer token is sent only on REST API requests, not logged or
forwarded to HTTPS asset redirects. Existing release gates are consumed through the
attestation validator and are not modified or rerun in GitHub Actions.

The workflow does not use private archive or release-evidence scripts, install project
dependencies, publish a release, or initiate a deployment during this task. Root
controls any actual workflow dispatch and publication.

## Required inputs and dependencies

- Decision 28 in `docs/DECISIONS.md`.
- `scripts/verify_deployment.py`, using only the Python standard library.
- A same-repository release with exactly one uploaded
  `github-pages-site.zip` asset, a release tag resolving to the dispatched candidate
  SHA, and the corresponding reviewed archive SHA-256.
- GitHub's [custom Pages workflow guidance](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
  and [release asset REST API](https://docs.github.com/en/rest/releases/assets?apiVersion=2022-11-28)
  were checked for action wiring, permissions, binary-download redirects, and the
  read-only Contents permission.

## Files owned

- `.github/workflows/pages.yaml`
- `docs/tasks/DEPLOY-002.md`

## Expected output

A `workflow_dispatch` Pages workflow that validates the exact tag, release asset,
archive digest, attestation, manifests, site file set, and release gates before making
the verified static site available to the Pages deployment action. Workflow
concurrency serializes deployments without cancelling an active deployment.

## Acceptance checks

- [x] Workflow inputs require `release_tag` and `archive_sha256`; Python validates
  their formats before making requests and does not interpolate them into shell code.
- [x] REST lookup is scoped to `GITHUB_REPOSITORY`, verifies the release tag resolves
  to `github.sha`, paginates release assets, requires a unique named ZIP asset, and
  handles the authenticated asset API's binary response or HTTPS redirect without
  forwarding the bearer token. Checkout does not persist its credentials in Git.
- [x] Existing standard-library validator receives `--archive`,
  `--expected-sha256`, `--candidate-revision`, and a fresh runner-temp output path.
  Pages upload path is the validator-extracted `site/` directory.
- [x] Workflow uses `actions/configure-pages@v5`,
  `actions/upload-pages-artifact@v3`, and `actions/deploy-pages@v4`; job permissions
  are `contents: read`, `pages: write`, and `id-token: write`; environment is
  `github-pages` with the deployment URL; concurrency has `cancel-in-progress: false`.
- [x] PyYAML parsed the workflow; the inline downloader compiled; each shell step
  passed `bash -n`; action versions, permissions, and workflow input wiring were
  asserted by a local static check.
- [x] Owned-file LF/trailing-whitespace checks and `git diff --check` on the tracked
  workflow — passed.
- [x] No GitHub workflow dispatch, repository API request, release download, or Pages
  deployment was run during validation.

## Escalation issues

None. `actionlint` is not installed in the local environment; YAML parsing, inline
Python compilation, and shell syntax checks passed. A live API or deployment test is
intentionally deferred to the coordinator's approved release process.
