#!/usr/bin/env python3

import json
import logging
import os
import subprocess
import sys
import ipaddress
from datetime import datetime
from typing import List, Optional

import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
LOG_FILE = os.environ.get("LOG_FILE", "/var/log/tailscale-pihole-sync.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Pi-hole API configuration
PIHOLE_CONFIG = {
    "base_url": os.environ.get("PIHOLE_API_URL", "http://pi.hole/api"),
    "password": os.environ.get("PIHOLE_PASSWORD", "")
}

# Comma-separated list of domains to append to hostnames (can be customized)
HOSTNAME_SUFFIXES = os.environ.get("HOSTNAME_SUFFIXES", ".ts")


def normalize_suffix(suffix: str) -> str:
    """
    Lowercase a suffix and make sure it begins with a dot
    """
    suffix = suffix.strip().lower()
    if not suffix.startswith("."):
        logger.warning(f"Suffix '{suffix}' doesn't begin with a dot. Adding one preemptively.")
        suffix = f".{suffix}"
    return suffix


suffixes = [normalize_suffix(s) for s in HOSTNAME_SUFFIXES.split(',') if s.strip()]

def get_tailscale_status() -> dict:
    """
    Execute the tailscale status command and parse the JSON output
    """
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running tailscale command: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing Tailscale JSON output: {e}")
        raise


def authenticate_pihole() -> Optional[str]:
    """
    Authenticate with Pi-hole v6 API and return the session ID
    """
    try:
        url = f"{PIHOLE_CONFIG['base_url']}/auth"
        payload = {"password": PIHOLE_CONFIG["password"]}

        response = requests.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        if not data or "session" not in data or "sid" not in data["session"]:
            logger.error(f"Invalid authentication response from Pi-hole: {data}")
            return None

        sid = data["session"]["sid"]
        logger.debug("Successfully authenticated with Pi-hole")
        return sid
    except requests.RequestException as e:
        logger.error(f"Error authenticating with Pi-hole: {e}")
        return None


def logout_pihole(sid: str) -> bool:
    """
    Logout from Pi-hole API by deleting the session
    """
    try:
        url = f"{PIHOLE_CONFIG['base_url']}/auth"
        headers = {"X-FTL-SID": sid}

        response = requests.delete(url, headers=headers)
        response.raise_for_status()

        logger.debug("Successfully logged out from Pi-hole")
        return True
    except requests.RequestException as e:
        logger.error(f"Error logging out from Pi-hole: {e}")
        return False


def get_custom_dns_entries(sid: str) -> Optional[List[str]]:
    """
    Get existing custom DNS entries from Pi-hole v6 API as raw "IP host [host...]"
    strings. Returns None on failure so callers can avoid overwriting entries
    they couldn't read.
    """
    try:
        url = f"{PIHOLE_CONFIG['base_url']}/config"
        headers = {"X-FTL-SID": sid}

        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        hosts = data["config"]["dns"]["hosts"]
        if not isinstance(hosts, list):
            raise ValueError(f"Expected dns.hosts to be a list, got {type(hosts).__name__}")
        return hosts
    except requests.RequestException as e:
        logger.error(f"Error getting custom DNS entries from Pi-hole: {e}")
        return None
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"Error parsing custom DNS entries from Pi-hole: {e}")
        return None


def is_managed_entry(entry: str) -> bool:
    """
    An entry is managed by this script if every hostname on it ends with one of
    our suffixes. Anything else (including mixed entries) is treated as manual.
    """
    parts = entry.split()
    if len(parts) < 2:
        return False
    return all(host.lower().endswith(tuple(suffixes)) for host in parts[1:])


