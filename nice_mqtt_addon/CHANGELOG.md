# Changelog

## 2.0.1

### Fixed
- Fixed doubled entity names in Home Assistant (e.g. "Gate Gate"). The cover is now the device's main entity, so it shows just the gate name.
- `nice_mac` is now uppercased automatically (the IT4WIFI rejects a lowercase MAC), so either case works in the config.

### Changed
- Driver log lines are now prefixed with the gate id (e.g. `nicegate.front_gate`) so multi-gate logs are attributable to a specific gate.
- Trimmed duplicate/noisy log lines.

### Documentation
- Clarified that `setup_code` must be entered exactly as printed, dashes included (e.g. `123-12-123`), and that MAC/setup code are per-device — never copy them between gates.

## 2.0.0

Multi-gate release. **Breaking change: the configuration format has changed.**

### Added
- Support for **multiple gates** from one add-on instance, defined as a list under `gates:` (each with its own `name`, `device_id`, `nice_host`, `nice_mac`, `setup_code`, `nice_pwd`). Each gate becomes its own Home Assistant device with independent MQTT topics.
- Isolated per-gate pairing: an unpaired gate is paired once (password logged) then left idle, without disrupting gates that are already running.
- Startup validation: empty `gates`, missing `nice_host`/`nice_mac`, or duplicate `device_id` fail fast with a clear error.
- Auto-migration of a legacy single-gate config into a one-element `gates` list (keeps `device_id: nice_gate_it4wifi` to preserve existing entities).

### Changed
- **BREAKING:** the flat `nice_host` / `nice_mac` / `setup_code` / `nice_pwd` options are replaced by the `gates:` list. Move your gate settings into the new format (see README).
- The extra T4 command buttons (Block, Partial, Courtesy, Master/Slave door, etc.) are **no longer exposed by default** — each gate shows only the Gate cover (open/stop/close). Set `expose_extra_buttons: true` on a gate to publish them.

## 1.0.7

### Changed
- Added buttons for all T4 commands in MQTT discovery
