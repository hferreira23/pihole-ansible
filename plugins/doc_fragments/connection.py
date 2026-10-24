"""Connection options shared by the collection's Pi-hole modules."""


class ModuleDocFragment:
    DOCUMENTATION = r'''
options:
  validate_certs:
    description:
      - Verify the server certificate and hostname for HTTPS requests.
      - Applies to authentication, API requests, session renewal, and logout.
      - Use O(ca_path) to trust a private CA or a self-signed certificate without disabling verification.
      - Set to V(false) only if you explicitly accept an unverified HTTPS connection.
    type: bool
    default: true
  ca_path:
    description:
      - Path to a PEM CA certificate bundle used to verify the HTTPS server.
      - The file must be readable on the host executing the module, including when using delegation.
      - If omitted, Requests uses its default trust configuration, including E(REQUESTS_CA_BUNDLE) when set.
      - Ignored when O(validate_certs=false). This is not a client certificate or private key.
    type: path
requirements:
  - pihole6api installed in the Python interpreter on the host executing the module
notes:
  - TLS certificate verification is enabled by default, unlike earlier collection versions.
  - TLS options apply only to HTTPS. Use an HTTPS O(url) to protect the API password in transit.
  - The collection uses its own verified transport with the pihole6api endpoint wrappers; it does not modify the installed Python package.
'''
