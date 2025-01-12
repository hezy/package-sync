import json
import subprocess
import os
from pathlib import Path
from datetime import datetime
import argparse
import shutil
from typing import TypeAlias, Dict, List, Set, Any, Optional, Tuple, Literal 

# Type aliases for better clarity
MachineConfig: TypeAlias = Dict[str, Dict[str, Any]]
LastChanges: TypeAlias = Dict[str, Any]
ConfigDict: TypeAlias = Dict[str, Optional[str] | MachineConfig | LastChanges]


CONFIG_PATH = Path("~/.config/package-sync/config.jsonfig.json").expanduser()


def check_internet_connection(
    hosts: list[str] | None = None
) -> tuple[bool, float | None]:
    r"""Check internet connectivity by pinging multiple reliable hosts.

    If no hosts are provided, checks connectivity using well-known DNS servers
    (Google DNS, Cloudflare DNS, and OpenDNS). Each host is pinged with a 2-second
    timeout. Returns both connection status and best observed latency.

    Args:
        hosts: List of host IP addresses to ping. If None, uses default DNS servers.

    Returns:
        A tuple containing:
            - A boolean indicating if any host responded successfully
            - The best response time in milliseconds, or None if all pings failed

    Example:
        >>> is_connected, latency = check_internet_connection()
        >>> print(f"Connected: {is_connected}, Latency: {latency}ms")
        Connected: True, Latency: 24.5ms

    """
    if hosts is None:
        hosts = [
            "8.8.8.8",  # Google DNS
            "1.1.1.1",  # Cloudflare DNS
            "208.67.222.222",  # OpenDNS
        ]

    best_latency: float | None = None
    for host in hosts:
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", host],
                capture_output=True,
                text=True,
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


def load_config() -> Dict[str, Any]:
    r"""Load the configuration file or create a new one if it doesn't exist.

    Returns:
        Dict[str, Any]: A configuration dictionary with the structure:
            {
                "primary_machine": Optional[str],
                "machines": Dict[str, Dict[str, Any]],
                "last_changes": Dict[str, Any]
            }

    """
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    if CONFIG_PATH.exists():
        try:
            with Path.open(CONFIG_PATH) as f:
                return json.load(f)
        except json.JSONDecodeError:
            backup_path = CONFIG_PATH.with_suffix(".json.bak")
            print(f"Config file corrupted. Backing up to {backup_path}")
            shutil.copy(CONFIG_PATH, backup_path)

    config: Dict[str, Any] = {
        "primary_machine": None,
        "machines": {},
        "last_changes": {}
    }
    save_config(config)
    return config


def sets_to_lists(obj: Dict | Set | Any) -> Dict | List | Any:
    r"""Convert all Set objects to sorted Lists within a nested dictionary structure.

    This function recursively traverses a nested dictionary and converts any Set objects 
    it encounters into sorted Lists. Other types are left unchanged. This is useful for 
    preparing nested data structures for JSON serialization, since JSON does not support
    Set types.

    Args:
        obj: The object to process. Can be:
            - A Dict with arbitrary nesting of Dicts and Sets
            - A Set of hashable elements
            - Any other type (which will be returned unchanged)

    Returns:
        The input object with all Sets converted to sorted Lists:
            - Dicts are processed recursively
            - Sets are converted to sorted Lists
            - All other types are returned as-is

    Examples:
        >>> sets_to_lists({'a': {1, 2}, 'b': {'c': {3, 1}, 'd': 5}})
        {'a': [1, 2], 'b': {'c': [1, 3], 'd': 5}}
        >>> sets_to_lists({1, 3, 2})
        [1, 2, 3]
        >>> sets_to_lists(42)
        42
    """
    if isinstance(obj, dict):
        return {key: sets_to_lists(value) for key, value in obj.items()}
    elif isinstance(obj, set):
        return sorted(list(obj))
    return obj


