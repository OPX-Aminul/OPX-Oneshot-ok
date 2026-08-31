#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  OneShot — Universal Linux Installer                        ║
# ║  Works on Debian/Ubuntu, Arch, Fedora, Alpine, and more     ║
# ║  Run as root: sudo bash install.sh                          ║
# ╚══════════════════════════════════════════════════════════════╝

set -e

RED='\033[1;31m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
CYAN='\033[1;36m'
RESET='\033[0m'

INSTALL_DIR="/usr/local/bin"
SCRIPT_NAME="oneshot"
COMMAND_NAME="wifi4"
TOOL_DIR="/opt/oneshot"

# ── Helpers ───────────────────────────────────────────────────

info()  { echo -e "${GREEN}[*]${RESET} $1"; }
warn()  { echo -e "${YELLOW}[-]${RESET} $1"; }
error() { echo -e "${RED}[!]${RESET} $1"; exit 1; }

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        error "Run this script as root: sudo bash install.sh"
    fi
}

detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO_ID="${ID}"
        DISTRO_LIKE="${ID_LIKE:-}"
    elif [ -f /etc/alpine-release ]; then
        DISTRO_ID="alpine"
        DISTRO_LIKE="alpine"
    else
        DISTRO_ID="unknown"
        DISTRO_LIKE=""
    fi
    info "Detected distro: ${DISTRO_ID} (${DISTRO_LIKE})"
}

# ── Package installation ──────────────────────────────────────

install_packages() {
    case "$DISTRO_ID" in
        debian|ubuntu|linuxmint|pop|kali|parrot)
            info "Installing packages via apt..."
            apt-get update -qq || warn "apt-get update failed, continuing..."
            apt-get install -y -qq python3 python3-pip python3-dev \
                git iw wpa_supplicant pixiewps iproute2 wcwidth 2>/dev/null || \
            apt-get install -y python3 python3-pip python3-dev \
                git iw wpa_supplicant iproute2 2>/dev/null || \
            warn "Some packages could not be installed"
            ;;
        alpine)
            info "Installing packages via apk (--no-cache)..."
            apk add --no-cache \
                python3 py3-pip python3-dev \
                git iw wireless-tools wpa_supplicant iproute2 2>/dev/null || \
            apk add --no-cache \
                python3 py3-pip \
                git iw wpa_supplicant iproute2 2>/dev/null || \
            warn "Some Alpine packages could not be installed"
            ;;
        arch|manjaro|endeavouros)
            info "Installing packages via pacman..."
            pacman -Sy --noconfirm python python-pip python-wcwidth \
                git iw wpa_supplicant pixiewps iproute2 2>/dev/null || \
            pacman -Sy --noconfirm python python-pip \
                git iw wpa_supplicant iproute2 2>/dev/null || \
            warn "Some packages could not be installed"
            ;;
        fedora|rhel|centos|rocky|almalinux)
            info "Installing packages via dnf/yum..."
            dnf install -y python3 python3-pip python3-devel \
                git iw wpa_supplicant pixiewps iproute 2>/dev/null || \
            yum install -y python3 python3-pip python3-devel \
                git iw wpa_supplicant iproute 2>/dev/null || \
            warn "Some packages could not be installed"
            ;;
        opensuse*|sles)
            info "Installing packages via zypper..."
            zypper install -y python3 python3-pip python3-devel \
                git iw wpa_supplicant pixiewps iproute2 2>/dev/null || \
            zypper install -y python3 python3-pip python3-devel \
                git iw wpa_supplicant iproute2 2>/dev/null || \
            warn "Some packages could not be installed"
            ;;
        void)
            info "Installing packages via xbps..."
            xbps-install -SuY python3 python3-pip \
                git iw wpa_supplicant pixiewps iproute2 || \
            warn "Some packages could not be installed"
            ;;
        *)
            warn "Unknown distro (${DISTRO_ID}). Trying common package managers..."
            if command -v apt-get &>/dev/null; then
                apt-get update -qq || true
                apt-get install -y python3 python3-pip git iw wpa_supplicant iproute2 || true
            elif command -v apk &>/dev/null; then
                apk add --no-cache python3 py3-pip git iw wpa_supplicant iproute2 || true
            elif command -v pacman &>/dev/null; then
                pacman -Sy --noconfirm python python-pip git iw wpa_supplicant iproute2 || true
            elif command -v dnf &>/dev/null; then
                dnf install -y python3 python3-pip git iw wpa_supplicant iproute2 || true
            elif command -v zypper &>/dev/null; then
                zypper install -y python3 python3-pip git iw wpa_supplicant iproute2 || true
            else
                warn "No supported package manager found. Install manually: python3, iw, wpa_supplicant, iproute2"
            fi
            ;;
    esac
}

# ── Python dependencies ───────────────────────────────────────

