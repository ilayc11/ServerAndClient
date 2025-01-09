import socket
import struct

MAGIC_COOKIE = 0xabcddcba
OFFER_TYPE = 0x2
UDP_PORT = 13117  # Port to listen on
BUFFER_SIZE = 1024



def send_udp_request(server_ip, udp_port, file_size):
    """Send a UDP request and process the response."""
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Step 1: Send the UDP request
    request = struct.pack(">IBQ", MAGIC_COOKIE, 0x3, file_size)
    udp_socket.sendto(request, (server_ip, udp_port))
    print(f"Sent UDP request to {server_ip}:{udp_port} for {file_size} bytes")

    # Step 2: Receive packets
    received_packets = set()
    udp_socket.settimeout(1)  # Timeout for detecting the end of transmission

    try:
        while True:
            data, address = udp_socket.recvfrom(BUFFER_SIZE)
            magic_cookie, message_type, total_packets, packet_number = struct.unpack(
                ">IBQQ", data[:20]
            )

            if magic_cookie != MAGIC_COOKIE or message_type != 0x4:
                print(f"Invalid packet from {address}")
                continue

            received_packets.add(packet_number)
    except socket.timeout:
        print("UDP transfer completed")

    # Step 3: Calculate packet loss
    total_packets = max(received_packets) + 1 if received_packets else 0
    lost_packets = total_packets - len(received_packets)
    print(f"Received {len(received_packets)} packets, lost {lost_packets} packets")


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

            # Connect to the server via TCP
            tcp_socket = socket.create_connection((address[0], tcp_port))
            print(f"Connected to server at {address[0]}:{tcp_port}")

            # Request file size from the user
            file_size = input("Enter file size to request (bytes): ").strip()
            tcp_socket.sendall((file_size + "\n").encode())

            # Receive the response
            bytes_received = 0
            while True:
                chunk = tcp_socket.recv(BUFFER_SIZE)
                if not chunk:
                    break
                bytes_received += len(chunk)
            print(f"Received {bytes_received} bytes from server")
            tcp_socket.close()

            # Send UDP request
            send_udp_request(address[0], udp_port, int(file_size))
    except Exception as e:
        print(f"Error: {e}")