def save_config(config: ConfigDict) -> None:
    r"""Save the configuration to the JSON file specified by CONFIG_PATH.

    Converts all sets in the config dictionary to sorted lists before saving,
    as JSON doesn't support set serialization. The configuration structure is:
    {
        "primary_machine": Optional[str],
        "machines": {
            "machine_name": {
                "packages": {
                    "brew": set[str],
                    "flatpak": set[str],
                    "pipx": set[str]
                },
               "last_update": str  # ISO format datetime
            },
            ...
        },
        "last_changes": Dict[str, Any]
    }

    Args:
        config: Configuration dictionary containing machine package states
               and sync information. Sets will be converted to sorted lists
               before saving.

    Side Effects:
        - Creates CONFIG_PATH parent directories if they don't exist
        - Writes the configuration to CONFIG_PATH in JSON format
        - Overwrites existing configuration file if it exists

    Raises:
        OSError: If there are filesystem permission issues or other IO errors
        TypeError: If the config contains types that can't be JSON serialized

    """
    config_copy = sets_to_lists(config)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config_copy, f, indent=2, sort_keys=True)


def get_pipx_packages() -> set[str]:
    r"""Get the list of installed pipx packages.

    Executes 'pipx list --json' to retrieve all installed packages in JSON
    format. Parses the JSON output to extract package names from the virtual
    environments. Handles error cases gracefully by returning an empty set.

    Note:
        This function assumes pipx's JSON output structure contains a 'venvs'
        key mapping to a dictionary of virtual environments.

    Returns:
        set[str]: A set of package names installed via pipx. Returns an empty
        set if:
            - pipx is not installed
            - pipx command fails to execute
            - JSON output cannot be parsed
            - 'venvs' key is missing from output

    Example:
        >>> packages = get_pipx_packages()
        >>> print(packages)
        {'black', 'mypy', 'ruff'}

    """
    try:
        result = subprocess.run(
            ["pipx", "list", "--json"], 
            capture_output=True, 
            text=True,
            check=False  # Don't raise CalledProcessError on non-zero return codes
        )
        if result.returncode != 0:
            return set()
        return set(json.loads(result.stdout)["venvs"].keys())
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return set()


def get_brew_packages() -> set[str]:
    r"""Get the list of installed Homebrew formula packages.

    Executes 'brew list --formula' to retrieve all installed formula packages.
    Parses the output where package names are separated by newlines.
    Handles error cases gracefully by returning an empty set.

    Returns:
        set[str]: A set of package names installed via Homebrew. Returns an empty set if:
            - brew is not installed
            - brew command fails to execute
            - output is empty or malformed

    Example:
        >>> packages = get_brew_packages()
        >>> print(packages)
        {'git', 'vim', 'wget', 'zsh'}

    Note:
        This function only lists formula packages, not casks. For casks, a separate
        command 'brew list --cask' would be needed.

    """
    try:
        result = subprocess.run(
            ["brew", "list", "--formula"], 
            capture_output=True, 
            text=True,
            check=False  # Don't raise CalledProcessError on non-zero return codes
        )
        if result.returncode != 0:
            return set()

        # Filter out empty strings that might result from trailing newlines
        packages = {pkg for pkg in result.stdout.strip().split("\n") if pkg}
        return packages

    except FileNotFoundError:
        return set()


def get_flatpak_packages() -> set[str]:
    r"""Get the list of installed Flatpak applications.

    Executes 'flatpak list --app --columns=application' to retrieve all
    installed applications. The command specifically:
        - Only lists applications (--app), not runtimes
        - Only includes application IDs (--columns=application)
        - Returns one application ID per line

    Handles error cases gracefully by returning an empty set.

    Returns:
        set[str]: A set of application IDs installed via Flatpak. Returns an empty set if:
            - flatpak is not installed
            - flatpak command fails to execute
            - output is empty or malformed

    Example:
        >>> packages = get_flatpak_packages()
        >>> print(packages)
        {'org.mozilla.firefox', 'com.spotify.Client'}

    Note:
        Application IDs follow the reverse DNS naming convention, e.g.,
        'org.mozilla.firefox' rather than just 'firefox'.

    """
    try:
        result = subprocess.run(
            ["flatpak", "list", "--app", "--columns=application"],
            capture_output=True,
            text=True,
            check=False  # Don't raise CalledProcessError on non-zero return codes
        )
        if result.returncode != 0:
            return set()

        # Filter out empty strings that might result from trailing newlines
        packages = {pkg for pkg in result.stdout.strip().split("\n") if pkg}
        return packages

    except FileNotFoundError:
        return set()


