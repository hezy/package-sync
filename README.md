# Package Sync

Package Sync is a Python script that helps you synchronize packages across multiple machines. It supports synchronizing packages installed via `pipx`, `brew`, and `flatpak`.

## Features

- Designate one machine as the primary machine, and sync packages on other machines to match the primary machine's state.
- Automatically install missing packages and remove extra packages on non-primary machines.
- Update all installed packages across all package managers with a single command.
- Keep track of the last update time for each machine.
- Handle corrupted config files by creating a backup and starting fresh.

## Prerequisites

- Python 3.x
- `pipx` (optional, for synchronizing Python packages)
- `brew` (optional, for synchronizing Homebrew packages)
- `flatpak` (optional, for synchronizing Flatpak packages)

## Installation

1. Clone the repository or download the script file.

2. Make the script executable:
   ```
   chmod +x package_sync.py
   ```

3. (Optional) Add the script to your system's PATH for easier access.

## Usage

Run the script with the following command:

```
./package_sync.py <machine_name> [--primary] [--update]
```

- `<machine_name>`: The name of the current machine. This is used to identify the machine in the configuration file.
- `--primary`: (Optional) Set the current machine as the primary machine. If no primary machine is set, the first machine to run the script will be designated as the primary machine.
- `--update`: (Optional) Update all installed packages across all package managers before performing sync operations.

The script will perform the following actions:

1. If the `--update` flag is provided:
   - Update all `pipx` packages using `pipx upgrade-all`
   - Update all `brew` packages using `brew upgrade`
   - Update all `flatpak` packages using `flatpak update`
2. Load or create the configuration file (`~/.config/package-sync/config.json`).
3. Retrieve the list of installed packages for `pipx`, `brew`, and `flatpak` on the current machine.
4. If the current machine is the primary machine or no primary machine is set, update the configuration file with the current machine's package state.
5. If the current machine is not the primary machine, sync its packages with the primary machine:
   - Install missing packages that are present on the primary machine but not on the current machine.
   - Remove extra packages that are present on the current machine but not on the primary machine.
6. Update the configuration file with the current machine's updated package state.

## Configuration File

The configuration file (`~/.config/package-sync/config.json`) stores the package state for each machine and the designated primary machine. It has the following structure:

```json
{
  "primary_machine": "<primary_machine_name>",
  "machines": {
    "<machine_name>": {
      "packages": {
        "pipx": ["<package1>", "<package2>", ...],
        "brew": ["<package1>", "<package2>", ...],
        "flatpak": ["<package1>", "<package2>", ...]
      },
      "last_update": "<timestamp>"
    },
    ...
  }
}
```

- `primary_machine`: The name of the designated primary machine.
- `machines`: An object containing the package state for each machine.
  - `<machine_name>`: The name of the machine.
    - `packages`: An object containing the list of installed packages for each package manager.
    - `last_update`: The timestamp of the last update for the machine.

If the configuration file becomes corrupted, the script will automatically create a backup of the corrupted file and start fresh with a new configuration file.

## License

This script is released under the [MIT License](LICENSE).