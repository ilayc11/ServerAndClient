import socket
import time
import struct
import threading
import sys
from concurrent.futures import ThreadPoolExecutor

# Constants
MAGIC_COOKIE = 0xabcddcba
OFFER_TYPE = 0x2
UDP_PORT = 13117
BUFFER_SIZE = 2028
MAX_CLIENTS = 100
MAX_RETRIES = 3


# ANSI Color codes
class Colors:
    HEADER = '\033[95m'  # Pink
    BLUE = '\033[94m'  # Blue
    CYAN = '\033[96m'  # Cyan
    GREEN = '\033[92m'  # Green
    YELLOW = '\033[93m'  # Yellow
    RED = '\033[91m'  # Red
    ENDC = '\033[0m'  # Reset color
    BOLD = '\033[1m'  # Bold
    UNDERLINE = '\033[4m'  # Underline


def format_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def format_speed(bits_per_second):
    for unit in ['bps', 'Kbps', 'Mbps', 'Gbps']:
        if bits_per_second < 1000.0:
            return f"{bits_per_second:.2f} {unit}"
        bits_per_second /= 1000.0
    return f"{bits_per_second:.2f} Tbps"


class SpeedTestServer:
    def __init__(self):
        try:
            # Initialize TCP socket
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_socket.bind(('', 0))
            self.SERVER_TCP_PORT = self.tcp_socket.getsockname()[1]

            # Initialize UDP socket
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.bind(('', 0))
            self.SERVER_UDP_PORT = self.udp_socket.getsockname()[1]

            # Get server IP
            hostname = socket.gethostname()
            self.SERVER_IP = socket.gethostbyname(hostname)

            self.tcp_socket.listen(MAX_CLIENTS)

            self.is_running = True
            self.thread_pool = ThreadPoolExecutor(max_workers=MAX_CLIENTS)
            self.active_clients = {}
            self.clients_lock = threading.Lock()

            print(f"{Colors.HEADER}{Colors.BOLD}Speed Test Server Started!{Colors.ENDC}")
            print(f"{Colors.BLUE}Listening on IP address: {Colors.CYAN}{self.SERVER_IP}{Colors.ENDC}")
            print(f"{Colors.BLUE}TCP Port: {Colors.CYAN}{self.SERVER_TCP_PORT}{Colors.ENDC}")
            print(f"{Colors.BLUE}UDP Port: {Colors.CYAN}{self.SERVER_UDP_PORT}{Colors.ENDC}")

        except Exception as e:
            print(f"{Colors.RED}Failed to initialize server: {e}{Colors.ENDC}")
            sys.exit(1)

    def track_client(self, client_address, conn_type):
        with self.clients_lock:
            if client_address not in self.active_clients:
                self.active_clients[client_address] = {'tcp_count': 0, 'udp_count': 0}
            self.active_clients[client_address][f'{conn_type}_count'] += 1

    def untrack_client(self, client_address, conn_type):
        with self.clients_lock:
            if client_address in self.active_clients:
                self.active_clients[client_address][f'{conn_type}_count'] -= 1
                if sum(self.active_clients[client_address].values()) == 0:
                    del self.active_clients[client_address]

    def offer_broadcast(self):
        udp_broadcast = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_broadcast.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        while self.is_running:
            try:
                message = struct.pack('>IBHH',
                                      MAGIC_COOKIE,
                                      OFFER_TYPE,
                                      self.SERVER_UDP_PORT,
                                      self.SERVER_TCP_PORT)
                udp_broadcast.sendto(message, ('<broadcast>', UDP_PORT))
                time.sleep(1)
            except Exception as e:
                print(f"{Colors.RED}Broadcast error: {e}{Colors.ENDC}")
                time.sleep(1)
        udp_broadcast.close()

    def handle_tcp_client(self, connection, address):
        self.track_client(address[0], 'tcp')
        connection.settimeout(30)

        try:
            request = connection.recv(BUFFER_SIZE).decode().strip()
            if not request:
                return

            file_size = int(request)
            if file_size <= 0:
                return

            print(f"{Colors.GREEN}➜ New TCP client connected from {Colors.CYAN}{address}{Colors.ENDC}")
            print(f"{Colors.BLUE}Requested size: {Colors.CYAN}{format_size(file_size)}{Colors.ENDC}")

            bytes_sent = 0
            start_time = time.time()
            chunk_size = min(BUFFER_SIZE, file_size)
            data = b'A' * chunk_size

            while bytes_sent < file_size and self.is_running:
                try:
                    remaining = file_size - bytes_sent
                    to_send = min(remaining, len(data))
                    sent = connection.send(data[:to_send])
                    if sent == 0:
                        break
                    bytes_sent += sent
                except socket.timeout:
                    break

            duration = time.time() - start_time
            speed = (bytes_sent * 8) / duration if duration > 0 else 0

            print(
                f"{Colors.GREEN}✓ TCP transfer complete to {Colors.CYAN}{address}{Colors.ENDC}\n"
                f"  {Colors.BLUE}├─ Sent: {Colors.CYAN}{format_size(bytes_sent)}{Colors.ENDC}\n"
                f"  {Colors.BLUE}├─ Time: {Colors.CYAN}{duration:.2f}s{Colors.ENDC}\n"
                f"  {Colors.BLUE}└─ Speed: {Colors.CYAN}{format_speed(speed)}{Colors.ENDC}"
            )

        except Exception as e:
            print(f"{Colors.RED}✗ Error handling TCP client {address}: {e}{Colors.ENDC}")
        finally:
            connection.close()
            self.untrack_client(address[0], 'tcp')

    def handle_udp_requests(self):
        MAX_PAYLOAD_SIZE = 1400
        HEADER_SIZE = struct.calcsize(">IBQQ")

        while self.is_running:
            try:
                self.udp_socket.settimeout(1.0)
                data, address = self.udp_socket.recvfrom(BUFFER_SIZE)

                if len(data) < struct.calcsize(">IBQ"):
                    continue

                self.track_client(address[0], 'udp')

                try:
                    magic_cookie, message_type, file_size = struct.unpack(">IBQ", data)
                    if magic_cookie != MAGIC_COOKIE or message_type != 0x3:
                        continue

                    print(f"{Colors.GREEN}➜ New UDP request from {Colors.CYAN}{address}{Colors.ENDC}")
                    print(f"{Colors.BLUE}Requested size: {Colors.CYAN}{format_size(file_size)}{Colors.ENDC}")

                    total_packets = (file_size + MAX_PAYLOAD_SIZE - 1) // MAX_PAYLOAD_SIZE
                    start_time = time.time()
                    bytes_sent = 0

                    for packet_number in range(total_packets):
                        if not self.is_running:
                            break

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
                    print(
                        f"{Colors.GREEN}✓ UDP transfer complete to {Colors.CYAN}{address}{Colors.ENDC}\n"
                        f"  {Colors.BLUE}├─ Sent: {Colors.CYAN}{format_size(bytes_sent)}{Colors.ENDC}\n"
                        f"  {Colors.BLUE}├─ Packets: {Colors.CYAN}{total_packets}{Colors.ENDC}\n"
                        f"  {Colors.BLUE}├─ Time: {Colors.CYAN}{duration:.2f}s{Colors.ENDC}\n"
                        f"  {Colors.BLUE}└─ Speed: {Colors.CYAN}{format_speed(speed)}{Colors.ENDC}"
                    )

                except Exception as e:
                    print(f"{Colors.RED}✗ UDP transfer error to {address}: {e}{Colors.ENDC}")
                finally:
                    self.untrack_client(address[0], 'udp')

            except socket.timeout:
                continue
            except Exception as e:
                print(f"{Colors.RED}✗ UDP handler error: {e}{Colors.ENDC}")
                time.sleep(1)

    def run(self):
        try:
            # Start broadcast and UDP handler threads
            threading.Thread(target=self.offer_broadcast, daemon=True).start()
            threading.Thread(target=self.handle_udp_requests, daemon=True).start()

            while True:  # Keep the server running indefinitely
                print(f"{Colors.GREEN}Server is running and listening for clients...{Colors.ENDC}")

                try:
                    self.tcp_socket.settimeout(1.0)  # Avoid blocking indefinitely
                    connection, address = self.tcp_socket.accept()
                    print(f"{Colors.BLUE}✓ New connection from {address}{Colors.ENDC}")
                    self.thread_pool.submit(self.handle_tcp_client, connection, address)
                except socket.timeout:
                    continue  # Timeout is used to periodically check `is_running`
                except Exception as e:
                    print(f"{Colors.RED}✗ Error accepting connection: {e}{Colors.ENDC}")
                    time.sleep(1)

        except KeyboardInterrupt:
            print(f"{Colors.YELLOW}Server shutting down manually...{Colors.ENDC}")

        finally:
            # Gracefully shutdown the server and clean up resources
            self.is_running = False
            self.tcp_socket.close()
            self.udp_socket.close()
            self.thread_pool.shutdown(wait=False)
            print(f"{Colors.GREEN}Server shutdown complete{Colors.ENDC}")


if __name__ == "__main__":
    server = SpeedTestServer()
    server.run()