def install_package(
    pkg_type: Literal["brew", "flatpak", "pipx"],
    package: str,
) -> bool:
    r"""Install a package using the specified package manager.

    Attempts to install a single package using the appropriate package manager.
    The function supports three package managers: brew, flatpak, and pipx.
    Installation status messages and any error output are printed to stdout.

    Args:
        pkg_type: Package manager to use. Must be one of: 'brew', 'flatpak', or 'pipx'
        package: Name or ID of the package to install

    Returns:
        Success status of the installation:
            - True if package was installed successfully
            - False if installation failed or package manager command errored

    Examples:
        >>> install_package("pipx", "black")
        Installing pipx package: black
        True

        >>> install_package("flatpak", "org.mozilla.firefox")
        Installing flatpak package: org.mozilla.firefox
        True

    Notes:
        - For flatpak installations, the -y flag is used to automatically accept prompts
        - Installation errors will print the stderr output before returning False
        - Requires the package manager to be installed and available in PATH

    """
    if pkg_type == "brew":
        cmd = ["brew", "install", package]
    elif pkg_type == "flatpak":
        cmd = ["flatpak", "install", "-y", package]
    elif pkg_type == "pipx":
        cmd = ["pipx", "install", package]

    print(f"Installing {pkg_type} package: {package}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Failed to install {package}: {result.stderr}")
        return False
    return True


def remove_package(pkg_type, package):
    r"""Remove a package of the specified type.

    Attempts to remove a single package using the appropriate package manager.
    Prints status messages and captures any error output.

    Args:
        pkg_type: String indicating package manager ('pipx', 'brew', or
        'flatpak') package: String name/ID of the package to remove

    Returns:
        bool: True if removal succeeded, False if it failed

    """
    if pkg_type == "brew":
        cmd = ["brew", "uninstall", package]
    elif pkg_type == "flatpak":
        cmd = ["flatpak", "uninstall", "-y", package]
    elif pkg_type == "pipx":
        cmd = ["pipx", "uninstall", package]

    print(f"Removing {pkg_type} package: {package}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Failed to remove {package}: {result.stderr}")
        return False
    return True


