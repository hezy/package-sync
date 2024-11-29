#!/usr/bin/env python3
import json
import subprocess
import os
from pathlib import Path
from datetime import datetime
import argparse
import shutil

CONFIG_PATH = Path("~/.config/package-sync/config.json").expanduser()


def load_config():
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                return json.load(f)
        except json.JSONDecodeError:
            backup_path = CONFIG_PATH.with_suffix(".json.bak")
            print(f"Config file corrupted. Backing up to {backup_path}")
            shutil.copy(CONFIG_PATH, backup_path)

    config = {"primary_machine": None, "machines": {}, "last_changes": {}}
    save_config(config)
    return config


def sets_to_lists(obj):
    if isinstance(obj, dict):
        return {key: sets_to_lists(value) for key, value in obj.items()}
    elif isinstance(obj, set):
        return sorted(list(obj))
    return obj


def save_config(config):
    config_copy = sets_to_lists(config)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config_copy, f, indent=2, sort_keys=True)


def get_pipx_packages():
    try:
        result = subprocess.run(
            ["pipx", "list", "--json"], capture_output=True, text=True
        )
        if result.returncode != 0:
            return set()
        return set(json.loads(result.stdout)["venvs"].keys())
    except FileNotFoundError:
        return set()


def get_brew_packages():
    try:
        result = subprocess.run(
            ["brew", "list", "--formula"], capture_output=True, text=True
        )
        if result.returncode != 0:
            return set()
        return set(result.stdout.strip().split("\n"))
    except FileNotFoundError:
        return set()


def get_flatpak_packages():
    try:
        result = subprocess.run(
            ["flatpak", "list", "--app", "--columns=application"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return set()
        packages = result.stdout.strip().split("\n")
        return set(pkg for pkg in packages if pkg)
    except FileNotFoundError:
        return set()


def install_package(pkg_type, package):
    if pkg_type == "pipx":
        cmd = ["pipx", "install", package]
    elif pkg_type == "brew":
        cmd = ["brew", "install", package]
    elif pkg_type == "flatpak":
        cmd = ["flatpak", "install", "-y", package]

    print(f"Installing {pkg_type} package: {package}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Failed to install {package}: {result.stderr}")
        return False
    return True


def remove_package(pkg_type, package):
    if pkg_type == "pipx":
        cmd = ["pipx", "uninstall", package]
    elif pkg_type == "brew":
        cmd = ["brew", "uninstall", package]
    elif pkg_type == "flatpak":
        cmd = ["flatpak", "uninstall", "-y", package]

    print(f"Removing {pkg_type} package: {package}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Failed to remove {package}: {result.stderr}")
        return False
    return True


def get_all_packages():
    return {
        "pipx": get_pipx_packages(),
        "brew": get_brew_packages(),
        "flatpak": get_flatpak_packages(),
    }


def print_package_state(machine_name, packages):
    print(f"\nPackages for {machine_name}:")
    for pkg_type in sorted(["pipx", "brew", "flatpak"]):
        pkgs = packages.get(pkg_type, set())
        if pkgs:
            print(f"{pkg_type:8} ({len(pkgs):2}): {', '.join(sorted(pkgs))}")


def sync_packages(machine_name, make_primary=False):
    config = load_config()
    current_packages = get_all_packages()

    print("\nCurrent machine state:")
    print_package_state(machine_name, current_packages)

    # Handle primary machine designation
    if make_primary or config["primary_machine"] is None:
        config["primary_machine"] = machine_name
        print(f"\nSetting {machine_name} as primary machine")

    print(f"\nPrimary machine is: {config['primary_machine']}")

    # If this is a new machine or we're updating the primary machine
    if (
        machine_name not in config["machines"]
        or machine_name == config["primary_machine"]
    ):
        config["machines"][machine_name] = {
            "packages": current_packages,
            "last_update": datetime.now().isoformat(),
        }
        save_config(config)
        print(f"\nUpdated state for {machine_name}")
        return

    # For non-primary machines, sync with primary
    primary_packages = config["machines"][config["primary_machine"]]["packages"]
    changes_made = False

    print("\nSyncing with primary machine...")
    for pkg_type in ["pipx", "brew", "flatpak"]:
        current = set(current_packages.get(pkg_type, []))
        primary = set(primary_packages.get(pkg_type, []))

        # Install missing packages
        to_install = primary - current
        if to_install:
            print(f"\nInstalling missing {pkg_type} packages:")
            for package in sorted(to_install):
                if install_package(pkg_type, package):
                    changes_made = True

        # Remove extra packages
        to_remove = current - primary
        if to_remove:
            print(f"\nRemoving extra {pkg_type} packages:")
            for package in sorted(to_remove):
                if remove_package(pkg_type, package):
                    changes_made = True

    if changes_made:
        current_packages = get_all_packages()

    # Update state
    config["machines"][machine_name] = {
        "packages": current_packages,
        "last_update": datetime.now().isoformat(),
    }
    save_config(config)

    print("\nFinal state:")
    print_package_state(machine_name, current_packages)


def main():
    parser = argparse.ArgumentParser(
        description="Sync packages across machines"
    )
    parser.add_argument("machine_name", help="Name of this machine")
    parser.add_argument(
        "--primary", action="store_true", help="Set this machine as primary"
    )
    args = parser.parse_args()
    sync_packages(args.machine_name, args.primary)


if __name__ == "__main__":
    main()
