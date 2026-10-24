"""Shared input and behavior documentation for Pi-hole list modules."""


class ModuleDocFragment:
    DOCUMENTATION = r'''
options:
  lists:
    description:
      - List entries to create, update, or remove in one invocation.
      - Provide this option or O(address). When provided, it takes precedence over all legacy single-entry options.
      - An empty list manages no entries; it does not fall back to O(address).
      - Lists omitted from the batch are not removed or otherwise managed.
    type: list
    elements: dict
    suboptions:
      address:
        description: Feed URL identifying the list.
        type: str
        required: true
      state:
        description:
          - V(present) creates a missing list or updates the specified fields of an existing list.
          - V(absent) removes an existing list and is unchanged if it is already absent.
        type: str
        required: true
        choices: [present, absent]
      comment:
        description:
          - Comment to set when O(lists[].state=present).
          - Omit to preserve an existing comment. An empty string clears the comment.
        type: str
      groups:
        description:
          - Complete desired membership set as group names or integer IDs, not an additive assignment.
          - Names are matched case insensitively. IDs must be unquoted integers; numeric strings are treated as names.
          - Omit to preserve existing memberships, including when another field changes.
          - Specify C([]) to clear all memberships. This is different from omitting the option.
          - A newly created list has no memberships when this option is omitted.
          - Unknown names cause failure before any list writes in the batch; they are never silently discarded.
          - Ignored when O(lists[].state=absent).
        type: list
        elements: raw
      enabled:
        description:
          - Whether the list is enabled when O(lists[].state=present).
          - Defaults to V(true) even for an existing list. Specify V(false) to keep a list disabled.
        type: bool
        default: true
  address:
    description:
      - Feed URL for the legacy single-entry format. Provide this option or O(lists).
      - Requires O(state). Ignored when O(lists) is provided.
    type: str
  state:
    description: Desired state in the single-entry format. See O(lists[].state).
    type: str
    choices: [present, absent]
  comment:
    description: Comment in the single-entry format. See O(lists[].comment).
    type: str
  groups:
    description:
      - Group names or integer IDs in the single-entry format. See O(lists[].groups).
      - Omit to preserve existing memberships; C([]) clears them.
    type: list
    elements: raw
  enabled:
    description: Enabled state in the single-entry format. See O(lists[].enabled).
    type: bool
    default: true
  password:
    description: Pi-hole API password or application password. Its value is hidden from module output.
    type: str
    required: true
  url:
    description:
      - Base URL of the Pi-hole instance, for example C(https://pihole.example.com).
      - Do not append C(/api); the client adds the API path.
    type: str
    required: true
  update_gravity:
    description:
      - Run gravity once after all requested list mutations in this invocation succeed.
      - Runs only if at least one list was added, updated, or deleted; a converged invocation does not run gravity.
      - Never runs in check mode or after a failed batch. A gravity API failure fails the module.
      - Each invocation is independent; this does not coalesce gravity across multiple module tasks.
      - Use O(gravity_timeout) to allow longer-running gravity requests.
    type: bool
    default: false
  gravity_timeout:
    description:
      - Positive request timeout in seconds for gravity when O(update_gravity=true) and a list changes.
      - Does not change the timeout for authentication, list/group reads, list mutations, or logout.
      - Unused when gravity is skipped, including in check mode and on convergence.
      - Uses Requests timeout semantics, not a total runtime deadline; it does not cancel a server-side gravity run.
      - A timeout fails the module but does not roll back earlier successful list changes.
    type: int
    default: 60
attributes:
  check_mode:
    support: full
    description:
      - Authenticates and reads groups and lists to predict additions, deletions, field updates, and membership changes.
      - Reports the same planned action names as normal mode, but skips list writes and gravity.
      - Requires a reachable API and valid credentials; failed reads and unknown group names still fail.
  diff_mode:
    support: none
    description: Does not return an Ansible before/after diff. Inspect RV(result) for per-list actions.
notes:
  - Group and list reads must succeed. A read error or malformed response is not treated as an empty server.
  - Group names for all present entries are resolved before any list mutation. Groups must already exist, including in check mode.
  - HTTP errors, an API C(error) response, and a nonempty C(processed.errors) array fail the module, including on HTTP 200.
  - Batches are not transactions. Earlier successful writes are not rolled back if a later write fails, and RV(changed) remains V(true).
  - Successful per-list responses are in RV(result); failed API response details are in RV(response) and, when available, RV(status_code).
'''
