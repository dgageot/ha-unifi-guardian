# UniFi Guardian (experimental)

A standalone Home Assistant custom integration that recognizes a Windows PC by
its WS-Discovery endpoint UUID and uses UniFi's **Block client / Unblock client**.
No existing UniFi integration, YAML helpers, PC agent, or Wi-Fi password change.

## Installation and setup

### HACS (requires a public repository)

In HACS, open the three-dot menu → **Custom repositories**. Add:

```text
https://github.com/dgageot/ha-unifi-guardian
```

Select **Integration**, add the repository, then find **UniFi Guardian** and
install it. Restart Home Assistant, then follow the setup steps below.
This is a custom repository, not an entry in HACS's default catalog.

### Manual installation (also works while the repository is private)

Download the source ZIP from GitHub while signed in. Copy
`custom_components/unifi_guardian` into `/config/custom_components/` on Home
Assistant Green, then restart Home Assistant.

### Setup

1. Ensure the PC is awake and Windows discovery is reachable from Home Assistant.
2. Add **UniFi Guardian** under Settings → Devices & services → Add integration.
3. Enter the console host (without `https://`), port (usually 443), and a dedicated
   local UniFi account with Network management permission. SSO is not supported.
   TLS verification defaults to enabled; disable only for a trusted console with
   a self-signed certificate. Credentials stay in Home Assistant's config-entry
   storage; protect your configuration and backups.
4. Choose the site, then an awake Wi-Fi client. Setup queries that client's
   WS-Discovery service and asks you to confirm its UUID. Nothing is blocked
   during setup. If discovery fails, setup cannot enroll the PC.
5. Add the **Block PC** switch and **Enforcement** sensor to your dashboard.
   Switch ON means blocking requested, OFF means release Guardian-owned blocks.
   Use the same switch in a bedtime automation if desired.

The switch persists your *requested* state. The sensor independently reports
controller confirmation for known MACs, not a guarantee that every possible
identity is blocked. Communication failures make the sensor unavailable.

## Recognition and safety

Every 15 seconds, Guardian polls UniFi and probes active Wi-Fi clients using
unicast UDP 3702. Green must reach that service on the PC. It never follows
advertised metadata URLs or treats hostnames/IP addresses as identity. A matching
UUID is checked against a fresh UniFi IP-to-MAC mapping before enrollment.

Confirmed MACs and requested blocking survive restarts. Block ownership is
journaled before sending commands so an interrupted command can be reconciled.
Existing blocks are left alone. UniFi has no per-client block ownership: avoid
simultaneously managing the same blocks elsewhere; another admin's later block
cannot always be distinguished from Guardian's. Missing client records are
reported as pending, not silently treated as success.

**Not tamper-proof.** UUID stability across MAC changes is not yet verified for
your PC. Discovery identifiers are unauthenticated and can disappear, reset, or
be spoofed. MAC spoofing can defeat identification or impersonate a known client.
New identities can get access before detection. If discovery is disabled, a new
MAC can go undetected. Historical MACs stay associated with the PC; do not reuse
those addresses for other devices. Only recognized clients are blocked, never
all unknown devices. This does not control cellular or other networks.

Start with the switch OFF and observe recognition over a natural MAC change.
Then perform an attended block/unblock test. A PC disappearing after blocking
is expected; Guardian keeps its mapping so it can unblock it while unreachable.

**Before disabling/removing the integration, turn the switch OFF and verify the
sensor.** Removal does not silently unblock clients. If Green is down, blocks
remain in UniFi; use UniFi's client Unblock action for manual recovery. If config
storage is lost, restore a backup or manually unblock the recorded clients.

This is an experimental integration. Compatibility and real blocking must be
validated on your console before unattended use. Tested with Home Assistant
2026.10.1; earlier versions are not currently declared supported.

## Development

Use Python 3.14 and the dependencies in `requirements-dev.txt`.
Run `pytest`, `ruff check .`, and `ruff format --check .`.
Tests use fake UniFi clients; they never block real devices.