install_python_deps() {
    info "Installing Python dependencies..."
    python3 -m pip install --quiet --break-system-packages wcwidth 2>/dev/null || \
    python3 -m pip install --quiet wcwidth 2>/dev/null || \
    pip3 install --quiet wcwidth 2>/dev/null || \
    warn "Could not install wcwidth via pip. If you get errors, run: pip3 install wcwidth"
}

# ── Check required binaries ───────────────────────────────────

check_requirements() {
    info "Checking requirements..."
    MISSING=""
    for bin in python3 iw wpa_supplicant ip; do
        if ! command -v "$bin" &>/dev/null; then
            MISSING="$MISSING $bin"
        fi
    done
    if [ -n "$MISSING" ]; then
        warn "Missing optional binaries:${MISSING}"
        warn "Some features may not work without them."
    fi
    if ! command -v pixiewps &>/dev/null; then
        warn "pixiewps not found — Pixie Dust attacks will not work."
        warn "Install it from your package manager or build from source."
    fi
}

# ── Install oneshot.py ────────────────────────────────────────

install_oneshot() {
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

    if [ ! -f "$SCRIPT_DIR/oneshot.py" ]; then
        error "oneshot.py not found in $SCRIPT_DIR. Run this script from the project directory."
    fi

    info "Installing oneshot.py to ${TOOL_DIR}/..."
    mkdir -p "$TOOL_DIR"
    cp "$SCRIPT_DIR/oneshot.py" "$TOOL_DIR/oneshot.py"

    # Copy vulnwsc.txt if present
    if [ -f "$SCRIPT_DIR/vulnwsc.txt" ]; then
        cp "$SCRIPT_DIR/vulnwsc.txt" "$TOOL_DIR/vulnwsc.txt"
        info "Copied vulnwsc.txt to ${TOOL_DIR}/"
    fi

    chmod +x "$TOOL_DIR/oneshot.py"
    info "Installed oneshot.py → ${TOOL_DIR}/oneshot.py"
}

# ── Create wifi4 command ──────────────────────────────────────

