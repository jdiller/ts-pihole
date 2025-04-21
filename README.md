# Tailscale to Pi-hole DNS Sync

This script automatically synchronizes your Tailscale devices with Pi-hole DNS entries. This allows you to access your Tailscale devices by hostname through your Pi-hole DNS server.

## Features

- Automatically extracts device information from Tailscale
- Creates DNS entries in Pi-hole for all online Tailscale devices
- Appends a configurable domain suffix to device names (default: `.lan`)
- Updates entries when IPs change
- Compatible with Pi-hole v6 API
- Detailed logging for monitoring and troubleshooting

## Requirements

- Python 3.6 or higher
- Tailscale CLI installed and configured
- Pi-hole v6 or higher
- Python packages: `requests`, `python-dotenv`

## Installation

1. Clone this repository or download the script:
   ```
   git clone https://github.com/yourusername/tailscale-pihole-sync.git
   cd tailscale-pihole-sync
   ```

2. Install the required Python packages:
   ```
   pip install -r requirements.txt
   ```

3. Copy the example environment file and edit it with your Pi-hole password:
   ```
   cp .env.example .env
   ```

4. Edit the `.env` file and add your Pi-hole admin password.

## Usage

Run the script manually:

```
python tailscale-pihole-sync.py
```

### Setting up as a Scheduled Task

To run the script automatically at regular intervals, set up a cron job:

```
# Run every hour
crontab -e
```

Add the following line:

```
0 * * * * cd /path/to/tailscale-pihole-sync && python tailscale-pihole-sync.py
```

## Logging

The script logs to both console and a log file. The default log file is `./tailscale-pihole-sync.log`, but you can change this in the `.env` file.

## Customization

You can customize the script behavior by modifying these parameters in the `.env` file:

- `PIHOLE_API_URL`: URL to your Pi-hole v6 API (default: http://pi.hole/api)
- `PIHOLE_PASSWORD`: Your Pi-hole admin password
- `HOSTNAME_SUFFIX`: Domain suffix to append to Tailscale hostnames (default: .lan)
- `LOG_FILE`: Path to the log file


