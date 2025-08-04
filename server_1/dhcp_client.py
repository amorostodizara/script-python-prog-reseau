import socket
import time
import random

SERVER_PORT = 6767
CLIENT_PORT = 6868


def random_mac():
    return "02:00:00:%02x:%02x:%02x" % (
        random.randint(0x00, 0x7F),
        random.randint(0x00, 0xFF),
        random.randint(0x00, 0xFF),
    )


mac = random_mac()
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("localhost", CLIENT_PORT))
sock.settimeout(5)

# DISCOVER
sock.sendto(f"DISCOVER:{mac}".encode(), ("localhost", SERVER_PORT))
print(f"[CLIENT] DISCOVER envoyé depuis {mac}")

try:
    data, _ = sock.recvfrom(1024)
    msg = data.decode()
    if msg.startswith("OFFER:"):
        offered_ip = msg.split(":")[1]
        print(f"[CLIENT] IP OFFERTE : {offered_ip}")
        sock.sendto(f"REQUEST:{offered_ip}:{mac}".encode(), ("localhost", SERVER_PORT))
        print("[CLIENT] REQUEST envoyé")
        ack_data, _ = sock.recvfrom(1024)
        ack_msg = ack_data.decode()
        if ack_msg.startswith("ACK:"):
            print(f"[CLIENT] IP {ack_msg.split(':')[1]} attribuée avec succès.")
        else:
            print("[CLIENT] IP refusée.")
except socket.timeout:
    print("[CLIENT] Temps d’attente dépassé.")
