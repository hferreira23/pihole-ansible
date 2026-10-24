# Pi-hole examples

These playbooks target a Pi-hole v6 API and use the `hferreira23.pihole` collection. Install the collection and its `pihole6api` dependency before running them. The reserved `example.com` list addresses and documentation-only client networks are placeholders; replace them with values appropriate for your Pi-hole.

Put connection values in inventory/group vars or an Ansible Vault-encrypted file, never in the playbook:

```yaml
# vault.yml (encrypt this file with ansible-vault)
pihole_url: https://pihole.example.net
pihole_password: "your-api-password"
# Optional: pihole_validate_certs: true
# Optional private CA bundle on the machine running the local play:
# pihole_ca_path: /etc/ssl/certs/pihole-ca.pem
```

Run a playbook with:

```sh
ansible-playbook -i localhost, -e @vault.yml --ask-vault-pass examples/manage-block-lists.yml
```

The management, preview, and error-handling plays use `connection: local` and the
same Python interpreter as `ansible-playbook`; install `pihole6api` there. A
configured `ca_path` must therefore exist on the controller. For delegated tasks
in your own playbooks, it must exist on the delegated host instead.

Certificate validation is enabled for authentication and every HTTPS API request.
Requests uses its default trust configuration unless you supply `pihole_ca_path`
or configure `REQUESTS_CA_BUNDLE`. Prefer a trusted CA bundle over setting
`pihole_validate_certs: false`, which explicitly disables verification. HTTPS is
still required to encrypt the password; certificate options do not secure HTTP.

## List behavior

`manage-block-lists.yml` and `manage-allow-lists.yml` batch present/update/absent operations. The `groups` field behaves as follows:

| Input | Existing list | New list |
| --- | --- | --- |
| Omitted | Preserve current memberships during other field updates | Created with no memberships |
| `groups: []` | Clear all memberships | Created with no memberships |
| `groups: [Default]` or `groups: [0]` | Set the listed memberships | Set the listed memberships |

Names resolve case-insensitively; unquoted integers are group IDs, while `"0"`
is a name. Unknown group names fail before any list writes in the batch.
Omitting `comment` preserves an existing comment; `comment: ""` clears it.
Unlike `groups`, `enabled` defaults to `true` even for existing lists; specify
`enabled: false` when updating a list that must remain disabled.

Gravity runs only after a successful batch containing actual list changes, at
most once per module invocation—not once for the whole playbook. It does not run
on convergence, in check mode, or after a failed batch. Re-running a management
playbook with the same desired state should report no list changes or gravity run.

`preview-list-changes.yml` sets `check_mode: true` on the **task** and displays
predicted actions without list writes or gravity. Authentication and reads still
need a reachable API, working credentials, and valid group names. It does not
return an Ansible before/after diff.

```sh
# Preview only, regardless of whether --check is passed:
ansible-playbook -i localhost, -e @vault.yml --ask-vault-pass examples/preview-list-changes.yml

# Preview the same management task you intend to apply:
ansible-playbook -i localhost, -e @vault.yml --ask-vault-pass examples/manage-block-lists.yml --check

# Apply it, then run again to check convergence:
ansible-playbook -i localhost, -e @vault.yml --ask-vault-pass examples/manage-block-lists.yml
```

Both batch `lists:` and legacy `address:`/`state:` formats remain supported.
Batch entries omitted from `lists` are left alone, and `lists: []` manages nothing.

## Groups, clients, and errors

Create custom groups with `manage-groups.yml` before assigning their names in `manage-clients.yml` or a list. Alternatively, use already-existing group names/IDs. In check mode, a group creation is only predicted, so a later task that reads/resolves that newly named group cannot use it yet: provision missing groups first or reference existing IDs.

The clients module treats an omitted `groups` field as its default `[]`; unlike list updates, omission does not preserve existing client memberships. Provide the desired groups explicitly when updating clients. The group examples only manage custom groups and do not delete Pi-hole's built-in `Default` group.

API errors fail automatically; no custom `failed_when` is needed. This includes
HTTP errors, API `error` responses, and `processed.errors` inside HTTP 200
responses. Returned `response` retains server details; `status_code` is included
when available and may be 200 for an API-level rejection.

`list-api-errors.yml` demonstrates a normal write with `block`/`rescue`: if the
write fails, it displays `ansible_failed_result`, then fails again so the error is
not suppressed. The placeholder URL does **not** guarantee rejection; adapt the
request to reproduce your failure. Batches are not transactions: earlier writes
can remain applied, and `changed: true` on a failed task means prior changes
were made, not that the failed write succeeded.

## Module help

```sh
ansible-doc hferreira23.pihole.block_list
ansible-doc hferreira23.pihole.allow_list
ansible-doc --snippet hferreira23.pihole.block_list
ansible-doc --json hferreira23.pihole.block_list
```

`--snippet` currently emits a short module name. Qualify the generated task key
as `hferreira23.pihole.block_list` to select this fork unambiguously.

The help includes shared TLS options, nested batch options, check-mode support,
examples, and per-action and failure return values. These are tested from the
built collection, along with syntax and module options for every example playbook.
