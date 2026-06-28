import asyncio
import json
import logging
import os
import re
import signal
import sys
import paho.mqtt.client as mqtt

from nice_driver import NiceGateApi

OPTIONS_PATH = "/data/options.json"

config = {
    "mqtt_broker": os.getenv("MQTT_BROKER", "core-mosquitto"),
    "mqtt_port": int(os.getenv("MQTT_PORT", 1883)),
    "mqtt_user": os.getenv("MQTT_USER", ""),
    "mqtt_pass": os.getenv("MQTT_PASS", ""),
    "nice_host": os.getenv("NICE_HOST", ""),
    "nice_mac": os.getenv("NICE_MAC", ""),
    "setup_code": os.getenv("SETUP_CODE", ""),
    "nice_pwd": os.getenv("NICE_PWD", "")
}

if os.path.exists(OPTIONS_PATH):
    try:
        with open(OPTIONS_PATH, 'r') as f:
            addon_options = json.load(f)
            for key, value in addon_options.items():
                if value is not None:
                    config[key] = value
        logging.info("Loaded configuration from Home Assistant Add-on options.")
    except Exception as e:
        logging.error(f"Error reading options.json: {e}")

MQTT_BROKER = config["mqtt_broker"]
MQTT_PORT = int(config["mqtt_port"])
MQTT_USER = config["mqtt_user"]
MQTT_PASS = config["mqtt_pass"]

if not all([MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS]):
    logging.error("MQTT configuration incomplete. Please provide: mqtt_broker, mqtt_port, mqtt_user, mqtt_pass")
    sys.exit(1)


def slugify(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


# Backward compatibility: translate legacy flat (single-gate) config into a
# one-element 'gates' list. This covers env-var configs and any options.json
# left over from a pre-2.0 install. Keeping device_id = "nice_gate_it4wifi"
# preserves the existing Home Assistant device/entities after upgrade.
if not config.get("gates") and config.get("nice_host"):
    logging.warning(
        "Flat (single-gate) configuration detected; migrated to a one-element "
        "'gates' list. Please switch to the new 'gates' format."
    )
    config["gates"] = [{
        "name": "Gate",
        "device_id": "nice_gate_it4wifi",
        "nice_host": config.get("nice_host", ""),
        "nice_mac": config.get("nice_mac", ""),
        "nice_pwd": config.get("nice_pwd", ""),
        "setup_code": config.get("setup_code", ""),
    }]

raw_gates = config.get("gates") or []
if not raw_gates:
    logging.error("No gates configured. Provide at least one entry under 'gates'.")
    sys.exit(1)

# Normalize and validate every gate before building any connections.
GATE_CONFIGS = []
_seen_ids = set()
for _g in raw_gates:
    _name = (_g.get("name") or "Gate").strip()
    _host = _g.get("nice_host", "")
    _mac = _g.get("nice_mac", "")
    _device_id = _g.get("device_id") or slugify(_name)

    if not all([_host, _mac]):
        logging.error(f"Gate '{_name}' is missing nice_host/nice_mac.")
        sys.exit(1)
    if not _device_id:
        logging.error(f"Gate '{_name}' has no usable device_id (set 'device_id' or a non-empty 'name').")
        sys.exit(1)
    if _device_id in _seen_ids:
        logging.error(f"Duplicate gate device_id '{_device_id}'. Each gate must be unique.")
        sys.exit(1)
    _seen_ids.add(_device_id)

    GATE_CONFIGS.append({
        "name": _name,
        "device_id": _device_id,
        "nice_host": _host,
        "nice_mac": _mac,
        "nice_pwd": _g.get("nice_pwd", "") or "",
        "setup_code": _g.get("setup_code", "") or "",
    })

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)

logger = logging.getLogger("main")

STATUS_MAP = {
    "closed": "closed",
    "open": "open",
    "closing": "closing",
    "opening": "opening",
    "stopped": "open" #stopped does not exists
}

COMMAND_MAP = {
    "STEP_BY_STEP": "MDAx",
    "STOP": "MDAy",
    "OPEN": "MDAz",
    "CLOSE": "MDA0",
    "PARTIAL_1": "MDA1",
    "PARTIAL_2": "MDA2",
    "PARTIAL_3": "MDA3",
    "APARTMENT_STEP": "MDBi",
    "STEP_HIGH_PRIORITY": "MDBj",
    "OPEN_BLOCK": "MDBk",
    "CLOSE_BLOCK": "MDBl",
    "BLOCK": "MDBm",
    "RELEASE": "MDEw",
    "COURTESY_TIMER": "MDEx",
    "COURTESY_TOGGLE": "MDEy",
    "MASTER_DOOR_STEP": "MDEz",
    "MASTER_DOOR_OPEN": "MDE0",
    "MASTER_DOOR_CLOSE": "MDE1",
    "SLAVE_DOOR_STEP": "MDE2",
    "SLAVE_DOOR_OPEN": "MDE3",
    "SLAVE_DOOR_CLOSE": "MDE4",
    "RELEASE_OPEN": "MDE5",
    "RELEASE_CLOSE": "MDFh"
}

EXCLUDE_BUTTON_COMMANDS = ["OPEN", "CLOSE", "STOP"]
ICON_MAP = {
    "STEP_BY_STEP": "mdi:debug-step-over",
    "PARTIAL_1": "mdi:gate-arrow-right",
    "BLOCK": "mdi:lock",
    "RELEASE": "mdi:lock-open",
    "COURTESY_TOGGLE": "mdi:lightbulb"
}

loop = None
mqtt_client = None
gates = []                 # list[Gate]
gates_by_cmd_topic = {}    # { command_topic: Gate } for routing incoming commands


