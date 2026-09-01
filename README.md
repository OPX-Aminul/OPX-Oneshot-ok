# OPX-wifi4 — Advanced WPS Attack & AP Mode Tool

OPX-wifi4 is a powerful WPS (Wi-Fi Protected Setup) penetration testing tool with a built-in **AP Mode** for captive portal attacks. Supports Pixie Dust attacks, online bruteforce, push-button connections, and **208 pre-built captive portal templates** across 19 categories. Works on **any Linux distribution** including Alpine, Debian, Ubuntu, Arch, Fedora, and more.

## ⚡ Features

### WPS Attack
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

### AP Mode (Evil Twin / Captive Portal)
- **Rogue Access Point** — Create fake WiFi networks with hostapd
- **Captive Portal** — Customizable login page to capture credentials
- **208 Pre-Built Templates** — 19 categories of login portals
- **Live Dashboard** — Real-time capture stats, per-user tracking, client details
- **DNS Logger** — Log all DNS queries from connected clients
- **Internet Forwarding** — Optional NAT-based internet access through AP
- **Internet Before Form** — Choose if internet works immediately or only after form submit
- **Session Data** — All captures saved to timestamped folders

### Captive Portal Detection (All Platforms)

| Platform | Probe URL | Response | Status |
|----------|-----------|----------|--------|
| Android 5-16 | `connectivitycheck.gstatic.com/generate_204` | 302 redirect | ✅ |
| Android (fallback) | `play.googleapis.com/generate_204` | 302 redirect | ✅ |
| Android (fallback) | `clients3.google.com/generate_204` | 302 redirect | ✅ |
| iOS / macOS | `captive.apple.com/hotspot-detect.html` | 302 redirect | ✅ |
| iOS (fallback) | `www.apple.com/library/test/success.html` | 302 redirect | ✅ |
| Windows NCSI | `www.msftconnecttest.com/connecttest.txt` | 302 redirect | ✅ |
| Windows (fallback) | `www.msftncsi.com/ncsi.txt` | 302 redirect | ✅ |
| ChromeOS / Chromium | `clients3.google.com/gen_204` | 302 redirect | ✅ |
| Firefox | `detectportal.firefox.com/canonical.html` | 302 redirect | ✅ |
| Firefox (fallback) | `detectportal.firefox.com/success.txt` | 302 redirect | ✅ |
| Linux NetworkManager | `nmcheck.gnome.org/check_network_status.txt` | 302 redirect | ✅ |
| FireOS / Kindle | `kindle-wifi/wifistub.html` | 302 redirect | ✅ |
| Chromium (Android) | `connectivitycheck.gstatic.com/curl.txt` | 302 redirect | ✅ |

## 🚀 Quick Install

```bash
git clone https://github.com/OPX-Aminul/OPX-Oneshot-ok.git
cd OPX-Oneshot-ok
sudo bash install.sh
```

After installation, just run:
```bash
sudo wifi4
```

That's it! It will auto-detect WiFi interfaces, ask you to select one, and then let you choose between **WiFi Attack** or **AP Mode**.

## 📦 Supported Distributions

| Distro | Package Manager | Status |
|--------|----------------|--------|
| Debian / Ubuntu / Linux Mint | `apt` | ✅ |
| Alpine Linux | `apk --no-cache` | ✅ |
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
sudo apt install python3 python3-pip python3-dev git iw wpa_supplicant pixiewps iproute2

# Alpine
sudo apk add --no-cache python3 py3-pip python3-dev git iw wireless-tools wpa_supplicant iproute2

# Arch
sudo pacman -S python python-pip git iw wpa_supplicant pixiewps iproute2

# Fedora
sudo dnf install python3 python3-pip python3-devel git iw wpa_supplicant pixiewps iproute2
```

### Python Dependencies
```bash
pip3 install wcwidth
```

## 🎯 Usage

### Quick Start (after install)
```bash
sudo wifi4
```

### Attack Modes

```bash
# Update tool from GitHub
sudo wifi4 -u

# Pixie Dust attack (offline PIN recovery)
sudo wifi4 -K

# Online bruteforce
sudo wifi4 -B

# Push Button Connect
sudo wifi4 --pbc

# Null PIN attack
sudo wifi4 -N

# Direct target with specific PIN
sudo wifi4 -b <BSSID> -p <PIN>

# Pixie Dust with full range brute
sudo wifi4 -K -F

# Show pixiewps command
sudo wifi4 -K -X
```

### AP Mode (Evil Twin / Captive Portal)

```bash
# Launch AP Mode (interactive — guided setup)
sudo wifi4 -a

