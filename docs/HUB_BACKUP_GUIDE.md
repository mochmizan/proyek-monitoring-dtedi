# Raspberry Pi Edge Gateway Backup Gate Guide

## 1. Overview & Policy

Before any software updates, dependency upgrades, or configuration changes are deployed to the physical Raspberry Pi edge gateways (`hs109rs-hub-01`), **a verified backup archive must be created and copied off-device**.

The Raspberry Pi edge gateway performs critical edge networking roles:
- Running **Mosquitto MQTT Broker** with password hashing and topic ACLs for ESP8266 nodes.
- Acting as an **Access Point (AP)** via `hostapd` / `dnsmasq` or managing network connections via `NetworkManager`.
- Running **HubBrain V5** systemd service with persistent offline SQLite buffer (`edge_cache.db`), TLS certificate pins (`cert.crt`), and edge secret credentials (`.env`).

Failure to back up these components before making system modifications risks orphaning wireless sensor nodes or losing edge buffered telemetry.

---

## 2. Protected Components

The automated backup tool (`tools/backup_hub.sh`) bundles the following critical paths into a single timestamped tarball (`hubbrain_backup_YYYYMMDD_HHMMSS.tar.gz`):

| Component | Filesystem Path | Purpose |
| :--- | :--- | :--- |
| **Network Connections** | `/etc/NetworkManager/system-connections/` | WiFi client credentials, static IP configurations |
| **Access Point (AP)** | `/etc/hostapd/hostapd.conf`, `/etc/dnsmasq.conf`, `/etc/dnsmasq.d/` | Hotspot SSID, WPA2 passphrase, DHCP range for ESP nodes |
| **MQTT Broker** | `/etc/mosquitto/mosquitto.conf`, `/etc/mosquitto/passwd`, `/etc/mosquitto/conf.d/` | Mosquitto broker setup, user passwords (`hubadmin`, node users) |
| **Systemd Units** | `/etc/systemd/system/hubbrain*.service` | Edge daemon auto-start service definitions and environment bindings |
| **HubBrain Config & Secrets** | `<REPO>/hub/.env` | Hub HMAC key, MQTT broker credentials, server target endpoints |
| **TLS Certificate Pin** | `<REPO>/hub/cert.crt` | Server public certificate used for HTTPS verification |
| **Edge Cache Buffer** | `<REPO>/hub/edge_cache.db` | Local SQLite WAL offline telemetry queue |

---

## 3. Creating the Backup (On the Raspberry Pi)

### Step 3.1: Run the Automated Backup Script

Log in to the Raspberry Pi via SSH or serial console and execute:

```bash
cd /opt/smsb  # or path to your repository root
sudo bash tools/backup_hub.sh
```

Optional parameters:
- `--out-dir /path/to/backups` (default: `$HOME/backups`)
- `--app-dir /path/to/smsb` (default: repository root)

### Step 3.2: Verify Output

The script automatically performs integrity checks:
1. Verifies that candidate files are located and included.
2. Creates the compressed tarball: `~/backups/hubbrain_backup_<timestamp>.tar.gz`.
3. Asserts that the archive file size is greater than 0 bytes.
4. Executes `tar -tzf` to confirm the archive can be read without errors.
5. Computes a SHA256 checksum and saves it to `hubbrain_backup_<timestamp>.tar.gz.sha256`.

Example output:
```text
================================================================
    HubBrain Edge Gateway - Mandatory Backup Gate (Milestone 9) 
================================================================
[*] Target archive: /home/pi/backups/hubbrain_backup_20260817_140000.tar.gz
[*] Checking files and directories to archive...
  [+] Found: /etc/NetworkManager/system-connections
  [+] Found: /etc/mosquitto
  [+] Found: /etc/systemd/system/hubbrain.service
  [+] Found: /opt/smsb/hub/.env
  [+] Found: /opt/smsb/hub/cert.crt

[*] Creating compressed tar archive...
[*] Running integrity verification on backup archive...
[*] Verifying tar table of contents (tar -tzf)...
[PASS] Backup archive created and verified successfully!
  Location: /home/pi/backups/hubbrain_backup_20260817_140000.tar.gz
  Size:     48K (49152 bytes)
  SHA256:   d4f2b187...e1
```

---

## 4. Copying Backup Off-Device (Mandatory Gate)

> [!CAUTION]
> **A backup stored only on the Raspberry Pi's SD card is NOT considered valid.** If the SD card experiences filesystem corruption or write failures, the backup is lost. You must download the archive to your workstation.

From your **local workstation / laptop** (macOS, Linux, or Windows PowerShell):

```bash
# Create local backup directory
mkdir -p ./pi_backups

# Download the backup archive and checksum file
scp pi@<PI_IP_ADDRESS>:/home/pi/backups/hubbrain_backup_*.tar.gz ./pi_backups/
scp pi@<PI_IP_ADDRESS>:/home/pi/backups/hubbrain_backup_*.tar.gz.sha256 ./pi_backups/

# Verify checksum on your local machine
cd ./pi_backups
sha256sum -c hubbrain_backup_*.tar.gz.sha256
```

---

## 5. Restoration Runbook (Disaster Recovery)

If an edge deployment fails, the operating system suffers corruption, or an updated service will not start, follow this procedure to restore previous state:

### Step 5.1: Transfer Backup to the Pi (if re-flashed)

```bash
scp ./pi_backups/hubbrain_backup_<timestamp>.tar.gz pi@<PI_IP_ADDRESS>:/tmp/
```

### Step 5.2: Stop Services

```bash
sudo systemctl stop hubbrain.service || true
sudo systemctl stop mosquitto || true
```

### Step 5.3: Extract Configurations

```bash
# Extract with preserved permissions and paths
sudo tar -xzvf /tmp/hubbrain_backup_<timestamp>.tar.gz -P -C /
```

### Step 5.4: Fix Permissions and Reload Services

```bash
# Fix NetworkManager keyfile permissions
sudo chmod 600 /etc/NetworkManager/system-connections/* 2>/dev/null || true
sudo systemctl restart NetworkManager

# Fix Mosquitto configuration permissions
sudo chown -R mosquitto:mosquitto /etc/mosquitto 2>/dev/null || true
sudo systemctl restart mosquitto

# Reload and restart HubBrain service
sudo systemctl daemon-reload
sudo systemctl restart hubbrain.service
sudo systemctl status hubbrain.service
```

---

## 6. Pre-Deployment Gate Checklist

Before executing edge software or firmware updates, the operator must verify:

- [ ] `tools/backup_hub.sh` executed with exit code 0.
- [ ] Archive size confirmed > 0 bytes.
- [ ] Archive table of contents contains `.env`, `mosquitto`, and network configs.
- [ ] `hubbrain_backup_*.tar.gz` downloaded to engineer workstation via `scp`/`rsync`.
- [ ] SHA256 checksum verified on local workstation.
- [ ] Sign-off recorded before proceeding with Pi git pull / update.
