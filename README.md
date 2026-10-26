# 🍓 pihole-ansible

> **⚠️ NOTICE: Personal Learning Fork**
>
> This is a **personal learning repository** forked from the original project for educational purposes. It is **not intended for production use or public consumption**.
>
> **Original Author:** [Shane Barbetta (@sbarbett)](https://github.com/sbarbett)
> **Original Repository:** [sbarbett/pihole-ansible](https://github.com/sbarbett/pihole-ansible)
>
> For changes to the maintained upstream project, use the original repository.
> For changes to this learning fork, follow [CONTRIBUTING.md](CONTRIBUTING.md).
>
> Full credit and appreciation go to Shane Barbetta for creating and maintaining the original pihole-ansible collection and the [pihole6api](https://github.com/sbarbett/pihole6api) Python library.

---

[![Galaxy Publish](https://github.com/hferreira23/pihole-ansible/actions/workflows/galaxy-publish.yml/badge.svg)](https://github.com/hferreira23/pihole-ansible/actions/workflows/galaxy-publish.yml)
[![Semantic Version Release](https://github.com/hferreira23/pihole-ansible/actions/workflows/sem-ver-release.yml/badge.svg)](https://github.com/hferreira23/pihole-ansible/actions/workflows/sem-ver-release.yml)
[![Commit Lint](https://github.com/hferreira23/pihole-ansible/actions/workflows/commit-lint.yml/badge.svg)](https://github.com/hferreira23/pihole-ansible/actions/workflows/commit-lint.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Overview

This collection provides Ansible modules for managing Pi-hole v6. It reuses the
endpoint wrappers from Shane Barbetta's
[pihole6api](https://github.com/sbarbett/pihole6api) library with a collection-owned
transport for verified TLS, authentication, and API error handling. Historical
roles remain in this repository but are excluded from the Galaxy artifact.

This collection includes:

**Modules:**
- `local_a_record`: Manage local A records
- `local_aaaa_record`: Manage local AAAA records (IPv6)
- `local_cname`: Manage local CNAME records
- `dhcp_config`: Enable, disable, and configure the DHCP server
- `dhcp_remove_lease`: Delete existing DHCP leases
- `listening_mode`: Configure PiHole's DNS listening mode
- `block_list`: Manage block lists with batch processing
- `allow_list`: Manage allow lists with batch processing
- `domains`: Manage individual exact/regex whitelist and blacklist entries (the Domains tab)
- `groups`: Manage PiHole groups
- `clients`: Manage PiHole clients

## Getting Started

### Prerequisites

- **Ansible:** ansible-core 2.19.0+
- **Python:** 3.13+ on the control node
- **pihole6api Library:** Required Python dependency

### Installation

```bash
ansible-galaxy collection install hferreira23.pihole
```

**Note:** For the original, maintained version, install from the original author's Galaxy namespace:

```bash
ansible-galaxy collection install sbarbett.pihole
```

To build this fork locally (for learning purposes only):

```bash
git clone https://github.com/YOUR-FORK/pihole-ansible
cd pihole-ansible
ansible-galaxy collection build
ansible-galaxy collection install hferreira23-pihole-*.tar.gz
```

#### `pihole6api` Dependency

The `pihole6api` Python library (developed by Shane Barbetta) is required for this Ansible collection to function. Installation method depends on your Ansible setup.

**Basic Installation:**

```bash
pip install pihole6api
```

**Note:** Some Linux distributions (Debian, macOS, Fedora, etc.) restrict system-wide `pip` installs due to [PEP 668](https://peps.python.org/pep-0668/). Use one of the methods below in such cases.

**Installing in a Virtual Environment (Recommended):**

If you want an isolated environment that won't interfere with system-wide packages, install both `pihole6api` and Ansible in a virtual environment:

```bash
python -m venv venv
source venv/bin/activate
pip install pihole6api ansible
```

To confirm that `ansible` and `pihole6api` are installed correctly within the environment, run:

```bash
which python && which ansible
python -c "import pihole6api; print(pihole6api.__file__)"
```

To exit the virtual environment:

```bash
deactivate
```

**Using `pipx`:**

If Ansible is installed via `pipx`, inject `pihole6api` into Ansible's environment:

```bash
pipx inject ansible pihole6api --include-deps
```

Verify installation:

```bash
pipx runpip ansible show pihole6api
```

Since Ansible does not automatically detect `pipx` environments, you must explicitly set the Python interpreter in your Ansible configuration:

Edit `ansible.cfg`:

```
[defaults]
interpreter_python = ~/.local/pipx/venvs/ansible/bin/python
```

For more information on `pipx` see [the official documentation](https://github.com/pypa/pipx) and [the Ansible install guide](https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html).

**Distribution-managed Python:** Do not bypass PEP 668 protections or install
development dependencies with system-wide `sudo pip`. Use a virtual environment
or the `pipx` approach above, and point Ansible's module interpreter at the
environment containing `pihole6api`.

## Usage Examples

### Individual whitelist and blacklist domains

Use `hferreira23.pihole.domains` for the web UI's **Domains** tab. The existing
`allow_list` and `block_list` modules manage feed subscriptions instead.

```yaml
- name: Manage individual domain rules
  hferreira23.pihole.domains:
    url: "{{ pihole_url }}"
    password: "{{ pihole_password }}"
    domains:
      - domain: allowed.example.com
        type: allow
        groups: [Default]
      - domain: '(^|\.)ads\.example\.com$'
        type: deny
        kind: regex
        groups: [0]
      - domain: obsolete.example.com
        type: deny
        state: absent
```

`type` is `allow` (whitelist) or `deny` (blacklist); `kind` defaults to `exact`,
and `state` to `present`. Each `(domain, type, kind)` is independent. Unlisted
entries remain untouched; duplicate identities are rejected. To move an entry,
explicitly remove the old identity and add the new one.

For existing domains, omitted/null `comment`, `groups`, and `enabled` preserve
current values. Use `comment: ""` or `groups: []` to clear those fields. Cleared
comments are normalized to `null`, matching Pi-hole's response. New
entries default to no comment, no group memberships, and enabled. Assign groups
explicitly for a rule to apply to those groups. Integer IDs remain integers;
numeric strings are names. Unknown names and malformed reads fail before writes.

Check mode authenticates and reads but never writes. Regex syntax is validated
by Pi-hole on actual writes, not during preview. No gravity run is needed or
performed. A failed batch retains earlier successful changes, without rollback.
TLS verification remains enabled from authentication onward. See
[`examples/manage-domains.yml`](examples/manage-domains.yml) and
`ansible-doc hferreira23.pihole.domains` for complete usage and returns.

### List reconciliation and TLS

`block_list` and `allow_list` support check mode for additions, deletions,
field updates, and group membership updates. For existing lists, omitting
`groups` preserves memberships; specifying `groups: []` clears them. Both batch
and legacy single-list inputs accept group names or integer IDs. Unknown group
names and failed reads stop the module rather than applying partial assignments.
New lists with omitted `groups` have no memberships.

HTTP errors, API `error` responses, and nonempty `processed.errors` fail the
module, with structured details in `response` and, when available, `status_code`.
An API rejection can have `status_code: 200`. Earlier successful operations in a failed batch still report
`changed: true`. `update_gravity: true` runs gravity once after a successful
batch with actual list changes, never on convergence or in check mode.

Both list modules accept `gravity_timeout` as a positive integer in seconds
(default: `60`). Set it higher for larger gravity runs. It applies only to the
gravity request; authentication, normal reads/writes, and logout retain their
normal timeout. A timeout fails the task without rolling back earlier changes
or cancelling server-side gravity. This is a Requests timeout, not a total
runtime deadline.

All modules verify TLS certificates **including authentication**, using a
collection-owned transport with the `pihole6api` endpoint wrappers. This does
not modify the separately installed Python package. For a private CA, set
`ca_path` to a PEM CA bundle on the managed host. To explicitly accept an
unverified self-signed certificate, set `validate_certs: false` (not recommended).
This secure default changes the previous unverified-HTTPS behavior.

```yaml
- name: Clear list memberships with a private CA
  hferreira23.pihole.block_list:
    url: https://pihole.example.com
    password: "{{ pihole_password }}"
    ca_path: /etc/ssl/certs/private-ca.pem
    address: https://example.com/hosts.txt
    state: present
    groups: []
    update_gravity: true
```

See the [examples guide](examples/README.md) for runnable playbooks, Vault-based
credentials, membership semantics, check-mode previews, and failure handling.

### Modules

* [Enable and Configure the PiHole DHCP Server](examples/configure-dhcp-client.yml)
* [Disable the PiHole DHCP Server](examples/disable-dhcp-client.yml)
* [Remove a DHCP Lease](examples/remove-dhcp-lease.yml)
* [Create a Local A Record](examples/create-a-record.yml)
* [Remove a Local A Record](examples/delete-a-record.yml)
* [Create a Local CNAME](examples/create-cname.yml)
* [Remove a Local CNAME](examples/delete-cname.yml)
* [Manage Allow Lists](examples/manage-allow-lists.yml)
* [Manage Block Lists](examples/manage-block-lists.yml)
* [Manage Groups](examples/manage-groups.yml)
* [Manage Clients](examples/manage-clients.yml)
* [Change Listening Mode](examples/change-listening-mode.yml)

## Documentation

After installing this collection, use its fully qualified module names:

```bash
ansible-doc hferreira23.pihole.block_list
ansible-doc hferreira23.pihole.allow_list
ansible-doc hferreira23.pihole.groups
ansible-doc hferreira23.pihole.clients

# Generate a task skeleton or machine-readable documentation:
ansible-doc --snippet hferreira23.pihole.block_list
ansible-doc --json hferreira23.pihole.block_list
```

Ansible currently emits short module names in `--snippet` output. Change the
generated task key to `hferreira23.pihole.block_list` before using it, so Ansible
selects this fork rather than another collection's module.

List-module help documents every nested batch option, legacy single-entry
options, TLS trust settings, check-mode predictions, gravity behavior, and return
values. In particular:

- `groups` omitted preserves existing **list** memberships; `groups: []` clears
  them. Client memberships still default to `[]` when omitted.
- For groups and clients, omitted or null `comment` preserves an existing comment
  during updates; `comment: ""` clears it.
- `enabled` defaults to `true`; explicitly pass `false` to keep a list disabled.
- Check mode authenticates and reads current state, but skips list writes and
  gravity. Groups referenced by name must already exist, even if an earlier
  check-mode task predicted their creation.
- A failed batch is not rolled back. Its `result` contains earlier completed list
  actions, and its top-level `response` retains available API error details.
- `result[].action` names are also used for predictions in check mode; a predicted
  `added`, `updated`, or `deleted` action does not mean a write occurred.

The [examples guide](examples/README.md) shows complete playbooks and safe ways
to preview them. Role-specific documentation remains under `roles/`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete local development,
validation, and documentation workflow. AI agents should start with
[AGENTS.md](AGENTS.md).

Run the regression suite locally with:

```bash
python -m venv .venv
.venv/bin/pip install -r tests/requirements.txt
.venv/bin/python -m pytest -q
```

Tests use mocked Pi-hole API responses and a temporary loopback HTTPS server;
no running Pi-hole instance is required. Documentation tests build and install
the collection into a temporary directory, exercise text and JSON `ansible-doc`
output for the new features, compare list options with the argument specification,
and syntax-check the example playbooks. CI defaults to the latest stable
ansible-core on supported Python 3.14, explicitly upgraded on every test run;
there is no older-version compatibility job. Draft PRs and changes limited to
guides, historical roles, or unrelated automation skip the expensive tests.
Relevant PRs run validation; pushes to `main` or feature branches do not rerun it.
Explicit manual dispatch remains available and always runs validation.
The required test check is still reported for skipped changes. JUnit reports are
retained for 14 days.

For contributions to the maintained upstream collection, use:
[https://github.com/sbarbett/pihole-ansible](https://github.com/sbarbett/pihole-ansible)

This fork remains a personal learning project. The local contribution workflow
does not imply production support or authorization to publish releases.

## Credits

**Original Author:** Shane Barbetta ([@sbarbett](https://github.com/sbarbett))
- **pihole-ansible collection:** [sbarbett/pihole-ansible](https://github.com/sbarbett/pihole-ansible)
- **pihole6api Python library:** [sbarbett/pihole6api](https://github.com/sbarbett/pihole6api)

All credit for the design, implementation, and maintenance of this project belongs to Shane Barbetta.

## License

MIT License

See [LICENSE](LICENSE) file for full text.
