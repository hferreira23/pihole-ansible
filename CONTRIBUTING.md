# Contributing to this learning fork

This repository builds the `hferreira23.pihole` Ansible collection. It is a
personal learning fork, not a production-supported replacement for
[sbarbett/pihole-ansible](https://github.com/sbarbett/pihole-ansible). Direct changes
to the maintained upstream project there. The steps below are for local work on
this fork; AI agents should also read [AGENTS.md](AGENTS.md).

## 1. Understand the scope

Before editing, inspect `git status --short` and preserve unrelated work. Read the
relevant module, shared helpers, and tests. The module flow is:

```text
Ansible module entry point and argument specification
  -> collection module_utils (shared list reconciliation and response validation)
  -> collection PiHole6Client / verified Requests transport
  -> external pihole6api endpoint wrappers
  -> Pi-hole v6 API
```

`block_list` and `allow_list` share their implementation in
`plugins/module_utils/lists.py`. TLS and HTTP/API failure handling live in
`plugins/module_utils/client.py`; name resolution and response-shape validation
live in `plugins/module_utils/api.py`. Check those boundaries before adding a new
copy of existing logic.

The `roles/` tree is historical, excluded from the Galaxy artifact, and still has
upstream namespace references. Treat role work as a separate scope. The current
automated tests exercise collection code, not deployments of those roles.

## 2. Set up an isolated development environment

From the repository root, with Python 3.13+:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r tests/requirements.txt
.venv/bin/ansible --version
```

`tests/requirements.txt` installs Ansible, pytest, and the tested `pihole6api`
version. The dependency is not source in this repository. Do not edit a
site-packages copy or the system Python environment to implement a collection fix.

Ansible requires version 2.19+ (`meta/runtime.yml`). The single CI test target
uses supported Python 3.14 and unpinned `ansible-core`, explicitly upgraded on
each run. Advance the Python minor only when Ansible supports it: rolling `3.x`
can select a newly released interpreter before Ansible works with it.
There is no older-version compatibility job; this does not change the collection's
declared minimum. The pip
cache stores downloads, not an installed environment, so it does not freeze the
latest target. Python setup also checks for the newest matching 3.14 patch release
rather than relying only on the runner's preinstalled versions.
To reproduce the CI dependency selection locally:

```sh
.venv/bin/python -m pip install --upgrade -r tests/requirements.txt ansible-core
.venv/bin/python -m pytest -q
```

## 3. Make a focused change and add coverage

- Match the existing module/Ansible patterns; reuse shared helpers.
- Keep password fields `no_log=True` and TLS verification enabled by default.
- Preserve batch and legacy list inputs, omitted-vs-empty memberships, and the
  distinction between list and client group defaults.
- Check read failures, rejected writes, HTTP-success/API-error bodies, and
  partial batch failure. Never treat a failed read as absence.
- Test check mode, convergence, and gravity when changing list reconciliation.
- Keep public argument documentation, examples, and return schemas synchronized.
  Document user-visible compatibility changes explicitly.

Useful focused checks:

```sh
.venv/bin/python -m pytest tests/unit/test_lists.py -q
.venv/bin/python -m pytest tests/unit/test_groups_clients.py -q
.venv/bin/python -m pytest tests/unit/test_client.py tests/unit/test_module_tls_options.py -q
.venv/bin/python -m pytest tests/integration/test_tls.py -q
.venv/bin/python -m pytest tests/integration/test_documentation.py -q
```

Tests use mocked API responses and a temporary loopback HTTPS server, not a live
Pi-hole. Documentation tests build and install the collection into temporary
directories, so they test packaged doc fragments instead of accidentally reading
a previously installed version. `tests/conftest.py` provides the collection's
namespace for direct unit-test imports; no editable Python-package install is
needed.

## 4. Maintain module help and examples

- `DOCUMENTATION`: module purpose, options/types/defaults/requirements, notes,
  related modules, and accurate check/diff-mode attributes.
- `plugins/doc_fragments/connection.py`: common TLS options and execution-host
  requirements. Keep every module using this fragment.
- `plugins/doc_fragments/list_management.py`: common batch/legacy list options,
  membership semantics, read/failure behavior, check mode, and gravity rules.
- `EXAMPLES`: valid task YAML using `hferreira23.pihole` FQCNs and variable-based
  secrets. `check_mode` is a task keyword, not a module argument.
- `RETURN`: actual result fields and conditions, including check-mode predictions
  and available API error details. Do not document fields the module never returns.
- `examples/`: complete playbooks. See [the examples guide](examples/README.md).
  Use reserved placeholder addresses, identify destructive operations, and do not
  delete Pi-hole's built-in `Default` group in an introductory example.

To inspect the built artifact manually without replacing a user's collection:

```sh
.venv/bin/ansible-galaxy collection build --output-path dist
verify_dir="$(mktemp -d)"
.venv/bin/ansible-galaxy collection install dist/hferreira23-pihole-*.tar.gz \
  --collections-path "$verify_dir" --offline --force
ANSIBLE_COLLECTIONS_PATH="$verify_dir" .venv/bin/ansible-doc hferreira23.pihole.block_list
ANSIBLE_COLLECTIONS_PATH="$verify_dir" .venv/bin/ansible-doc --json hferreira23.pihole.block_list
ANSIBLE_COLLECTIONS_PATH="$verify_dir" .venv/bin/ansible-doc --snippet hferreira23.pihole.block_list
ANSIBLE_COLLECTIONS_PATH="$verify_dir" .venv/bin/ansible-playbook \
  --syntax-check -i localhost, examples/manage-block-lists.yml
```

Use the archive for the current version in `galaxy.yml` if `dist/` contains more
than one build. Rebuilding the same local version requires `collection build
--force`; this only overwrites the local artifact, not a published release.
The install `--force` above is deliberately restricted to the fresh temporary
directory. Avoid a global force-install.

Ansible's generated snippets currently use short names even when requested by
FQCN. Qualify the generated task key before use. Check text **and** JSON help:
successful YAML parsing alone does not guarantee useful rendered help. Similarly,
playbook syntax-check does not validate every module option; the documentation
tests check example input keys too.

Normal example runs can modify a real Pi-hole. Supply credentials through Vault
or another secret store and obtain explicit permission before any live run.
List check mode still authenticates/reads and requires existing referenced groups.

## 5. Validate before handing off

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q plugins tests .github/scripts
git diff --check
.venv/bin/ansible-galaxy collection build --output-path dist
git diff --stat
git status --short
```

Use `collection build --force` only when intentionally replacing your own local
build. Do not add virtual environments, credentials, caches, or generated tarballs
to a change. Review new/untracked files as well as `git diff`.

The test workflow runs on pull requests and explicit manual dispatch only.
Pushes to `main` or feature branches do not trigger it, avoiding duplicate tests
after merge. Draft PRs skip work; marking them ready starts validation, and
converting them back to draft cancels superseded runs.
Title/body/label edits do not retrigger tests. New runs cancel older runs for the
same PR/ref.

A lightweight changed-file gate skips the expensive job for changes limited to
Markdown guides, historical roles, or unrelated release/bot/workflow configuration.
Changes to plugins (including embedded documentation), tests, example playbooks,
runtime/packaging metadata, the test workflow/selector, and unknown paths still
run. Renames include both old and new paths. Missing history or detection errors
run tests conservatively; manual dispatch always runs the suite. There are no
workflow-level path filters, so the existing required `unit (ansible-core)` check
is reported as skipped rather than left pending for irrelevant changes.
If repository rules still require `unit (ansible-core~=2.19.0)`, remove that
obsolete requirement; the old compatibility job is no longer emitted.

The single test job logs its resolved Ansible version, checks dependencies,
compiles Python, runs the suite, and builds the collection. JUnit reports are
written outside the collection tree and retained for 14 days even if tests fail.

Optional linters have
repository configuration (`.ansible-lint`, `.yamllint`) but are not installed by
the test requirements; do not claim they ran unless you actually ran them. A
successful collection build does not prove live API compatibility or role safety.

Summarize behavior changes, test commands/results, untested paths, and migration
requirements. Avoid claiming the whole repository was validated when only a
focused test ran.

## 6. Commits and releases are separate operations

Do not create commits, branches, pull requests, tags, or releases, push code, or
publish Galaxy artifacts unless explicitly requested. When a commit is requested,
use a Conventional Commit title such as `fix(lists): clear empty memberships` or
`docs: document verified TLS and check mode`, matching the commit-lint workflow.

Release-please runs on `main`, updating release history and `galaxy.yml` through
its configured release process. A published GitHub release triggers the Galaxy
publish workflow. Do not manually bump the version, edit generated release
history, or invoke publishing while implementing an ordinary fix or docs update.