create_wifi4() {
    info "Creating ${COMMAND_NAME} command..."

    cat > "${INSTALL_DIR}/${COMMAND_NAME}" << 'WIFI4_EOF'
#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  wifi4 — OneShot WPS Attack Tool Launcher
#  Auto-detects WiFi interfaces, prompts user, runs with -k
#  Use -u / --update to update from GitHub
# ═══════════════════════════════════════════════════════════════

TOOL_DIR="/opt/oneshot"
TOOL="$TOOL_DIR/oneshot.py"
VULN_FILE="$TOOL_DIR/vulnwsc.txt"
REPO_RAW="https://raw.githubusercontent.com/OPX-Aminul/OPX-Oneshot-ok/main"
TMP_DIR=$(mktemp -d)

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

# ── Handle -u / --update ─────────────────────────────────────
UPDATE_MODE=0
for arg in "$@"; do
    if [ "$arg" = "-u" ] || [ "$arg" = "--update" ]; then
        UPDATE_MODE=1
        break
    fi
done

if [ "$UPDATE_MODE" -eq 1 ]; then
    echo ""
    echo -e "\033[1;36m╔══════════════════════════════════════════════════╗\033[0m"
    echo -e "\033[1;36m║\033[0m  \033[1;97mOneShot Updater\033[0m                              \033[1;36m║\033[0m"
    echo -e "\033[1;36m╚══════════════════════════════════════════════════╝\033[0m"
    echo ""

    DOWNLOADER=""
    if command -v curl &>/dev/null; then
        DOWNLOADER="curl"
    elif command -v wget &>/dev/null; then
        DOWNLOADER="wget"
    else
        echo -e "\033[1;31m[!] Neither curl nor wget found. Install one to use --update.\033[0m"
        exit 1
    fi

    echo -e "\033[1;32m[*] Updating from GitHub...\033[0m"
    echo -e "\033[90m    Repo: OPX-Aminul/OPX-Oneshot-ok\033[0m"
    echo ""

    if [ -f "$TOOL" ]; then
        cp "$TOOL" "${TOOL}.bak"
        echo -e "\033[90m    [~] Backed up current version\033[0m"
    fi

    echo -ne "\033[1;33m    [↓] Downloading oneshot.py...\033[0m"
    if [ "$DOWNLOADER" = "curl" ]; then
        curl -sL -o "$TOOL" "${REPO_RAW}/oneshot.py"
    else
        wget -q -O "$TOOL" "${REPO_RAW}/oneshot.py"
    fi
    if [ -f "$TOOL" ] && [ -s "$TOOL" ]; then
        chmod +x "$TOOL"
        echo -e "\033[1;32m OK\033[0m"
    else
        echo -e "\033[1;31m FAILED\033[0m"
        echo -e "\033[1;31m[!] Failed to download oneshot.py. Check your internet connection.\033[0m"
        if [ -f "${TOOL}.bak" ]; then
            mv "${TOOL}.bak" "$TOOL"
            echo -e "\033[90m    [~] Restored previous version\033[0m"
        fi
        exit 1
    fi

    echo -ne "\033[1;33m    [↓] Downloading vulnwsc.txt...\033[0m"
    if [ "$DOWNLOADER" = "curl" ]; then
        curl -sL -o "$VULN_FILE" "${REPO_RAW}/vulnwsc.txt"
    else
        wget -q -O "$VULN_FILE" "${REPO_RAW}/vulnwsc.txt"
    fi
    if [ -f "$VULN_FILE" ] && [ -s "$VULN_FILE" ]; then
        ENTRIES=$(wc -l < "$VULN_FILE")
        echo -e "\033[1;32m OK\033[0m \033[90m(${ENTRIES} entries)\033[0m"
    else
        echo -e "\033[1;33m SKIP\033[0m \033[90m(using existing database)\033[0m"
    fi

    rm -f "${TOOL}.bak"
    echo ""
    echo -e "\033[1;32m[✓] Update complete!\033[0m"
    echo -e "\033[90m    Installed: $TOOL\033[0m"
    echo -e "\033[90m    Database:  $VULN_FILE\033[0m"
    echo ""
    echo -e "\033[90m    Run \033[0msudo wifi4\033[90m to start the tool\033[0m"
    echo ""
    exit 0
fi

# ── Normal mode: check requirements ──
if [ ! -f "$TOOL" ]; then
    echo -e "\033[1;31m[!] oneshot.py not found at $TOOL\033[0m"
    echo "    Re-run: sudo bash install.sh"
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    echo -e "\033[1;31m[!] Run as root: sudo wifi4\033[0m"
    exit 1
fi

# ── Auto-detect WiFi interfaces (POSIX-compatible) ───────────
echo -e "\033[1;36m[*] Scanning for WiFi interfaces...\033[0m"

if ! command -v iw &>/dev/null; then
    echo -e "\033[1;33m[-] 'iw' not found — wireless interface detection is limited.\033[0m"
    echo -e "\033[90m    Install it (e.g. apt/pacman/dnf install iw) for best results.\033[0m"
fi

IFACES_FILE="$TMP_DIR/ifaces.txt"
> "$IFACES_FILE"

# Method 1: iw dev (most reliable) — lists real 802.11 wireless interfaces
iw dev 2>/dev/null | awk '/Interface/{print $2}' >> "$IFACES_FILE"

# Method 2: /sys/class/net — check every interface for wireless capability
for iface_path in /sys/class/net/*; do
    iface=$(basename "$iface_path")
    [ "$iface" = "lo" ] && continue
    # Check if it has wireless stats
    if [ -d "$iface_path/wireless" ] || [ -d "$iface_path/phy80211" ]; then
        echo "$iface" >> "$IFACES_FILE"
    fi
done 2>/dev/null

# Method 3: ip link — broad search for ANY non-loopback interface.
# This runs UNCONDITIONALLY so wlan0 (and friends) are never dropped just
# because an earlier method already found dummy0/eth0.
ip -o link show 2>/dev/null | awk -F': ' '{print $2}' | grep -v '^lo$' | grep -v '^$' >> "$IFACES_FILE"

# Method 4: iwconfig fallback (only if iwconfig exists)
if command -v iwconfig &>/dev/null; then
    iwconfig 2>/dev/null | awk '{print $1}' | grep -v "^lo$" | grep -v "^eth" >> "$IFACES_FILE"
fi

# Method 5: last resort — always include wlan0 if it exists
if [ -d /sys/class/net/wlan0 ]; then
    echo "wlan0" >> "$IFACES_FILE"
fi

# Prefer wireless interfaces; keep others as fallback but ensure the user
# can always pick the real WiFi NIC even when wired/dummy ifaces crowd the list.
PREFER_WIRELESS_FILE="$TMP_DIR/ifaces_wireless.txt"
> "$PREFER_WIRELESS_FILE"
for iface in $(sort -u "$IFACES_FILE"); do
    [ -z "$iface" ] && continue
    if [ -d "/sys/class/net/$iface/wireless" ] || [ -d "/sys/class/net/$iface/phy80211" ]; then
        echo "$iface" >> "$PREFER_WIRELESS_FILE"
    fi
done
if [ -s "$PREFER_WIRELESS_FILE" ]; then
    cp "$PREFER_WIRELESS_FILE" "$IFACES_FILE"
fi

# Deduplicate
DEDUP_FILE="$TMP_DIR/ifaces_dedup.txt"
sort -u "$IFACES_FILE" | grep -v '^$' > "$DEDUP_FILE"

# Read into variable (POSIX-compatible)
IFACES=""
if [ -s "$DEDUP_FILE" ]; then
    while IFS= read -r line; do
        IFACES="${IFACES}${line} "
    done < "$DEDUP_FILE"
fi

# Count
set -- $IFACES
IFACE_COUNT=0
for iface in "$@"; do
    IFACE_COUNT=$((IFACE_COUNT + 1))
done

if [ "$IFACE_COUNT" -eq 0 ]; then
    echo -e "\033[1;31m[!] No WiFi interfaces found.\033[0m"
    echo ""
    echo -e "    \033[90mAll network interfaces on this system:\033[0m"
    ip -o link show 2>/dev/null | awk -F': ' '{print "      " $2}' | grep -v "^      lo$" || true
    echo ""
    echo -e "    \033[93mTip: You can use the interface name directly:\033[0m"
    echo -e "    \033[90mpython3 /opt/oneshot/oneshot.py -i <interface> -k -K\033[0m"
    echo ""
    exit 1
fi

# ── Prompt user to select interface ───────────────────────────
echo ""
echo -e "\033[1;32m[*] Available WiFi interfaces:\033[0m"
set -- $IFACES
IDX=0
for iface in "$@"; do
    IDX=$((IDX + 1))
    echo -e "    \033[1;33m${IDX})\033[0m ${iface}"
done
echo ""

SELECTED=""
while true; do
    printf "Select interface [1-%d]: " "$IFACE_COUNT"
    read -r choice
    case "$choice" in
        ''|*[!0-9]*)
            echo -e "\033[1;31m[!] Enter a number.\033[0m"
            continue
            ;;
    esac
    if [ "$choice" -ge 1 ] 2>/dev/null && [ "$choice" -le "$IFACE_COUNT" ] 2>/dev/null; then
        set -- $IFACES
        IDX=0
        for iface in "$@"; do
            IDX=$((IDX + 1))
            if [ "$IDX" -eq "$choice" ]; then
                SELECTED="$iface"
                break
            fi
        done
        break
    fi
    echo -e "\033[1;31m[!] Invalid choice. Enter a number between 1 and ${IFACE_COUNT}.\033[0m"
done

# Trim any accidental CR / leading-trailing whitespace from the selected name
# (e.g. install.sh edited on Windows can leave CRLF, which would break "-i wlan0").
SELECTED=$(printf '%s' "$SELECTED" | tr -d '\r' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')

echo -e "\033[1;32m[*] Using interface: ${SELECTED}\033[0m"
echo ""

# ── Build args to forward to oneshot.py ──
# Only forward option flags (starting with '-'). Drop positional tokens such as
# a stray interface name, because the interface is already passed via -i.
CLEAN_ARGS=""
for arg in "$@"; do
    case "$arg" in
        -u|--update) continue ;;
        -*)
            CLEAN_ARGS="${CLEAN_ARGS} ${arg}" ;;
    esac
done

# ── Run OneShot with -k (kill) and -K (Pixie Dust) by default ─
echo -e "\033[90m[~] Launching: python3 $TOOL -i $SELECTED -k -K$CLEAN_ARGS\033[0m"
exec python3 "$TOOL" -i "$SELECTED" -k -K $CLEAN_ARGS
WIFI4_EOF

    chmod +x "${INSTALL_DIR}/${COMMAND_NAME}"
    info "Created command: ${INSTALL_DIR}/${COMMAND_NAME}"
}

# ── Main ──────────────────────────────────────────────────────

main() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════╗${RESET}"
    echo -e "${CYAN}║  OneShot — Universal Linux Installer             ║${RESET}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════╝${RESET}"
    echo ""

    check_root
    detect_distro
    install_packages
    install_python_deps
    check_requirements
    install_oneshot
    create_wifi4

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════╗${RESET}"
    echo -e "${GREEN}║  Installation complete!                          ║${RESET}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "  ${CYAN}Usage:${RESET}"
    echo -e "    sudo wifi4                  ${YELLOW}# Auto-detect interface & run${RESET}"
    echo -e "    sudo wifi4 -u               ${YELLOW}# Update tool from GitHub${RESET}"
    echo -e "    sudo wifi4 -K               ${YELLOW}# Pixie Dust attack${RESET}"
    echo -e "    sudo wifi4 -B               ${YELLOW}# Bruteforce attack${RESET}"
    echo -e "    sudo wifi4 --pbc            ${YELLOW}# Push Button Connect${RESET}"
    echo -e "    sudo wifi4 -b <BSSID> -K    ${YELLOW}# Direct target attack${RESET}"
    echo ""
    echo -e "  ${CYAN}Direct usage:${RESET}"
    echo -e "    python3 ${TOOL_DIR}/oneshot.py -i wlan0 -k -K"
    echo ""
}

main "$@"
