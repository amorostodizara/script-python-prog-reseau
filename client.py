# === client.py ===
import socket
import random
import time
import argparse
import threading

SERVER_HOST = "192.168.1.165"
SERVER_PORT = 6767

parser = argparse.ArgumentParser()
parser.add_argument("--lease", type=int, default=30, help="Durée de bail souhaitée (s)")
parser.add_argument(
    "--outage", type=int, default=0, help="Couper le client après N secondes"
)
args = parser.parse_args()

# MAC aléatoire
mac = "02:00:00:%02x:%02x:%02x" % (
    random.randint(0, 127),
    random.randint(0, 255),
    random.randint(0, 255),
)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# ➜ port dynamique pour pouvoir lancer plusieurs clients
sock.bind(("", 0))
local_port = sock.getsockname()[1]
print(f"[CLIENT {local_port}] MAC={mac}")

sock.settimeout(5)

# DISCOVER
sock.sendto(f"DISCOVER:{mac}".encode(), (SERVER_HOST, SERVER_PORT))
print("[CLIENT] DISCOVER envoyé")

try:
    offer, _ = sock.recvfrom(1024)
    if not offer.decode().startswith("OFFER:"):
        raise RuntimeError("Offre invalide")
    ip = offer.decode().split(":")[1]
    print(f"[CLIENT] Offre IP {ip}")
    sock.sendto(f"REQUEST:{ip}:{mac}:{args.lease}".encode(), (SERVER_HOST, SERVER_PORT))
    ack, _ = sock.recvfrom(1024)
    if not ack.decode().startswith("ACK:"):
        raise RuntimeError("ACK non reçu")
    print(f"[CLIENT] IP {ip} attribuée")

except Exception as e:
    print(f"[CLIENT] Erreur lors de la négociation DHCP: {e}")

    def renew_loop():
        while True:
            time.sleep(args.lease // 2)
