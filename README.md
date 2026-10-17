# UniFi Guardian

A Home Assistant integration that recognizes a Windows PC by its discovery UUID
and blocks or unblocks it through UniFi—even after MAC changes, if the UUID stays
available. No PC agent or Wi-Fi password changes needed.

## Install

1. In **HACS → ⋮ → Custom repositories**, add
   `https://github.com/dgageot/ha-unifi-guardian` as an **Integration**.
2. Download **UniFi Guardian** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → UniFi Guardian**.
4. Enter your UniFi host, port (usually `443`), and a **local account with Network
   management permissions**. Keep TLS verification enabled unless your trusted
   console uses a self-signed certificate.
5. Select your site and awake PC, then confirm its discovered UUID.

Requires Home Assistant **2026.10.1+** and access to the PC’s Windows discovery
service (UDP 3702). Setup does not block anything.

## Use

Add **Block PC** and **Enforcement** to your dashboard:

- **On:** request blocking of the PC’s recognized MAC addresses.
- **Off:** release blocks created by Guardian.
- **Enforcement:** check whether UniFi confirmed the request.

Guardian checks every 15 seconds and remembers identities and requests across
restarts. The same switch can be used in bedtime automations.

## Limitations

**Experimental, not tamper-proof.** Discovery can be disabled, changed, or
spoofed; a new MAC may get access before recognition. Test block/unblock and
recognition after a MAC change before relying on it.

Avoid managing the same blocks elsewhere. **Unblock before removing the
integration**—blocks remain in UniFi if Guardian stops. Use UniFi’s **Unblock
client** action for manual recovery.