class Gate:
    """Holds everything that used to be global, scoped to a single gate."""

    def __init__(self, name, device_id, host, mac, pwd, setup_code):
        self.name = name
        self.device_id = device_id
        self.host = host
        self.mac = mac
        self.pwd = pwd
        self.setup_code = setup_code

        self.topic_base = f"nice/{device_id}"
        self.topic_cmd = f"{self.topic_base}/set"
        self.topic_state = f"{self.topic_base}/state"
        self.topic_avail = f"{self.topic_base}/availability"

        self.api = NiceGateApi(
            host,
            mac,
            pwd,
            on_status_callback=lambda status, g=self: nice_status_callback(g, status),
        )


def publish_gate_discovery(client, gate):
    """Subscribe to a gate's command topic and publish its HA discovery payloads."""
    client.subscribe(gate.topic_cmd)

    device_block = {
        "identifiers": [gate.device_id],
        "name": gate.name,
        "manufacturer": "Nice",
        "model": "IT4WIFI"
    }

    cover_config = {
        "name": gate.name,
        "unique_id": f"{gate.device_id}_cover",
        "device_class": "gate",
        "command_topic": gate.topic_cmd,
        "state_topic": gate.topic_state,
        "availability_topic": gate.topic_avail,
        "payload_open": "OPEN",
        "payload_close": "CLOSE",
        "payload_stop": "STOP",
        "device": device_block
    }
    client.publish(f"homeassistant/cover/{gate.device_id}/config", json.dumps(cover_config), retain=True)

    for command_key in COMMAND_MAP:
        if command_key in EXCLUDE_BUTTON_COMMANDS:
            continue

        readable_name = command_key.replace("_", " ").title()
        safe_slug = command_key.lower()

        button_config = {
            "name": f"{readable_name}",
            "unique_id": f"{gate.device_id}_btn_{safe_slug}",
            "command_topic": gate.topic_cmd,
            "payload_press": command_key,
            "availability_topic": gate.topic_avail,
            "icon": ICON_MAP.get(command_key, "mdi:gesture-tap-button"),
            "device": device_block
        }
        topic_config = f"homeassistant/button/{gate.device_id}_{safe_slug}/config"
        client.publish(topic_config, json.dumps(button_config), retain=True)
        logger.info(f"[{gate.device_id}] Published discovery for button: {readable_name}")

    client.publish(gate.topic_avail, "online", retain=True)


def on_mqtt_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        logger.info(f"Connected to MQTT Broker successfully (Code: {reason_code})")
        for gate in gates:
            publish_gate_discovery(client, gate)
    else:
        logger.error(f"Failed to connect to MQTT Broker. Reason code: {reason_code}")


def on_mqtt_message(client, userdata, msg):
    gate = gates_by_cmd_topic.get(msg.topic)
    if not gate:
        logger.warning(f"Received command on unknown topic: {msg.topic}")
        return

    payload = msg.payload.decode().upper()
    logger.info(f"[{gate.device_id}] Received MQTT command: {payload}")

    if loop:
        command_code = COMMAND_MAP.get(payload)
        if command_code:
            coro = gate.api.t4(command_code)
            asyncio.run_coroutine_threadsafe(coro, loop)
        else:
            logger.warning(f"[{gate.device_id}] Unknown command: {payload}")


def nice_status_callback(gate, status):
    """Called when a gate's status changes."""
    logger.info(f"[{gate.device_id}] Nice Callback Status Raw: '{status}'")

    status_clean = str(status).strip() if status else "unknown"
    ha_status = STATUS_MAP.get(status_clean, "unknown")

    if ha_status == "unknown":
        logger.warning(f"[{gate.device_id}] Status '{status_clean}' not found in STATUS_MAP. Available: {list(STATUS_MAP.keys())}")
        ha_status = status_clean.lower()

    if mqtt_client:
        mqtt_client.publish(gate.topic_state, ha_status, retain=True)


async def main():
    global loop, mqtt_client
    loop = asyncio.get_running_loop()

    for gc in GATE_CONFIGS:
        gate = Gate(
            gc["name"],
            gc["device_id"],
            gc["nice_host"],
            gc["nice_mac"],
            gc["nice_pwd"],
            gc["setup_code"],
        )
        gates.append(gate)
        gates_by_cmd_topic[gate.topic_cmd] = gate

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    if MQTT_USER:
        mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)

    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_message = on_mqtt_message

    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        logger.error(f"Failed to connect to MQTT: {e}")
        return

    logger.info(f"Initializing {len(gates)} gate(s)...")
    for gate in gates:
        if gate.pwd:
            # Configured gate — runs independently in its own supervisor loop.
            logger.info(f"[{gate.device_id}] Starting (host={gate.host})...")
            await gate.api.start()
        else:
            # Unpaired gate — ONE-SHOT pairing attempt, then leave it idle.
            # Do NOT call start(): a blank password would crash the signed STATUS
            # command and retry-loop forever.
            logger.info(f"[{gate.device_id}] No password set; attempting one-shot pairing...")
            paired = await gate.api.pair(gate.setup_code)
            if paired:
                logger.warning(
                    f"[{gate.device_id}] Paired. Add this password to the gate's config and "
                    f"restart: {paired}. Then authorize the 'homeassisstant' user in the "
                    f"NiceWelcome app."
                )
            else:
                logger.error(f"[{gate.device_id}] Pairing failed; gate will stay idle.")
            # No start(), no retry — gate stays idle until configured and restarted.

    try:
        while True:
            await asyncio.sleep(3600)

    except asyncio.CancelledError:
        logger.info("Stopping...")
    finally:
        for gate in gates:
            await gate.api.close()
            mqtt_client.publish(gate.topic_avail, "offline")
        mqtt_client.loop_stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
