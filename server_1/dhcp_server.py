import socket
import json
import time

# === Configuration ===
SERVER_PORT = 6767  # évite le port 67 réservé/root
CLIENT_PORT = 6868
LEASE_DURATION = 60  # en secondes

IP_POOL = [f"192.168.1.{i}" for i in range(100, 111)]
LEASE_FILE = "leases.json"

# === Initialiser ou charger les baux ===
try:
    with open(LEASE_FILE, "r") as f:
        leases = json.load(f)
except FileNotFoundError:
    leases = {ip: {"status": "free", "mac": "", "lease_start": 0} for ip in IP_POOL}


def save_leases():
    with open(LEASE_FILE, "w") as f:
        json.dump(leases, f)


def cleanup_expired_leases():
    now = time.time()
    for ip, info in leases.items():
        if info["status"] == "used" and now - info["lease_start"] > LEASE_DURATION:
            leases[ip]["status"] = "free"
            leases[ip]["mac"] = ""
            leases[ip]["lease_start"] = 0
    save_leases()


# === Lancement du serveur ===
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("localhost", SERVER_PORT))
print(f"[SERVEUR] Démarré sur le port {SERVER_PORT}...")

while True:
    data, addr = sock.recvfrom(1024)
    msg = data.decode()
    cleanup_expired_leases()

    if msg.startswith("DISCOVER:"):
        mac = msg.split(":")[1]
        ip_offer = next(
            (ip for ip, info in leases.items() if info["status"] == "free"), None
        )
        if ip_offer:
            print(f"[SERVEUR] OFFRE {ip_offer} à {mac}")
            sock.sendto(f"OFFER:{ip_offer}".encode(), (addr[0], CLIENT_PORT))

    elif msg.startswith("REQUEST:"):
        # On sépare seulement 2 fois pour garder l'adresse MAC intacte
        _, ip_req, mac = msg.split(":", 2)
        if leases[ip_req]["status"] == "free":
            leases[ip_req]["status"] = "used"
            leases[ip_req]["mac"] = mac
            leases[ip_req]["lease_start"] = time.time()
            save_leases()
            print(f"[SERVEUR] IP {ip_req} attribuée à {mac}")
            sock.sendto(f"ACK:{ip_req}".encode(), (addr[0], CLIENT_PORT))
        else:
            sock.sendto("NAK".encode(), (addr[0], CLIENT_PORT))
