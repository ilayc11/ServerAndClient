import socket
import struct

MAGIC_COOKIE = 0xabcddcba
OFFER_TYPE = 0x2
UDP_PORT = 13117  # Port to listen on
BUFFER_SIZE = 1024

udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
udp_socket.bind(("", UDP_PORT))
print(f"Client is listening for offers on UDP port {UDP_PORT}...")

while True:
    data,address=udp_socket.recvfrom(BUFFER_SIZE)
    try:
        magic_cookie,message_type,udp_port,tcp_port=struct.unpack('>IBHH',data)
        if magic_cookie == MAGIC_COOKIE and message_type == OFFER_TYPE:
            print(f"Received offer from {address[0]}:")
            print(f"  - UDP Port: {udp_port}")
            print(f"  - TCP Port: {tcp_port}")

            tcp_socket = socket.create_connection((address[0], tcp_port))
            print(f"Connected to server at {address[0]}:{tcp_port}")

            # Step 2: Request file size
            file_size = input("Enter file size to request (bytes): ")
            tcp_socket.sendall((file_size + "\n").encode())

            # Step 3: Receive the data
            bytes_received = 0
            while True:
                chunk = tcp_socket.recv(BUFFER_SIZE)
                if not chunk:
                    break
                bytes_received += len(chunk)
            print(f"Received {bytes_received} bytes from server")
            tcp_socket.close()
    except Exception as e:
        print(f"Error: {e}")
