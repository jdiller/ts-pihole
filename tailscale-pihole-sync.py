#!/usr/bin/env python3

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
LOG_FILE = os.environ.get("LOG_FILE", "./tailscale-pihole-sync.log")
logging.basicConfig(
    level=logging.INFO,
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
    "api_token": os.environ.get("PIHOLE_API_TOKEN", "")
}


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


def add_dns_record(domain: str, ip: str) -> bool:
    """
    Add a DNS record to Pi-hole using v6 API
    """
    try:
        url = f"{PIHOLE_CONFIG['base_url']}/dns/custom"
        headers = {"X-API-Key": PIHOLE_CONFIG["api_token"]}
        data = {"domain": domain, "ip": ip}

        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()

        data = response.json()
        if data.get("success", False):
            logger.info(f"Successfully added DNS record: {domain} -> {ip}")
            return True
        else:
            logger.error(f"Failed to add DNS record: {domain} -> {ip}. Response: {data}")
            return False
    except requests.RequestException as e:
        logger.error(f"Error adding DNS record for {domain}: {e}")
        return False


def get_existing_dns_entries() -> Dict[str, str]:
    """
    Get existing custom DNS entries from Pi-hole using v6 API
    """
    try:
        url = f"{PIHOLE_CONFIG['base_url']}/dns/custom"
        headers = {"X-API-Key": PIHOLE_CONFIG["api_token"]}

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        entries = {}

        if data.get("success", False) and "data" in data:
            for entry in data["data"]:
                entries[entry["domain"]] = entry["ip"]

        return entries
    except requests.RequestException as e:
        logger.error(f"Error getting existing DNS entries: {e}")
        return {}


def delete_dns_record(domain: str) -> bool:
    """
    Delete a DNS record from Pi-hole using v6 API
    """
    try:
        url = f"{PIHOLE_CONFIG['base_url']}/dns/custom/{domain}"
        headers = {"X-API-Key": PIHOLE_CONFIG["api_token"]}

        response = requests.delete(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        if data.get("success", False):
            logger.info(f"Successfully deleted DNS record for {domain}")
            return True
        else:
            logger.error(f"Failed to delete DNS record for {domain}. Response: {data}")
            return False
    except requests.RequestException as e:
        logger.error(f"Error deleting DNS record for {domain}: {e}")
        return False


def extract_hostname(dns_name: str) -> str:
    """
    Extract hostname from Tailscale DNS name
    """
    # DNSName typically has format like "hostname.tailnet-name.ts.net"
    parts = dns_name.split(".")
    return parts[0]


def sync_tailscale_to_pihole():
    """
    Main function to synchronize Tailscale peers with Pi-hole DNS
    """
    try:
        logger.info("Starting Tailscale to Pi-hole synchronization")

        # Check if API token is configured
        if not PIHOLE_CONFIG["api_token"]:
            logger.error("Error: Pi-hole API token not configured. Set PIHOLE_API_TOKEN in .env file.")
            return

        # Get Tailscale status
        tailscale_status = get_tailscale_status()

        # Get existing Pi-hole DNS entries
        existing_entries = get_existing_dns_entries()

        # Track which entries should exist
        desired_entries = {}

        # Process peers (including self)
        peers = tailscale_status.get("Peer", {}).copy()
        if "Self" in tailscale_status:
            peers[tailscale_status["Self"]["ID"]] = tailscale_status["Self"]

        for peer_id, peer in peers.items():
            if peer.get("Online", False):
                # Get the IP address (prefer Tailscale IPs)
                ip = None
                if peer.get("TailscaleIPs") and len(peer["TailscaleIPs"]) > 0:
                    ip = peer["TailscaleIPs"][0]
                elif peer.get("IP"):
                    ip = peer["IP"]

                if not ip:
                    logger.warning(f"Warning: No IP found for peer {peer_id}")
                    continue

                hostname = extract_hostname(peer.get("DNSName", ""))
                if not hostname:
                    logger.warning(f"Warning: No hostname extracted for peer {peer_id}")
                    continue

                desired_entries[hostname] = ip

                # Add or update DNS entries
                if hostname not in existing_entries or existing_entries[hostname] != ip:
                    # If the hostname exists but with wrong IP, delete it first
                    if hostname in existing_entries:
                        delete_dns_record(hostname)
                    add_dns_record(hostname, ip)
                else:
                    logger.info(f"DNS record already exists and is up to date: {hostname} -> {ip}")

        # Remove outdated entries
        for domain, ip in existing_entries.items():
            # Only manage entries that appear to be Tailscale hosts
            # You might want to filter with a prefix or pattern specific to your Tailnet
            if domain not in desired_entries and "." not in domain:
                delete_dns_record(domain)

        logger.info("Tailscale to Pi-hole synchronization completed successfully")
    except Exception as e:
        logger.error(f"Error during synchronization: {e}")


if __name__ == "__main__":
    sync_tailscale_to_pihole()