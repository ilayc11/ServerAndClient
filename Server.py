import socket
import time
import struct
import threading

MAGIC_COOKIE=0xabcddcba
OFFER_TYPE=0X2
UDP_PORT=13117
SERVER_UDP_PORT=12345
SERVER_TCP_PORT=54321
BROADCAST_INTERVAL=1
BUFFER_SIZE = 1024




def offer_broadcast():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    print("Server is broadcasting offers...")
    while True:
        message=struct.pack('>IBHH',MAGIC_COOKIE,OFFER_TYPE,SERVER_UDP_PORT,SERVER_TCP_PORT)
        udp_socket.sendto(message,('<broadcast>',UDP_PORT))
        print(f"Broadcasted offer message to UDP port {UDP_PORT}")
        time.sleep(BROADCAST_INTERVAL)

def handle_client(connection,address):
    print(f"Connected to TCP client {address}")
    try:
        request=connection.recv(BUFFER_SIZE).decode().strip()
        print(f"Received file size request: {request} bytes")
        file_size = int(request)
        data = b'A' * BUFFER_SIZE  # Dummy data
        bytes_sent = 0
        while bytes_sent < file_size:
            connection.sendall(data)
            bytes_sent += len(data)
        print(f"Finished sending {bytes_sent} bytes to {address}")
    except Exception as e:
        print(f"Error handling client {address}: {e}")

    finally:
        connection.close()

def handle_udp_requests():
    """Handle incoming UDP requests."""
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind(("", SERVER_UDP_PORT))
    print(f"Server is listening for UDP requests on port {SERVER_UDP_PORT}...")

    while True:
        data, address = udp_socket.recvfrom(BUFFER_SIZE)
        try:
            # Parse the request
            magic_cookie, message_type, file_size = struct.unpack(">IBQ", data)
            if magic_cookie != MAGIC_COOKIE or message_type != 0x3:
                print(f"Invalid UDP request from {address}")
                continue

            print(f"Valid UDP request from {address}: file size {file_size} bytes")

            # Simulate sending data packets
            total_packets = (file_size + BUFFER_SIZE - 1) // BUFFER_SIZE
            for packet_number in range(total_packets):
                packet = struct.pack(
                    ">IBQQ",
                    MAGIC_COOKIE,
                    0x4,  # Payload message type
                    total_packets,
                    packet_number,
                ) + b'A' * (BUFFER_SIZE - 20)  # Payload data
                udp_socket.sendto(packet, address)

            print(f"Sent {total_packets} packets to {address}")
        except Exception as e:
            print(f"Error handling UDP request from {address}: {e}")

def accept_connections():
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.bind(('',SERVER_TCP_PORT))
    tcp_socket.listen(5)
    print(f"Server is listening for TCP connections on port {SERVER_TCP_PORT}...")
    while True:
        connection, address = tcp_socket.accept()
        threading.Thread(target=handle_client, args=(connection, address)).start()

if __name__ == "__main__":
    threading.Thread(target=offer_broadcast, daemon=True).start()
    threading.Thread(target=handle_udp_requests, daemon=True).start()
    accept_connections()
