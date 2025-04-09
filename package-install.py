#!/usr/bin/env python3
"""
Package installer script that reads a TOML configuration file and
installs packages using various package managers.
"""

import subprocess
import sys
import tomli
import logging
import os
from typing import Dict, List, Any


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('package_installer.log')
    ]
)


def load_config(config_path: str) -> dict[str, Any]:
    """Load the TOML configuration file."""
    try:
        with open(config_path, "rb") as f:
            return tomli.load(f)
    except Exception as e:
        logging.error(f"Failed to load config file: {e}")
        sys.exit(1)


def check_command_exists(command: str) -> bool:
    """Check if a command exists in the system PATH."""
    try:
        subprocess.run(
            ["which", command], 
            check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        return True
    except subprocess.CalledProcessError:
        return False


def run_command(command: List[str]) -> bool:
    """Run a shell command and return the success status."""
    try:
        logging.info(f"Running: {' '.join(command)}")
        subprocess.run(command, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {e}")
        return False


def install_apt_packages(packages: List[str]) -> None:
    """Install packages using apt."""
    if not check_command_exists("apt"):
        logging.warning("apt not found, skipping apt installations")
        return

    # Update apt repositories first
    if not run_command(["sudo", "apt", "update"]):
        logging.error("Failed to update apt repositories")
        return

    for package in packages:
        logging.info(f"Installing {package} with apt...")
        run_command(["sudo", "apt", "install", "-y", package])


def install_flatpak_packages(packages: List[str]) -> None:
    """Install packages using flatpak."""
    if not check_command_exists("flatpak"):
        logging.warning("flatpak not found, skipping flatpak installations")
        return

    # Add Flathub repository if not already added
    run_command(["flatpak", "remote-add", "--if-not-exists", "flathub-verified", 
                 "https://flathub.org/repo/flathub.flatpakrepo"])

    for package in packages:
        logging.info(f"Installing {package} with flatpak...")
        run_command(["flatpak", "install", "-y", "flathub-verified", package])


def install_homebrew_packages(packages: List[str]) -> None:
    """Install packages using homebrew."""
    if not check_command_exists("brew"):
        logging.warning("brew not found, skipping Homebrew installations")
        return

    # Update Homebrew first
    run_command(["brew", "update"])

    for package in packages:
        logging.info(f"Installing {package} with Homebrew...")
        run_command(["brew", "install", package])


def install_uv_packages(packages: List[str]) -> None:
    """Install Python packages using uv."""
    if not check_command_exists("uv"):
        logging.warning("uv not found, skipping uv installations")
        return

    for package in packages:
        logging.info(f"Installing {package} with uv...")
        run_command(["uv", "tool", "install", package])


def main():
    """Main function to parse arguments and run the installer."""
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <config.toml>")
        sys.exit(1)

    config_path = sys.argv[1]
    if not os.path.exists(config_path):
        logging.error(f"Config file not found: {config_path}")
        sys.exit(1)

    logging.info(f"Loading configuration from {config_path}")
    config = load_config(config_path)

    # Install packages for each package manager
    if "apt" in config and "packages" in config["apt"]:
        install_apt_packages(config["apt"]["packages"])

    if "flatpak" in config and "packages" in config["flatpak"]:
        install_flatpak_packages(config["flatpak"]["packages"])

    if "homebrew" in config and "packages" in config["homebrew"]:
        install_homebrew_packages(config["homebrew"]["packages"])

    if "uv" in config and "packages" in config["uv"]:
        install_uv_packages(config["uv"]["packages"])

    logging.info("Installation process complete!")


if __name__ == "__main__":
    main()
