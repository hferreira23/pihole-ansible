# Working on hferreira23.pihole

This is a personal learning fork of `sbarbett/pihole-ansible`, not the maintained
upstream project. Make changes for **this collection's namespace**,
`hferreira23.pihole`. Read [CONTRIBUTING.md](CONTRIBUTING.md) for the executable
setup and validation workflow, then [examples/README.md](examples/README.md) for
user-facing behavior. More specific instructions in nested directories, if any,
apply within those directories.

## Start here

1. Read the user's scope and run `git status --short`. Preserve pre-existing
   changes; never reset or overwrite unrelated work.
2. Read `galaxy.yml`, `meta/runtime.yml`, and the relevant module and tests.
3. Trace shared behavior through `plugins/module_utils/` before adding a helper
   or copying logic. A shared change can affect all ten modules.
4. Add or update regression tests, documentation, and examples together.
5. Run the checks below and report what ran, what failed, and what was not tested.
   Never imply that mocked tests prove live Pi-hole compatibility.

## Repository map

| Path | Purpose |
| --- | --- |
| `plugins/modules/` | Ansible module entry points, argument specs, `DOCUMENTATION`, `EXAMPLES`, and `RETURN` |
| `plugins/module_utils/lists.py` | Shared allow/block list argument spec, planning, reconciliation, check mode, and gravity |
| `plugins/module_utils/api.py` | Response validation, fail-closed group resolution, structured failure details |
| `plugins/module_utils/client.py` | Collection-owned Requests transport and wrapper around external `pihole6api` endpoint classes |
| `plugins/doc_fragments/` | Shared connection/TLS and list-management documentation, merged by `ansible-doc` |
| `examples/` | Standalone collection playbooks and usage guide |
| `tests/unit/` | Module reconciliation, error paths, argument parsing, and transport tests |
| `tests/integration/` | Loopback HTTPS tests and built-collection documentation/example validation; no live Pi-hole |
| `roles/` | Historical role source and role examples; excluded from Galaxy builds |
| `galaxy.yml`, `meta/runtime.yml` | Collection identity, packaging exclusions, and minimum Ansible version |
| `.github/workflows/` | Test workflow, commit linting, release automation, Galaxy publishing |
| `.github/scripts/ci_test_changes.py` | Conservative changed-file gate for the single latest-Ansible CI test job |

### Architecture and boundaries

- The modules run on the Ansible target or delegated host, not necessarily the
  controller. Python dependencies and CA files must exist on that execution host.
- List modules are thin wrappers around `module_utils/lists.py`; keep their
  semantics identical except for list type. Preserve batch and legacy inputs.
- `pihole6api` is an external Python dependency, **not vendored source**. The
  collection owns its transport because the dependency's connection initializes
  insecure TLS. Do not bypass the collection client or monkeypatch global
  Requests/library state. Changing this repository does not fix direct consumers
  of the external package.
- Roles still contain upstream namespace references and have a separate history.
  Do not silently refactor roles or rename their module references while fixing
  collection modules. `galaxy.yml` excludes `roles`; a collection build therefore
  does not validate or ship them.

## Contracts to preserve

- For **lists**, omitted `groups` preserves existing memberships, even during
  another field update; explicit `[]` clears them. New lists with omitted groups
  have no memberships. For **clients**, omission still defaults to `[]` and clears
  memberships; do not accidentally document or implement list semantics there.
- Integer group IDs stay integers. Numeric strings are names. Unknown group names
  and failed/malformed reads must fail, never silently drop assignments or imply
  an empty server. Resolve names before batch writes.
- List check mode authenticates and reads state, predicts changes, and skips list
  mutations and gravity. It still fails on read errors and unknown names. Do not
  claim equivalent check-mode behavior for unrelated modules without checking
  their implementation.
- HTTP errors, API `error`, and nonempty `processed.errors` are failures, even at
  HTTP 200. Preserve structured response/status details when available. Record
  change after a successful write, not before a rejected one.
- Batches are not transactions. Retain earlier successful results and `changed`
  on later failure; do not imply rollback or atomicity.
- Gravity runs once per successful changed list invocation, never on convergence,
  check mode, or a failed batch. Do not infer mutations from a gravity log string.
- Verify HTTPS certificates from the **first authentication request** onward.
  `validate_certs` defaults to true; `ca_path` is a CA bundle on the execution
  host. Keep explicit opt-out available, but never make it the default or suppress
  its warnings globally.

## Required workflow

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r tests/requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q plugins tests .github/scripts
git diff --check
.venv/bin/ansible-galaxy collection build --output-path dist
```

Use Python 3.13+ for the documented development setup and Ansible 2.19+ as required
by `meta/runtime.yml`. CI tests only the latest stable ansible-core on supported
Python 3.14, explicitly upgrading unpinned `ansible-core` on every test run.
Advance Python only when Ansible supports it; rolling `3.x` can select an
unsupported interpreter before Ansible is ready for it.
There is no 2.19 compatibility job. Do not pin/cap the test target or skip its
installation because of a pip-cache hit. A lightweight changed-file gate skips
draft PRs and irrelevant-only changes without leaving a required check pending;
manual dispatch and failed detection run tests conservatively.
Run focused tests while iterating, then the full suite. The documentation suite
builds and installs into a temporary location, checks `ansible-doc` JSON, text,
and snippets, checks list docs against argument specs, and syntax-checks examples.
It also validates example module inputs: syntax-check alone does not catch an
unsupported module argument such as putting task-level `check_mode` inside a
module's argument mapping.

If documentation or options change, update the appropriate doc fragment and
`RETURN`/examples, then run `tests/integration/test_documentation.py`. Use the
fork's FQCN in examples. Generated `ansible-doc --snippet` output uses short names;
qualify those task keys before recommending them to users.

## Safety and scope

- Never use real Pi-hole credentials, inventories, or servers unless the user
  explicitly authorizes a live test. Examples contain placeholders and may alter
  lists, groups, and clients when run normally. Tests should use mocks or loopback.
- Keep credentials out of source, test output, and artifacts. Password arguments
  must retain `no_log=True`; use Vault or another secret store in examples.
- Do not install into system Python or use `--break-system-packages`; use a venv.
  Avoid replacing a user's installed collection when verifying docs; use temporary
  collection paths as described in the contributor guide.
- Do not commit, push, create branches/PRs, publish artifacts, or contact upstream
  without an explicit request. If asked to commit, use Conventional Commit titles
  consistent with the existing commit-lint and release-please workflows.
- Do not bump versions or hand-edit generated release history as part of an
  ordinary fix. Release-please manages version/changelog changes; Galaxy publishing
  happens through the release workflow and requires maintainer authorization.
- In the final handoff, summarize changed behavior, checks actually run, remaining
  warnings/limitations, and any migration impact (especially TLS defaults).
