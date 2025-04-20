# Tailscale to Pi-hole DNS Sync

A script that automatically synchronizes your Tailscale devices with Pi-hole DNS entries. This allows you to access your Tailscale devices by hostname through your Pi-hole DNS server.

## Features

- Automatically extracts device information from Tailscale
- Creates DNS entries in Pi-hole for all online Tailscale devices
- Updates entries when IPs change
- Removes entries for devices no longer on the Tailnet
- Detailed logging for monitoring and troubleshooting
- Uses Pi-hole v6 API for better compatibility

## Requirements

### For Python script:
- Python 3.6 or higher
- Tailscale CLI installed and configured
- Pi-hole v6 or higher with API access

## Installation

1. Clone this repository or download the scripts:
   ```
   git clone https://github.com/yourusername/tailscale-pihole-sync.git
   cd tailscale-pihole-sync
   ```

2. For Python script, install the required packages:
   ```
   pip install -r requirements.txt
   ```

3. Copy the example environment file and edit it with your Pi-hole API token:
   ```
   cp .env.example .env
   ```

4. Edit the `.env` file and add your Pi-hole API token. You can find this in the Pi-hole web interface under Settings > API / Web interface > Show API token.

## Usage

```
python tailscale-pihole-sync.py
```