# Or use long flag
sudo wifi4 --ap-mode
```

When you select **AP Mode** (option 2) or use `-a`, you'll be guided through:

1. **DNS-Only Mode** — Pure DNS traffic logging (no portal)
2. **Internet Access** — Enable/disable NAT forwarding
3. **HTML Selection** — Browse 19 categories with 208 templates, use current directory HTML, or custom path
4. **Internet Before Form** — Grant internet immediately (Y) or only after form submit (N)
5. **Internet Before Insert** — Grant internet before form fill (Y) or block until submit (N)
6. **SSID & Channel** — Name your fake AP and pick WiFi channel

The AP will start broadcasting and show a **live dashboard** of:
- Captured form submissions (usernames, passwords, etc.)
- Per-user data (IP, captures, timestamps, fields)
- All DNS queries from connected clients
- Session data saved to timestamped `captures/` folders

```bash
# Direct CLI usage (skip interactive prompts)
python3 /opt/oneshot/ap_mode.py -i wlan0 --dns-only
python3 /opt/oneshot/ap_mode.py -i wlan0 --html /path/to/page.html
python3 /opt/oneshot/ap_mode.py -i wlan0 --html /path/to/page.html --internet
```

### 📁 Captive Portal Template Catalog (19 Categories, 208 Templates)

| Category | Count | Examples |
|----------|-------|----------|
| 📱 Social Media | 46 | YouTube, Instagram, WhatsApp, TikTok, Discord, Netflix, Spotify, Steam, PlayStation |
| 🚂 Railway Companies | 26 | SNCB, SNCF, Deutsche Bahn, Renfe |
| ✈️ Airlines (EU) | 18 | Air France, British Airways, Ryanair, EasyJet |
| 🌐 ISPs (EU) | 17 | Proximus, Vodafone, Deutsche Telekom, Orange |
| 🏨 Hotels | 12 | Hilton, Ibis, Novotel, Sheraton |
| 💪 Gyms & Fitness | 12 | Basic-Fit, Anytime Fitness, McFIT |
| 🏷️ Brands | 10 | Nike, Coca-Cola, Red Bull, Carlsberg |
| 🍔 Fast Food & Coffee | 10 | McDonald's, KFC, Starbucks, Pizza Hut |
| 📡 WiFi Routers | 7 | TP-Link, NETGEAR, Linksys, Ubiquiti |
| 🇺🇸 US Airlines | 7 | Alaska, JetBlue, Spirit, American, Delta |
| 💻 Tech Companies | 6 | Google, Microsoft, Apple, Amazon, Starlink |
| 🛒 Supermarkets | 6 | Delhaize, IKEA, Tesco |
| 🎢 Theme Parks | 6 | Disneyland Paris, Efteling, Walibi |
| 🎭 Test & Prank Pages | 5 | FakeHack, Frequency, Matrix, Prank_Game |
| 📡 US ISPs & Carriers | 5 | CoxWifi, Spectrum, T-Mobile, Verizon, AT&T |
| 🎨 Custom Portals | 4 | CafeWiFi, CoffeeShop, CorporateWiFi, HotelGuest |
| 💳 Payment & Banking | 4 | Stripe, Square, Wise, Revolut |
| ☁️ Cloud Services | 4 | AWS, Azure, Cloudflare, Google Cloud |
| 🎬 Streaming | 3 | Disney+, HBO Max, Crunchyroll |

### OPX-wifi4 Wrapper Options

The `wifi4` command (OPX-wifi4 launcher) handles these flags itself (before launching oneshot.py):

```
  -u, --update    Update oneshot.py and vulnwsc.txt from GitHub
  -a, --ap-mode   Launch AP Mode directly (skip mode selection menu)
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
| `oneshot.py` | OPX-wifi4 main tool — single-file WPS attack script |
| `ap_mode.py` | OPX-wifi4 AP Mode — Evil Twin / Captive Portal / DNS Logger |
| `vulnwsc.txt` | Vulnerable device models database (600+ entries) |
| `install.sh` | Universal Linux installer |
| `captive_portal/templates/login.html` | Default captive portal login page |
| `captive_portal/templates/success.html` | Login success page |
| `captive_portal/catalog/` | 208 pre-built HTML templates across 19 categories |

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

### WPS Version Detection
The scanner automatically detects and displays the WPS version for each network:
- **WPS 1.0** — Potentially vulnerable (highlighted green in scan list)
- **WPS 2.0** — Standard, more secure

## ⚠️ Disclaimer

This tool is for **authorized security testing only**. Only use it on networks you own or have explicit permission to test. Unauthorized access to computer networks is illegal.

AP Mode requires `hostapd` and `dnsmasq` to be installed. The installer will attempt to install these automatically. On Alpine Linux, these packages are available in the community repository.

The captive portal catalog includes templates cloned from [flipper-portals](https://github.com/L-ubu/flipper-portals) and [evil-portal](https://github.com/bigbrodude6119/flipper-zero-evil-portal), plus custom templates for social media, payment, cloud, and streaming services.

## License

OPX-wifi4 Non-Commercial Copyleft License — see `LICENSE`.

Free for personal and educational use. Commercial use, paid redistribution, closed-source forks, relicensing, and takedown/impersonation of this project are prohibited.
