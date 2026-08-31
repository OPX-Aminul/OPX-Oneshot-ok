# 🔥 OneShot — WPS Attack Tool

OneShot is a powerful WPS (Wi-Fi Protected Setup) penetration testing tool that supports Pixie Dust attacks, online bruteforce, and push-button connections. Works on **any Linux distribution** including Alpine, Debian, Ubuntu, Arch, Fedora, and more.

## ⚡ Features

- **Pixie Dust Attack** — Offline WPS PIN recovery via pixiewps
- **Online Bruteforce** — Smart two-phase PIN bruteforce (first half + second half)
- **Push Button Connect (PBC)** — WPS push button connection
- **Null PIN Attack** — Try empty PIN (00000000)
- **Auto PIN Generation** — Generates likely PINs based on MAC address algorithms
- **WPS Version Detection** — Identifies WPS 1.0 vs 2.0 (1.0 = potentially vulnerable)
- **WPS Lock Handling** — Auto-retries after WPS lock with configurable timeout
- **Process Interference Detection** — Kills conflicting processes (`-k` flag)
- **Real-Time Logger** — Timestamped, color-coded terminal output
- **Vulnerability Database** — 600+ known vulnerable device models
- **Session Save/Restore** — Resume bruteforce from where you left off
- **Android Support** — MediaTek WiFi interface handling
- **Cross-Distro Installer** — Works on Debian, Ubuntu, Arch, Fedora, Alpine, and more

## 🚀 Quick Install

```bash
git clone https://github.com/OPX-Aminul/OPX-Oneshot-ok.git
cd OPX-Oneshot-ok
sudo bash install.sh
```

After installation, just run:
```bash
sudo wififour
```

That's it! It will auto-detect WiFi interfaces, ask you to select one, and launch the tool with `-k` (kill interfering processes) automatically.

## 📦 Supported Distributions

| Distro | Package Manager | Status |
|--------|----------------|--------|
| Debian / Ubuntu / Linux Mint | `apt` | ✅ |
| Alpine Linux | `apk` | ✅ |
| Arch / Manjaro | `pacman` | ✅ |
| Fedora / RHEL / CentOS | `dnf` / `yum` | ✅ |
| openSUSE / SLES | `zypper` | ✅ |
| Void Linux | `xbps` | ✅ |
| Kali / Parrot | `apt` | ✅ |

## 🔧 Manual Install

If you prefer manual installation:

### Dependencies
```bash
# Debian/Ubuntu
sudo apt install python3 python3-pip iw wpa_supplicant pixiewps iproute2

# Alpine
sudo apk add python3 py3-pip iw wpa_supplicant pixiewps iproute2

# Arch
sudo pacman -S python python-pip iw wpa_supplicant pixiewps iproute2

# Fedora
sudo dnf install python3 python3-pip iw wpa_supplicant pixiewps iproute2
```

### Python Dependencies
```bash
pip3 install wcwidth
```

## 🎯 Usage

### Quick Start (after install)
```bash
sudo wififour
```

### Attack Modes

```bash
# Pixie Dust attack (offline PIN recovery)
sudo wififour -K

# Online bruteforce
sudo wififour -B

# Push Button Connect
sudo wififour --pbc

# Null PIN attack
sudo wififour -N

# Direct target with specific PIN
sudo wififour -b <BSSID> -p <PIN>

# Pixie Dust with full range brute
sudo wififour -K -F

# Show pixiewps command
sudo wififour -K -X
```

### All Options

```
Required:
  -i, --interface=<wlan0>    Name of the interface to use

Target:
  -b, --bssid=<mac>          BSSID of the target AP

Attack Modes:
  -p, --pin=<wps pin>        Use a specified pin
  -N, --null-pin             Use null pin (00000000)
  -K, --pixie-dust           Run Pixie Dust attack
  -B, --bruteforce           Run online bruteforce attack
  --pbc                      Run WPS push button connection

Optional:
  -k, --kill                 Kill interfering processes automatically
  -w, --write                Write credentials to file on success
  -l, --loop                 Run in loop mode
  -c, --clear                Clear screen on each scan
  -d, --delay=<n>            Delay between pin attempts (bruteforce only)
  -t, --timeout=<n>          Timeout for WPS lock retry (default: 60s)
  --restore                  Restore killed processes on exit

Advanced:
  -F, --pixie-force          Run pixiewps with --force (full range)
  -X, --show-pixie-cmd       Always print pixiewps command
  -I, --iface-down           Bring interface down on exit
  -M, --mtk-wifi             Activate MediaTek WiFi driver
  -D, --dont-touch-settings  Don't touch Android WiFi settings
  --reverse-scan             Reverse network list order
  --vuln-list=<file>         Custom vulnerable devices list
  -v, --verbose              Verbose output
```

## 📁 Files

| File | Description |
|------|-------------|
| `oneshot.py` | Main tool — single-file WPS attack script |
| `vulnwsc.txt` | Vulnerable device models database (600+ entries) |
| `install.sh` | Universal Linux installer |

## 🔒 How It Works

### Pixie Dust Attack
1. Connects to target AP via WPS
2. Captures WPS protocol data (E-Nonce, PKR, PKE, AuthKey, E-Hash1, E-Hash2, R-Nonce)
3. Runs pixiewps to recover PIN offline
4. Uses recovered PIN to get WPA PSK

### Smart Bruteforce
1. Tries PINs 0000-9999 for first half (4 digits)
2. Validates first half via WPS Message M6
3. Tries 000-999 for second half (3 digits)
4. Calculates 8th digit via WPS checksum

### WPS Lock Handling
When an AP locks WPS after failed attempts:
- Tool detects M2D messages and WSC_NACK responses
- Waits configurable timeout (default 60s)
- Retries automatically with the same PIN

## ⚠️ Disclaimer

This tool is for **authorized security testing only**. Only use it on networks you own or have explicit permission to test. Unauthorized access to computer networks is illegal.

## 📜 License

GPLv2 — See [LICENSE](LICENSE) for details.
