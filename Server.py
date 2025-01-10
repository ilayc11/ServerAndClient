import socket
import time
import struct
import threading
import sys

# Constants
MAGIC_COOKIE = 0xabcddcba
OFFER_TYPE = 0x2
UDP_PORT = 13117
BUFFER_SIZE = 1024


class SpeedTestServer:
    def __init__(self):
        # Get available ports
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.bind(('', 0))
        self.SERVER_TCP_PORT = self.tcp_socket.getsockname()[1]

        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(('', 0))
        self.SERVER_UDP_PORT = self.udp_socket.getsockname()[1]

        # Get server IP
        hostname = socket.gethostname()
        self.SERVER_IP = socket.gethostbyname(hostname)

        self.tcp_socket.listen(5)

    def offer_broadcast(self):
        """Broadcast offer messages."""
        udp_broadcast = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_broadcast.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        print(f"\033[36mServer started, listening on IP address {self.SERVER_IP}\033[0m")

        while True:
            try:
                message = struct.pack('>IBHH',
                                      MAGIC_COOKIE,
                                      OFFER_TYPE,
                                      self.SERVER_UDP_PORT,
                                      self.SERVER_TCP_PORT)
                udp_broadcast.sendto(message, ('<broadcast>', UDP_PORT))
                time.sleep(1)  # Send offer every second
            except Exception as e:
                print(f"\033[31mBroadcast error: {e}\033[0m")
                time.sleep(1)

    def handle_tcp_client(self, connection, address):
        """Handle TCP client connection."""
        try:
            # Get file size request
            request = connection.recv(BUFFER_SIZE).decode().strip()
            file_size = int(request)
            print(f"\033[32mReceived TCP request from {address}: {file_size} bytes\033[0m")

            # Send data
            bytes_sent = 0
            start_time = time.time()

            while bytes_sent < file_size:
                remaining = file_size - bytes_sent
                chunk_size = min(remaining, BUFFER_SIZE)
                data = b'A' * chunk_size
                connection.sendall(data)
                bytes_sent += chunk_size

            duration = time.time() - start_time
            speed = (bytes_sent * 8) / duration if duration > 0 else 0
            print(f"\033[32mCompleted TCP transfer to {address}: "
                  f"{bytes_sent} bytes in {duration:.2f} seconds "
                  f"({speed:.1f} bits/second)\033[0m")

        except Exception as e:
            print(f"\033[31mError handling TCP client {address}: {e}\033[0m")
        finally:
            connection.close()

    def handle_udp_requests(self):
        """Handle UDP client requests."""
        MAX_PAYLOAD_SIZE = 1400
        HEADER_SIZE = struct.calcsize(">IBQQ")

        while True:
            try:
                data, address = self.udp_socket.recvfrom(BUFFER_SIZE)

                # Parse request
                magic_cookie, message_type, file_size = struct.unpack(">IBQ", data)
                if magic_cookie != MAGIC_COOKIE or message_type != 0x3:
                    continue

                print(f"\033[34mReceived UDP request from {address}: {file_size} bytes\033[0m")

                # Calculate packets needed
                total_packets = (file_size + MAX_PAYLOAD_SIZE - 1) // MAX_PAYLOAD_SIZE
                start_time = time.time()
                bytes_sent = 0

                # Send packets
                for packet_number in range(total_packets):
                    remaining = file_size - bytes_sent
                    payload_size = min(remaining, MAX_PAYLOAD_SIZE)

                    header = struct.pack(
                        ">IBQQ",
                        MAGIC_COOKIE,
                        0x4,
                        total_packets,
                        packet_number
                    )
                    payload = b'A' * payload_size
                    self.udp_socket.sendto(header + payload, address)
                    bytes_sent += payload_size

                duration = time.time() - start_time
                speed = (bytes_sent * 8) / duration if duration > 0 else 0
                print(f"\033[34mCompleted UDP transfer to {address}: "
                      f"{bytes_sent} bytes in {duration:.2f} seconds "
                      f"({speed:.1f} bits/second)\033[0m")

            except Exception as e:
                print(f"\033[31mError handling UDP request: {e}\033[0m")

    def run(self):
        """Start the server."""
        # Start broadcast thread
        threading.Thread(target=self.offer_broadcast, daemon=True).start()

        # Start UDP handler thread
        threading.Thread(target=self.handle_udp_requests, daemon=True).start()

        # Accept TCP connections
        while True:
            try:
                connection, address = self.tcp_socket.accept()
                threading.Thread(target=self.handle_tcp_client,
                                 args=(connection, address),
                                 daemon=True).start()
            except Exception as e:
                print(f"\033[31mError accepting connection: {e}\033[0m")
                time.sleep(1)


if __name__ == "__main__":
    server = SpeedTestServer()
    server.run()