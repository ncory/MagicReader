import socket

UDP_IP = "192.168.1.91"
UDP_PORT = 5000 #49152
MESSAGE = "Start-Full"
MESSAGE = "ShowStop"
#MESSAGE = "Busts Show"

# Available UDP strings for Dave's Player 1:
# "Start-Full"    Full show
# "Leota Show"    Madame Leota Show
# "Busts Show"    Busts Show
# "ShowStop"      Stop current show and return to idle mode

try:
    print(f"Sending '{MESSAGE}' to {UDP_IP}:{UDP_PORT}")

    # Encode string to bytes
    data = MESSAGE.encode("utf-8")
    print(f"Message as bytes: {data}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(data, (UDP_IP, UDP_PORT))

    print("Finished sending UDP")

except Exception as e:
    print(f"Exception: {e}")