def update_custom_dns_entries(sid: str, entries: List[str]) -> bool:
    """
    Update custom DNS entries in Pi-hole using v6 API
    """
    try:
        url = f"{PIHOLE_CONFIG['base_url']}/config"
        headers = {"X-FTL-SID": sid}

        # Prepare the payload to update dns.hosts
        payload = {
            "config": {
                "dns": {
                    "hosts": entries
                }
            }
        }

        response = requests.patch(url, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()

        # Check if the response contains our DNS entries
        # Pi-hole v6 returns the entire config and doesn't have a "success" field
        if ("config" in data and
            "dns" in data["config"] and
            "hosts" in data["config"]["dns"]):

            # Check if our entries are in the response
            response_hosts = data["config"]["dns"]["hosts"]

            # Basic validation - check if count matches
            if len(response_hosts) == len(entries):
                logger.info("Successfully updated Pi-hole custom DNS entries")
                return True
            else:
                # Log a warning but still return success as the API call worked
                logger.warning(f"DNS entries count mismatch: sent {len(entries)}, received {len(response_hosts)}")
                return True
        else:
            logger.error("DNS hosts not found in API response")
            return False

    except requests.RequestException as e:
        logger.error(f"Error updating custom DNS entries in Pi-hole: {e}")
        return False


def extract_hostname(dns_name: str, suffix) -> str:
    """
    Extract hostname from Tailscale DNS name and append suffix
    """
    # DNSName typically has format like "hostname.tailnet-name.ts.net"
    hostname = dns_name.split(".")[0]
    if not hostname:
        return ""

    # Suffixes are normalized (lowercase, leading dot) at startup
    return f"{hostname}{suffix}"


def sync_tailscale_to_pihole():
    """
    Main function to synchronize Tailscale peers with Pi-hole DNS
    """
    try:
        logger.info("Starting Tailscale to Pi-hole synchronization")

        # Check if password is configured
        if not PIHOLE_CONFIG["password"]:
            logger.error("Error: Pi-hole password not configured. Set PIHOLE_PASSWORD in .env file.")
            return

        # Authenticate with Pi-hole
        sid = authenticate_pihole()
        if not sid:
            logger.error("Failed to authenticate with Pi-hole. Check your password.")
            return

        try:
            # Get Tailscale status
            tailscale_status = get_tailscale_status()

            # Get existing Pi-hole DNS entries
            existing_entries = get_custom_dns_entries(sid)
            if existing_entries is None:
                logger.error("Could not read existing Pi-hole DNS entries; aborting to avoid clobbering them")
                return

            # Keep anything that isn't using one of our suffixes; managed entries
            # get rebuilt from the current Tailscale state below
            preserved_entries = [e for e in existing_entries if not is_managed_entry(e)]
            logger.debug(
                f"Found {len(existing_entries)} existing custom DNS entries in Pi-hole; "
                f"preserving {len(preserved_entries)} not using managed suffixes {suffixes}"
            )

            # Track which entries should exist
            desired_entries = {}

            # Process peers (including self)
            peers = tailscale_status.get("Peer", {}).copy()
            if "Self" in tailscale_status:
                peers[tailscale_status["Self"]["ID"]] = tailscale_status["Self"]

            # Build entries for online Tailscale devices
            for peer_id, peer in peers.items():
                if peer.get("Online", False):
                    # Get all IP addresses (prefer Tailscale IPs)
                    ips = []
                    if peer.get("TailscaleIPs") and len(peer["TailscaleIPs"]) > 0:
                        ips = peer["TailscaleIPs"]
                    elif peer.get("IP"):
                        ips = [peer["IP"]]

                    if not ips:
                        logger.warning(f"Warning: No IP found for peer {peer_id}")
                        continue

                    for suffix in suffixes:
                        domain = extract_hostname(peer.get("DNSName", ""), suffix)
                        if not domain:
                            logger.warning(f"Warning: No hostname extracted for peer {peer_id}")
                            continue

                        # Process both IPv4 and IPv6 addresses
                        for ip in ips:
                            try:
                                ip_obj = ipaddress.ip_address(ip)
                                desired_entries[f"{ip} {domain}"] = True
                                ip_type = "IPv6" if ip_obj.version == 6 else "IPv4"
                                logger.info(f"Processed Tailscale device: {domain} -> {ip} ({ip_type})")
                            except ValueError:
                                logger.warning(f"Warning: Invalid IP address '{ip}' for peer {peer_id}")
                                continue

            # Manual entries first, then managed ones, in the format Pi-hole v6 expects ("IP domain")
            managed_entries = list(desired_entries.keys())
            dns_entries = preserved_entries + managed_entries

            # Update the entries in Pi-hole
            success = update_custom_dns_entries(sid, dns_entries)
            if success:
                logger.info(
                    f"Successfully synced {len(managed_entries)} Tailscale DNS entries to Pi-hole "
                    f"({len(preserved_entries)} other entries preserved)"
                )
            else:
                logger.error("Failed to sync Tailscale devices to Pi-hole DNS")

        finally:
            # Always log out to clean up the session
            logout_pihole(sid)

    except Exception as e:
        logger.error(f"Error during synchronization: {e}")


if __name__ == "__main__":
    sync_tailscale_to_pihole()

