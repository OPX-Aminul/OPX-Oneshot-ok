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
            apt-get update -qq
            apt-get install -y -qq python3 python3-pip python3-dev \
                git iw wpa_supplicant pixiewps iproute2 wcwidth 2>/dev/null || \
            apt-get install -y python3 python3-pip python3-dev \
                git iw wpa_supplicant iproute2 2>/dev/null
            ;;
        alpine)
            info "Installing packages via apk (--no-cache)..."
            # Alpine: use --no-cache to avoid stale index
            # python3-dev for building, wireless-tools for iwconfig fallback
            apk add --no-cache \
                python3 py3-pip python3-dev \
                git iw wireless-tools wpa_supplicant iproute2 2>/dev/null || \
            apk add --no-cache \
                python3 py3-pip \
                git iw wpa_supplicant iproute2 2>/dev/null || \
            error "Failed to install Alpine packages. Try manually: apk add python3 py3-pip git iw wpa_supplicant iproute2"
            ;;
        arch|manjaro|endeavouros)
            info "Installing packages via pacman..."
            pacman -Sy --noconfirm python python-pip python-wcwidth \
                git iw wpa_supplicant pixiewps iproute2 2>/dev/null || \
            pacman -Sy --noconfirm python python-pip \
                git iw wpa_supplicant iproute2
            ;;
        fedora|rhel|centos|rocky|almalinux)
            info "Installing packages via dnf/yum..."
            dnf install -y python3 python3-pip python3-devel \
                git iw wpa_supplicant pixiewps iproute 2>/dev/null || \
            yum install -y python3 python3-pip python3-devel \
                git iw wpa_supplicant iproute 2>/dev/null || \
            error "Failed to install packages. Install manually: python3, iw, wpa_supplicant, iproute2"
            ;;
        opensuse*|sles)
            info "Installing packages via zypper..."
            zypper install -y python3 python3-pip python3-devel \
                git iw wpa_supplicant pixiewps iproute2 2>/dev/null || \
            zypper install -y python3 python3-pip python3-devel \
                git iw wpa_supplicant iproute2
            ;;
        void)
            info "Installing packages via xbps..."
            xbps-install -SuY python3 python3-pip \
                git iw wpa_supplicant pixiewps iproute2
            ;;
        *)
            warn "Unknown distro (${DISTRO_ID}). Trying common package managers..."
            if command -v apt-get &>/dev/null; then
                apt-get update -qq && apt-get install -y python3 python3-pip git iw wpa_supplicant iproute2
            elif command -v apk &>/dev/null; then
                apk add --no-cache python3 py3-pip git iw wpa_supplicant iproute2
            elif command -v pacman &>/dev/null; then
                pacman -Sy --noconfirm python python-pip git iw wpa_supplicant iproute2
            elif command -v dnf &>/dev/null; then
                dnf install -y python3 python3-pip git iw wpa_supplicant iproute2
            elif command -v zypper &>/dev/null; then
                zypper install -y python3 python3-pip git iw wpa_supplicant iproute2
            else
                error "No supported package manager found. Install manually: python3, iw, wpa_supplicant, iproute2"
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

    # Check for curl or wget
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

    # Backup current version
    if [ -f "$TOOL" ]; then
        cp "$TOOL" "${TOOL}.bak"
        echo -e "\033[90m    [~] Backed up current version\033[0m"
    fi

    # Download oneshot.py
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
        # Restore backup
        if [ -f "${TOOL}.bak" ]; then
            mv "${TOOL}.bak" "$TOOL"
            echo -e "\033[90m    [~] Restored previous version\033[0m"
        fi
        exit 1
    fi

    # Download vulnwsc.txt
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

    # Remove backup on success
    rm -f "${TOOL}.bak"

    # Show installed version
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

# ── Auto-detect WiFi interfaces ───────────────────────────────
echo -e "\033[1;36m[*] Scanning for WiFi interfaces...\033[0m"

INTERFACES=()
while IFS= read -r iface; do
    INTERFACES+=("$iface")
done < <(iw dev 2>/dev/null | awk '/Interface/{print $2}')

# Also check ip link for wireless interfaces
while IFS= read -r iface; do
    # Skip if already in list
    found=0
    for existing in "${INTERFACES[@]}"; do
        if [ "$existing" = "$iface" ]; then
            found=1
            break
        fi
    done
    if [ "$found" -eq 0 ]; then
        INTERFACES+=("$iface")
    fi
done < <(ip link show 2>/dev/null | awk -F': ' '/^[0-9]+:/{gsub(/@.*/, "", $2); print $2}' | grep -E '^(wlan|wlp|ath|wlx)')

# Fallback: also check iwconfig for systems where iw is not installed
if [ ${#INTERFACES[@]} -eq 0 ] && command -v iwconfig &>/dev/null; then
    while IFS= read -r iface; do
        found=0
        for existing in "${INTERFACES[@]}"; do
            if [ "$existing" = "$iface" ]; then
                found=1
                break
            fi
        done
        if [ "$found" -eq 0 ]; then
            INTERFACES+=("$iface")
        fi
    done < <(iwconfig 2>/dev/null | awk '{print $1}' | grep -v "lo\|eth")
fi

# Remove 'lo' and empty entries
FILTERED=()
for iface in "${INTERFACES[@]}"; do
    if [ -n "$iface" ] && [ "$iface" != "lo" ]; then
        FILTERED+=("$iface")
    fi
done
INTERFACES=("${FILTERED[@]}")

if [ ${#INTERFACES[@]} -eq 0 ]; then
    echo -e "\033[1;31m[!] No WiFi interfaces found.\033[0m"
    echo "    Make sure a WiFi adapter is connected."
    exit 1
fi

# ── Prompt user to select interface ───────────────────────────
echo ""
echo -e "\033[1;32m[*] Available WiFi interfaces:\033[0m"
for i in "${!INTERFACES[@]}"; do
    echo -e "    \033[1;33m$((i+1)))\033[0m ${INTERFACES[$i]}"
done
echo ""

while true; do
    read -rp "Select interface [1-${#INTERFACES[@]}]: " choice
    if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#INTERFACES[@]}" ]; then
        SELECTED="${INTERFACES[$((choice-1))]}"
        break
    fi
    echo -e "\033[1;31m[!] Invalid choice. Enter a number between 1 and ${#INTERFACES[@]}.\033[0m"
done

echo -e "\033[1;32m[*] Using interface: ${SELECTED}\033[0m"
echo ""

# ── Filter out -u from args before passing to oneshot.py ──
CLEAN_ARGS=()
for arg in "$@"; do
    if [ "$arg" != "-u" ] && [ "$arg" != "--update" ]; then
        CLEAN_ARGS+=("$arg")
    fi
done

# ── Run OneShot with -k (kill) and -K (Pixie Dust) by default ─
exec python3 "$TOOL" -i "$SELECTED" -k -K "${CLEAN_ARGS[@]}"
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
