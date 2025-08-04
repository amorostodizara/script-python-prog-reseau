import socket
import json
import time
import re
import threading
import subprocess
import platform

SERVER_PORT = 6767
LEASE_FILE = "leases.json"
RESERVATION_FILE = "reservations.json"
LOG_FILE = "dhcp.log"

DEFAULT_LEASE_DURATION = 30  # 1 h
IP_POOL = [f"192.168.1.{i}" for i in range(2, 254)]  # 192.168.1.10‑20 pour tests

# === Ping de surveillance (désactivé par défaut en simulation locale) ===
PING_ENABLED = True  # passe à True si tes clients ont vraiment l'IP sur le réseau
PING_INTERVAL = 10  # secondes
PING_FAILURE_THRESHOLD = 3  # essais

# === Utilitaires ===

IS_WINDOWS = platform.system().lower().startswith("win")


def ping_ip(ip: str) -> bool:
    if IS_WINDOWS:
        cmd = ["ping", "-n", "1", "-w", "1000", ip]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", ip]
    return (
        subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode
        == 0
    )


def is_valid_mac(mac: str) -> bool:
    return re.fullmatch(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", mac) is not None


def log(msg: str):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{time.ctime()} - {msg}\n")
    print(f"[LOG] {msg}")


def load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# === Chargement des données ===

leases = load_json(
    LEASE_FILE,
    {
        ip: {
            "status": "free",
            "mac": "",
            "lease_start": 0,
            "lease_time": DEFAULT_LEASE_DURATION,
        }
        for ip in IP_POOL
    },
)
reservations = load_json(RESERVATION_FILE, {})

# === Surveillance par ping (optionnelle) ===
monitor_flags = {}


def monitor_ip(ip: str):
    """Ping cyclique, libère l'IP si injoignable."""
    failures = 0
    while monitor_flags.get(ip, False):
        time.sleep(PING_INTERVAL)
        if ping_ip(ip):
            failures = 0
        else:
            failures += 1
            log(f"Ping échoué {ip} ({failures}/{PING_FAILURE_THRESHOLD})")
            if failures >= PING_FAILURE_THRESHOLD:
                log(f"Client {ip} hors‑ligne — libération")
                release_ip(ip)
                break


def start_monitor(ip: str):
    if not PING_ENABLED:
        return  # rien en simulation
    monitor_flags[ip] = True
    threading.Thread(target=monitor_ip, args=(ip,), daemon=True).start()


def stop_monitor(ip: str):
    monitor_flags[ip] = False


# === Fonctions cœur ===


def release_ip(ip: str):
    stop_monitor(ip)
    leases[ip] = {
        "status": "free",
        "mac": "",
        "lease_start": 0,
        "lease_time": DEFAULT_LEASE_DURATION,
    }
    save_json(LEASE_FILE, leases)
    log(f"IP {ip} libérée")
    print(f"[INFO] IP {ip} LIBÉRÉE → DISPONIBLE maintenant")


def release_ip(ip: str):
    stop_monitor(ip)
    leases[ip] = {
        "status": "free",
        "mac": "",
        "lease_start": 0,
        "lease_time": DEFAULT_LEASE_DURATION,
    }
    save_json(LEASE_FILE, leases)
    log(f"IP {ip} libérée et leases.json mis à jour")


def cleanup_expired():
    now = time.time()
    for ip, info in leases.items():
        if info["status"] == "used" and now - info["lease_start"] > info["lease_time"]:
            log(f"Bail expiré pour {ip}")
            release_ip(ip)


# === Thread console admin ===


def admin_console():
    while True:
        cmd = input("[ADMIN] show/reserv/exit > ").strip().lower()
        if cmd == "show":
            for ip, info in leases.items():
                print(f"{ip}: {info}")
        elif cmd == "reserv":
            print(json.dumps(reservations, indent=2))
        elif cmd == "exit":
            break


threading.Thread(target=admin_console, daemon=True).start()

# === Boucle serveur ===

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("", SERVER_PORT))
print(f"[SERVEUR] DHCP démarré sur UDP {SERVER_PORT}")

while True:
    data, addr = sock.recvfrom(1024)
    msg = data.decode()
    cleanup_expired()

    # --- DISCOVER ---
    if msg.startswith("DISCOVER:"):
        mac = msg.partition(":")[2]
        if not is_valid_mac(mac):
            log(f"MAC invalide {mac}")
            continue

        ip_offer = reservations.get(mac)
        if not ip_offer:
            ip_offer = next(
                (ip for ip, inf in leases.items() if inf["mac"] == mac), None
            )
        if not ip_offer:
            ip_offer = next(
                (ip for ip, inf in leases.items() if inf["status"] == "free"), None
            )

        if ip_offer:
            sock.sendto(f"OFFER:{ip_offer}".encode(), addr)
            log(f"OFFER {ip_offer} → {mac}")
        else:
            log("Plus d'IP disponibles")

    # --- REQUEST ---
    elif msg.startswith("REQUEST:"):
        rest = msg[len("REQUEST:") :]
        ip_req, _, mac_lease = rest.partition(":")
        mac, _, lease_str = mac_lease.rpartition(":")
        lease_time = int(lease_str) if lease_str.isdigit() else DEFAULT_LEASE_DURATION

        if not (is_valid_mac(mac) and ip_req in leases):
            sock.sendto(b"NAK", addr)
            log(f"NAK IP/MAC invalide {ip_req}/{mac}")
            continue

        if leases[ip_req]["status"] == "free" or leases[ip_req]["mac"] == mac:
            leases[ip_req] = {
                "status": "used",
                "mac": mac,
                "lease_start": time.time(),
                "lease_time": lease_time,
            }
            save_json(LEASE_FILE, leases)
            sock.sendto(f"ACK:{ip_req}".encode(), addr)
            log(f"ACK {ip_req} attribuée à {mac} ({lease_time}s)")
            start_monitor(ip_req)
        else:
            sock.sendto(b"NAK", addr)
            log(f"NAK {ip_req} déjà utilisée")

    # --- RENEW ---
    elif msg.startswith("RENEW:"):
        ip, _, rest = msg[len("RENEW:") :].partition(":")
        mac, _, lease_str = rest.rpartition(":")
        lease_time = int(lease_str) if lease_str.isdigit() else DEFAULT_LEASE_DURATION

        if leases.get(ip, {}).get("mac") == mac:
            leases[ip]["lease_start"] = time.time()
            leases[ip]["lease_time"] = lease_time
            save_json(LEASE_FILE, leases)
            sock.sendto(f"ACK:{ip}".encode(), addr)
            log(f"RENEW ACK {ip} ({lease_time}s)")
        else:
            sock.sendto(b"NAK", addr)
            log(f"NAK RENEW {ip}/{mac}")