def update_packages(
    pkg_type: Literal["brew", "flatpak", "pipx"],
    timeout: float = 60,
) -> tuple[bool, bool]:
    r"""Update all packages of the specified package manager.

    Attempts to update all installed packages using the specified package
    manager. The operation has a configurable timeout to prevent hanging. Status
    messages and any error output are printed to stdout.

    Args:
        pkg_type: Package manager to use. Must be one of:
        'brew', 'flatpak', or 'pipx'
        timeout: Maximum time in seconds to wait for the update operation to
        complete

    Returns:
        A tuple of (success, is_timeout) where:
            - success: True if all packages were updated successfully
            - is_timeout: True if the operation exceeded the timeout duration

    Examples:
        >>> update_packages("pipx")  # Default 60s timeout
        Updating pipx packages...
        (True, False)

        >>> update_packages("flatpak", timeout=120)  # Extended timeout
        Updating flatpak packages...
        (True, False)

    Notes:
        - For brew updates, uses --ignore-dependencies flag
        - For flatpak updates, -y flag is used to automatically accept prompts
        - Timeouts are treated as update failures (success=False)
        - Non-timeout errors print diagnostic information before returning

    """
    if pkg_type == "brew":
        cmd = ["brew", "upgrade", "--ignore-dependencies"]  # Fixed typo in dependencies
    elif pkg_type == "flatpak":
        cmd = ["flatpak", "update", "-y"]
    elif pkg_type == "pipx":
        cmd = ["pipx", "upgrade-all"]
    else:
        print(f"Unknown package type: {pkg_type}")
        return False, False

    print(f"\nUpdating {pkg_type} packages...")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
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
    r"""Get all installed packages from all supported package managers.

    Retrieves the complete list of installed packages from pipx, brew, and
    flatpak. Packages that fail to retrieve are represented as empty sets.

    Returns:
        dict: A dictionary with package manager names as keys and sets of
        installed packages as values. Format:
              {
                  'brew': {pkg1, pkg2, ...},
                  'flatpak': {pkg1, pkg2, ...},
                  'pipx': {pkg1, pkg2, ...}
              }

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

    pkg_types = ["brew", "flatpak", "pipx"]
    results = {}
    timeout_failures = []

    # First pass - quick timeout
    for pkg_type in pkg_types:
        if not any(
            [
                pkg_type == "brew" and shutil.which("brew"),
                pkg_type == "flatpak" and shutil.which("flatpak"),
                pkg_type == "pipx" and shutil.which("pipx"),
            ]
        ):
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
    r"""Get all installed packages."""
    return {
        "brew": get_brew_packages(),
        "flatpak": get_flatpak_packages(),
        "pipx": get_pipx_packages(),
    }


def print_package_state(machine_name, packages):
    r"""Print the package state for a machine.

    Displays a formatted summary of all installed packages, grouped by package manager.
    Sorts package managers and package names alphabetically for consistent output.

    Args:
        machine_name: String name of the machine
        packages: Dictionary of package sets by package manager type

    """
    print(f"\nPackages for {machine_name}:")
    for pkg_type in sorted(["brew", "flatpak", "pipx"]):
        pkgs = packages.get(pkg_type, set())
        if pkgs:
            print(f"{pkg_type:8} ({len(pkgs):2}): {', '.join(sorted(pkgs))}")


def install_package(pkg_type, package):
    r"""Install a package of the specified type.

    Attempts to install a single package using the appropriate package manager.
    Prints status messages and captures any error output.

    Args:
        pkg_type: String indicating package manager ('brew', 'flatpak' or
        'pipx')
        package: String name/ID of the package to install

    Returns:
        bool: True if installation succeeded, False if it failed

    """
    if pkg_type == "brew":
        cmd = ["brew", "install", package]
    elif pkg_type == "flatpak":
        cmd = ["flatpak", "install", "-y", package]
    elif pkg_type == "pipx":
        cmd = ["pipx", "install", package]

    print(f"Installing {pkg_type} package: {package}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Failed to install {package}: {result.stderr}")
        return False
    return True


def remove_package(pkg_type, package):
    r"""Remove a package of the specified type.

    Attempts to remove a single package using the appropriate package manager.
    Prints status messages and captures any error output.

    Args:
        pkg_type: String indicating package manager ('pipx', 'brew', or
        'flatpak')
        package: String name/ID of the package to remove

    Returns:
        bool: True if removal succeeded, False if it failed

    """
    if pkg_type == "brew":
        cmd = ["brew", "uninstall", package]
    elif pkg_type == "flatpak":
        cmd = ["flatpak", "uninstall", "-y", package]
    elif pkg_type == "pipx":
        cmd = ["pipx", "uninstall", package]

    print(f"Removing {pkg_type} package: {package}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Failed to remove {package}: {result.stderr}")
        return False
    return True


def update_packages(pkg_type, timeout=60):
    r"""Update all packages of the specified type.

    Args:
        pkg_type: The package manager to use ('pipx', 'brew', or 'flatpak')
        timeout: Maximum time in seconds to wait for the update

    Returns:
        tuple: (success, is_timeout) where:
            - success is True if update completed successfully
            - is_timeout is True if the operation timed out

    """
    if pkg_type == "brew":
        cmd = ["brew", "upgrade"]
    elif pkg_type == "flatpak":
        cmd = ["flatpak", "update", "-y"]
    elif pkg_type == "pipx":
        cmd = ["pipx", "upgrade-all"]
    else:
        print(f"Unknown package type: {pkg_type}")
        return False, False

    print(f"\nUpdating {pkg_type} packages...")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
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
    r"""Get all installed packages from all supported package managers.

    Retrieves the complete list of installed packages from pipx, brew, and
    flatpak. Packages that fail to retrieve are represented as empty sets.

    Returns:
        dict: A dictionary with package manager names as keys and sets of installed
              packages as values. Format:
              {
                  'brew': {pkg1, pkg2, ...},
                  'flatpak': {pkg1, pkg2, ...},
                  'pipx': {pkg1, pkg2, ...}
              }

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

    pkg_types = ["brew", "flatpak", "pipx"]
    results = {}
    timeout_failures = []

    # First pass - quick timeout
    for pkg_type in pkg_types:
        if not any(
            [
                pkg_type == "brew" and shutil.which("brew"),
                pkg_type == "flatpak" and shutil.which("flatpak"),
                pkg_type == "pipx" and shutil.which("pipx"),
            ]
        ):
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
    r"""Get all installed packages."""
    return {
        "brew": get_brew_packages(),
        "flatpak": get_flatpak_packages(),
        "pipx": get_pipx_packages(),
    }


def print_package_state(machine_name, packages):
    r"""Print the package state for a machine.

    Displays a formatted summary of all installed packages, grouped by package manager.
    Sorts package managers and package names alphabetically for consistent output.

    Args:
        machine_name: String name of the machine
        packages: Dictionary of package sets by package manager type

    """
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
    r"""Main function to parse arguments and handle package operations."""
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
