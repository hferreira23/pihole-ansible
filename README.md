# 🍓 pihole-ansible

> **⚠️ NOTICE: Personal Learning Fork**
>
> This is a **personal learning repository** forked from the original project for educational purposes. It is **not intended for production use or public consumption**.
>
> **Original Author:** [Shane Barbetta (@sbarbett)](https://github.com/sbarbett)
> **Original Repository:** [sbarbett/pihole-ansible](https://github.com/sbarbett/pihole-ansible)
>
> **All contributions, issues, and pull requests should be directed to the original repository.**
> This fork exists solely for personal experimentation and learning Ansible collection development.
>
> Full credit and appreciation go to Shane Barbetta for creating and maintaining the original pihole-ansible collection and the [pihole6api](https://github.com/sbarbett/pihole6api) Python library.

---

## Overview

This collection provides Ansible modules and roles for managing PiHole v6 via a custom API client. This collection is built on top of the [pihole6api](https://github.com/sbarbett/pihole6api) Python library developed by Shane Barbetta, which handles authentication and requests.

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

If Ansible is installed via `pipx`, inject `pihole6api` into Ansible’s environment:

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

**Installing for System-Wide Ansible (Generally Not Recommended):**

If Ansible was installed via a package manager (`apt`, `dnf`, `brew`) and a virtual environment or `pipx` is not a feasible or desired solution, run `pip` with `--break-system-packages` to bypass **PEP 668** restrictions:

```bash
sudo pip install --break-system-packages pihole6api
```

Verify installation:

```bash
python3 -c "import pihole6api; print(pihole6api.__file__)"

```

## Usage Examples

All examples reference the original repository for consistency. Refer to the `examples/` directory in this fork or the original repository.

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

* Each module includes embedded documentation accessible via `ansible-doc`:
  ```bash
  ansible-doc sbarbett.pihole.module_name
  # or for this fork:
  ansible-doc hferreira23.pihole.module_name
  ```
* Detailed information for each role is in its respective README file within the `roles/` directory
* For the most up-to-date documentation, refer to the [original repository](https://github.com/sbarbett/pihole-ansible)

## Contributing

**Please direct all contributions to the original repository:**
[https://github.com/sbarbett/pihole-ansible](https://github.com/sbarbett/pihole-ansible)

This fork is for personal learning only and does not accept contributions.

## Credits

**Original Author:** Shane Barbetta ([@sbarbett](https://github.com/sbarbett))
- **pihole-ansible collection:** [sbarbett/pihole-ansible](https://github.com/sbarbett/pihole-ansible)
- **pihole6api Python library:** [sbarbett/pihole6api](https://github.com/sbarbett/pihole6api)

All credit for the design, implementation, and maintenance of this project belongs to Shane Barbetta.

## License

MIT License

See [LICENSE](LICENSE) file for full text.
