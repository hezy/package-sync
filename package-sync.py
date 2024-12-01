#!/usr/bin/env python3
import json
import subprocess
import os
from pathlib import Path
from datetime import datetime
import argparse
import shutil

CONFIG_PATH = Path("~/.config/package-sync/config.json").expanduser()


def check_internet_connection(hosts=None):
    """
    Check internet connectivity by pinging multiple reliable hosts.
    
    Args:
        hosts: List of hosts to check. Defaults to well-known reliable servers
        
    Returns:
        tuple: (is_connected, latency) where:
            - is_connected is True if at least one host responds
            - latency is the best response time in milliseconds, or None if all failed
    """
    if hosts is None:
        hosts = [
            "8.8.8.8",          # Google DNS
            "1.1.1.1",          # Cloudflare DNS
            "208.67.222.222",   # OpenDNS
        ]
    
    best_latency = None
    for host in hosts:
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", host],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                # Extract time from ping output
                try:
                    time_str = result.stdout.split("time=")[1].split()[0]
                    latency = float(time_str)
                    if best_latency is None or latency < best_latency:
                        best_latency = latency
                except (IndexError, ValueError):
                    continue
        except subprocess.SubprocessError:
            continue
    
    return best_latency is not None, best_latency


def load_config():
    """Load the configuration file or create a new one if it doesn't exist."""
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
    """Convert sets to lists in a nested dictionary."""
    if isinstance(obj, dict):
        return {key: sets_to_lists(value) for key, value in obj.items()}
    elif isinstance(obj, set):
        return sorted(list(obj))
    return obj


def save_config(config):
    """Save the configuration file."""
    config_copy = sets_to_lists(config)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config_copy, f, indent=2, sort_keys=True)


def get_pipx_packages():
    """Get the list of installed pipx packages."""
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
    """Get the list of installed brew packages."""
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
    """Get the list of installed flatpak packages."""
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
    """Install a package of the specified type."""
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
    """Remove a package of the specified type."""
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


def update_packages(pkg_type, timeout=60):
    """
    Update all packages of the specified type.
    
    Args:
        pkg_type: The package manager to use ('pipx', 'brew', or 'flatpak')
        timeout: Maximum time in seconds to wait for the update
        
    Returns:
        tuple: (success, is_timeout) where:
            - success is True if update completed successfully
            - is_timeout is True if the operation timed out
    """
    if pkg_type == "pipx":
        cmd = ["pipx", "upgrade-all"]
    elif pkg_type == "brew":
        cmd = ["brew", "upgrade"]
    elif pkg_type == "flatpak":
        cmd = ["flatpak", "update", "-y"]
    else:
        print(f"Unknown package type: {pkg_type}")
        return False, False

    print(f"\nUpdating {pkg_type} packages...")
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True,
            timeout=timeout
        )
        
        if result.returncode != 0:
            print(f"Failed to update {pkg_type} packages: {result.stderr}")
            if result.stdout.strip():
                print(result.stdout)
            return False, False
        
        if result.stdout.strip():
            print(result.stdout)
            
        return True, False
        
    except subprocess.TimeoutExpired:
        print(f"Timeout while updating {pkg_type} packages (>{timeout}s)")
        return False, True
    except Exception as e:
        print(f"Unexpected error while updating {pkg_type} packages: {str(e)}")
        return False, False


def update_all_packages():
    """
    Update all packages from all package managers, with retry for timeouts.
    First checks internet connectivity to avoid unnecessary waits.
    
    Returns:
        bool: True if all updates succeeded, False otherwise
    """
    # First check internet connectivity
    print("Checking internet connectivity...")
    is_connected, latency = check_internet_connection()
    
    if not is_connected:
        print("\nERROR: No internet connectivity detected.")
        print("Please check your internet connection and try again.")
        return False
        
    print(f"Internet connection detected (latency: {latency:.1f}ms)")
    
    # Adjust timeouts based on latency
    base_timeout = max(60, int(latency / 10))  # 60s minimum, or 100x ping time
    retry_timeout = base_timeout * 3
    
    pkg_types = ["pipx", "brew", "flatpak"]
    results = {}
    timeout_failures = []
    
    # First pass - quick timeout
    for pkg_type in pkg_types:
        if not any([
            pkg_type == "pipx" and shutil.which("pipx"),
            pkg_type == "brew" and shutil.which("brew"),
            pkg_type == "flatpak" and shutil.which("flatpak")
        ]):
            continue
            
        success, is_timeout = update_packages(pkg_type, timeout=base_timeout)
        if is_timeout:
            timeout_failures.append(pkg_type)
        else:
            results[pkg_type] = success
    
    # If we had timeouts, check connectivity again before retrying
    if timeout_failures:
        print("\nChecking internet connection before retrying...")
        is_connected, new_latency = check_internet_connection()
        
        if not is_connected:
            print("\nWARNING: Internet connection lost during updates.")
            print("Remaining updates cancelled.")
            return False
            
        if new_latency > latency * 2:
            print(f"\nWARNING: Network latency has increased significantly")
            print(f"Original: {latency:.1f}ms, Current: {new_latency:.1f}ms")
        
        # Only retry if some updates succeeded or if latency is reasonable
        if any(results.values()) or new_latency < 1000:  # 1 second threshold
            print("\nRetrying timed out updates with extended timeout...")
            for pkg_type in timeout_failures:
                success, _ = update_packages(pkg_type, timeout=retry_timeout)
                results[pkg_type] = success
        else:
            print("\nNetwork conditions too poor to retry updates.")
            for pkg_type in timeout_failures:
                results[pkg_type] = False
    
    # Analyze results
    failed = [pkg for pkg, success in results.items() if not success]
    
    # Print summary
    if failed:
        print("\nUpdate summary:")
        print(f"Failed updates: {', '.join(failed)}")
        print("You may want to try updating these package managers manually")
    
    return len(failed) == 0


def get_all_packages():
    """Get all installed packages."""
    return {
        "pipx": get_pipx_packages(),
        "brew": get_brew_packages(),
        "flatpak": get_flatpak_packages(),
    }


def print_package_state(machine_name, packages):
    """Print the package state for a machine."""
    print(f"\nPackages for {machine_name}:")
    for pkg_type in sorted(["pipx", "brew", "flatpak"]):
        pkgs = packages.get(pkg_type, set())
        if pkgs:
            print(f"{pkg_type:8} ({len(pkgs):2}): {', '.join(sorted(pkgs))}")


def sync_packages(machine_name, make_primary=False):
    """Sync packages for a machine."""
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
    """Main function to parse arguments and handle package operations."""
    parser = argparse.ArgumentParser(
        description="Sync and update packages across machines"
    )
    parser.add_argument("machine_name", help="Name of this machine")
    parser.add_argument(
        "--primary", action="store_true", help="Set this machine as primary"
    )
    parser.add_argument(
        "--update", action="store_true", help="Update all installed packages"
    )
    args = parser.parse_args()
    
    if args.update:
        print("\nUpdating all packages...")
        update_all_packages()
    
    sync_packages(args.machine_name, args.primary)


if __name__ == "__main__":
    main()