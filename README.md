# Nice-IT4WIFI to MQTT HomeAssistant AddOn

## Description

This repository contains an AddOn for HomeAssistant that allows integration with Nice IT4WIFI devices via MQTT. This is not an official integration.

## AddOn Installation

You can clone this repository or add it to the online repository in the addon store

IMPORTANT: this addon works only with the gate set up in the "MyNice Welcome" app (not the new "My Nice"). this because only in the old app you can control the new user connecting to your accessory. For android user you can find the apk online given that it was removed from Google Play. I don't know if an equivalent app is available on iPhone (without using HK).

## AddOn Configuration

You need to have a working MQTT broker (you can use HA addon) and the MQTT integration set up in Home Assistant.

As of version `2.0.0` the addon supports **multiple gates**. Each gate is defined as an entry under a `gates:` list. The MQTT settings are global (shared by all gates).

```yaml
# Complete with your broker address (if you use homeassistant addon you can leave the default value)
mqtt_broker: "core-mosquitto"
# Your MQTT broker port
mqtt_port: 1883
# Your MQTT user (This addon works only if you have user and password but it can be changed in future releases if necessary)
mqtt_user: ""
# Your MQTT password
mqtt_pass: ""
# One entry per gate
gates:
  - name: "Front Gate"          # Friendly name shown in Home Assistant
    device_id: "front_gate"     # Unique id used for entities/topics (see note below)
    nice_host: "192.168.1.50"   # IP of the gate (router settings or accessory info in the Nice App)
    nice_mac: "AA:BB:CC:DD:EE:01" # MAC of the gate (printed on the IT4WIFI setup label)
    setup_code: ""              # Setup Code (printed on the IT4WIFI setup label) - needed only for first pairing
    nice_pwd: ""                # Leave empty for first binding, then fill in the password shown in the logs
  - name: "Back Gate"
    device_id: "back_gate"
    nice_host: "192.168.1.51"
    nice_mac: "AA:BB:CC:DD:EE:02"
    setup_code: ""
    nice_pwd: ""
```

Notes on `device_id`:

* It must be **unique** for every gate. If two gates resolve to the same id the addon stops at startup with a clear error.
* It is optional: if omitted it is derived from `name` (lowercased, non-alphanumeric characters become `_`). Setting it explicitly is recommended so renaming a gate later does not orphan its entities.
* When upgrading from a single-gate version, keep one gate as `device_id: "nice_gate_it4wifi"` to preserve your existing Home Assistant device and entities.

> Tip: the `gates` list can be edited in the form of the Configuration tab (use **＋ Add**), but with several gates it is usually easier to use the **⋮ menu → Edit in YAML**.

### Pairing each gate

For every gate that does not yet have a password, leave `nice_pwd` empty, then:

1. Start (or restart) the addon.
2. Open the **Log** tab. For each unpaired gate you will see a line like:
   `[front_gate] Paired. Add this password to the gate's config and restart: <PASSWORD>. Then authorize the 'homeassisstant' user in the NiceWelcome app.`
3. Open your "My Nice Welcome" app and **authorize** the new `homeassisstant` user (the controller rejects the connection until you do).
4. Copy `<PASSWORD>` into that gate's `nice_pwd` and **Save**.
5. **Restart** the addon.

Gates that already have a `nice_pwd` simply connect on start. You can mix paired and unpaired gates freely: an unpaired gate is paired once, logs its password and then stays idle (without disturbing the other gates) until you fill in its password and restart.

After this you will see one MQTT device per gate, each with a cover entity and the command buttons.

# How to authorize user in My Nice Welcome app

Open the app andopen settings (bottom right button). Then select User Management, select your accessory. You should see a request from "homeassistant"

# Recovering from a denied or invalid pairing

If you accidentally **deny** the `homeassisstant` user in the app (or the user is otherwise revoked), that gate will keep failing the connection handshake and retry forever in the logs. The addon does **not** automatically create a new user or prompt again while a password is configured.

To recover, re-trigger pairing for that gate:

1. Set that gate's `nice_pwd` back to empty (`""`) and Save.
2. Restart the addon. It will pair again, log a new password, and raise a fresh authorization request in the app.
3. Approve the request this time, paste the new password into `nice_pwd`, Save and Restart.

Because pairing is isolated per gate, doing this for one gate does not affect your other working gates.

# Possible Bugs

Due to sockets managing of the IT4WIFI could happen that, while your server closes sockets when disconnected, the device is flooded with zombie connection making it unavailble on the wifi. It should be rare (if last bug fixing did not already solve that) but if it happens you can connect your mobile phone via mobile data and restart the device via Nice app or you can restart your router.

# Info

* Currently an integration cannot be developed due to old ssl requirements of the device (which cannot be used in recent python versions like the one for home assistant integration)

* I'm a simple customer and a programmer and I did this addon to use my own gate with Home Assistant, so I tested only commands working with my gate. All the commands available in the app should have been mapped to MQTT. Given that this is not an official addon, I do not promise I will be always available to fix bugs (unless they compromise also my gate) but I'll try to do my best ;)


# Donation
If you enjoy this add-on and want to support my open-source contributions, please consider buying me a coffee.

<a href="https://www.buymeacoffee.com/scama032000">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" >
</a>