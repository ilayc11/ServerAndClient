import socket
import struct
import threading
import time
import sys
from queue import Queue
import signal

# Constants
MAGIC_COOKIE = 0xabcddcba
OFFER_TYPE = 0x2
UDP_PORT = 13117
BUFFER_SIZE = 1024
MAX_RETRIES = 3
TIMEOUT = 30


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


class SpeedTestClient:
    def __init__(self):
        self.state = "STARTUP"
        self.current_server = None
        self.transfer_threads = []
        self.transfers_completed = False
        self.error_queue = Queue()
        self.is_running = True
        signal.signal(signal.SIGINT, self.handle_interrupt)

    def handle_interrupt(self, signum, frame):
        print(f"\n{Colors.YELLOW}Client shutting down...{Colors.ENDC}")
        self.is_running = False
        self.transfers_completed = True

    def get_user_parameters(self):
        try:
            print(f"{Colors.CYAN}Please enter the following parameters:{Colors.ENDC}")
            while True:
                try:
                    self.file_size = int(input(f"{Colors.YELLOW}File size to transfer (bytes): {Colors.ENDC}"))
                    self.tcp_connections = int(input(f"{Colors.YELLOW}Number of TCP connections: {Colors.ENDC}"))
                    self.udp_connections = int(input(f"{Colors.YELLOW}Number of UDP connections: {Colors.ENDC}"))

                    if self.file_size > 0 and self.tcp_connections >= 0 and self.udp_connections >= 0:
                        if self.tcp_connections + self.udp_connections > 0:
                            break
                    print(
                        f"{Colors.RED}Please enter valid numbers (file size > 0, at least one connection){Colors.ENDC}")
                except ValueError:
                    print(f"{Colors.RED}Please enter valid numbers{Colors.ENDC}")

            print(
                f"\n{Colors.GREEN}Configuration:{Colors.ENDC}\n"
                f"  {Colors.BLUE}├─ File size: {Colors.CYAN}{format_size(self.file_size)}{Colors.ENDC}\n"
                f"  {Colors.BLUE}├─ TCP connections: {Colors.CYAN}{self.tcp_connections}{Colors.ENDC}\n"
                f"  {Colors.BLUE}└─ UDP connections: {Colors.CYAN}{self.udp_connections}{Colors.ENDC}"
            )
            self.state = "LOOKING_FOR_SERVER"

        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Client shutdown requested{Colors.ENDC}")
            sys.exit(0)

    def handle_tcp_transfer(self, server_ip, tcp_port, connection_id):
        for retry in range(MAX_RETRIES):
            tcp_socket = None
            try:
                start_time = time.time()
                tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                tcp_socket.settimeout(TIMEOUT)

                print(f"{Colors.BLUE}Starting TCP transfer #{connection_id}...{Colors.ENDC}")
                tcp_socket.connect((server_ip, tcp_port))
                tcp_socket.sendall(f"{self.file_size}\n".encode())

                bytes_received = 0
                last_progress = 0
                while bytes_received < self.file_size and self.is_running:
                    chunk = tcp_socket.recv(BUFFER_SIZE)
                    if not chunk:
                        if bytes_received < self.file_size:
                            raise ConnectionError("Server closed connection prematurely")
                        break
                    bytes_received += len(chunk)

                    # Show progress every 10%
                    progress = (bytes_received * 100) // self.file_size
                    if progress - last_progress >= 10:
                        print(f"{Colors.BLUE}TCP #{connection_id} Progress: {Colors.CYAN}{progress}%{Colors.ENDC}")
                        last_progress = progress

                end_time = time.time()
                duration = end_time - start_time
                speed = (bytes_received * 8) / duration if duration > 0 else 0

                print(
                    f"{Colors.GREEN}✓ TCP transfer #{connection_id} complete{Colors.ENDC}\n"
                    f"  {Colors.BLUE}├─ Received: {Colors.CYAN}{format_size(bytes_received)}{Colors.ENDC}\n"
                    f"  {Colors.BLUE}├─ Time: {Colors.CYAN}{duration:.2f}s{Colors.ENDC}\n"
                    f"  {Colors.BLUE}└─ Speed: {Colors.CYAN}{format_speed(speed)}{Colors.ENDC}"
                )
                break

            except Exception as e:
                print(f"{Colors.RED}✗ TCP transfer #{connection_id} error: {e}{Colors.ENDC}")
                if retry < MAX_RETRIES - 1:
                    print(f"{Colors.YELLOW}Retrying TCP transfer #{connection_id}...{Colors.ENDC}")
                    time.sleep(1)
            finally:
                if tcp_socket:
                    tcp_socket.close()

    '''
    def handle_udp_transfer_(self, server_ip, udp_port, connection_id):
        try:
            start_time = time.time()
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.settimeout(1)

            print(f"{Colors.BLUE}Starting UDP transfer #{connection_id}...{Colors.ENDC}")

            # Calculate the total number of packets needed
            total_packets = (self.file_size + BUFFER_SIZE - 1) // BUFFER_SIZE
            bytes_sent = 0
            last_progress = 0

            # Send packets
            for packet_number in range(total_packets):
                start_byte = packet_number * BUFFER_SIZE
                end_byte = min(start_byte + BUFFER_SIZE, self.file_size)

                # Construct the packet
                packet_data = struct.pack(">IBQQ", MAGIC_COOKIE, 0x3, total_packets, packet_number)
                payload = b"x" * (end_byte - start_byte)  # Simulating data
                udp_socket.sendto(packet_data + payload, (server_ip, udp_port))
                bytes_sent += len(payload)

                # Display progress every 10%
                progress = (bytes_sent * 100) // self.file_size
                if progress - last_progress >= 10:
                    print(f"{Colors.BLUE}UDP #{connection_id} Progress: {Colors.CYAN}{progress}%{Colors.ENDC}")
                    last_progress = progress

            end_time = time.time()
            duration = end_time - start_time
            speed = (bytes_sent * 8) / duration if duration > 0 else 0

            print(
                f"{Colors.GREEN}✓ UDP transfer #{connection_id} complete{Colors.ENDC}\n"
                f"  {Colors.BLUE}├─ Sent: {Colors.CYAN}{format_size(bytes_sent)}{Colors.ENDC}\n"
                f"  {Colors.BLUE}├─ Time: {Colors.CYAN}{duration:.2f}s{Colors.ENDC}\n"
                f"  {Colors.BLUE}└─ Speed: {Colors.CYAN}{format_speed(speed)}{Colors.ENDC}"
            )

        except Exception as e:
            print(f"{Colors.RED}✗ UDP transfer #{connection_id} error: {e}{Colors.ENDC}")
        finally:
            udp_socket.close()
    ''' # TODO REMOVE THAT METHOD BEFORE SUBMITTING THE ASSIGNMENT

    def handle_udp_transfer(self, server_ip, udp_port, connection_id):
        try:
            print('Entered handle_upd_transfer method ... ')
            start_time = time.time()
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.settimeout(1)

            print(f"{Colors.BLUE}Starting UDP transfer #{connection_id}...{Colors.ENDC}")
            request = struct.pack(">IBQ", MAGIC_COOKIE, 0x3, self.file_size)
            udp_socket.sendto(request, (server_ip, udp_port))
            received_packets = set()
            total_packets = None
            bytes_received = 0
            last_progress = 0

            while self.is_running:
                try:
                    data, _ = udp_socket.recvfrom(BUFFER_SIZE) # TODO : IN THAT LINE THE CODE RAISE EXCEPTION
                    if len(data) < struct.calcsize(">IBQQ"):
                        continue

                    header = data[:struct.calcsize(">IBQQ")]
                    payload = data[struct.calcsize(">IBQQ"):]
                    magic_cookie, message_type, total_packets, packet_number = struct.unpack(
                        ">IBQQ", header
                    )
                    print(f"TOTAL PACKETS --->>>> {total_packets}")
                    if magic_cookie != MAGIC_COOKIE or message_type != 0x4:
                        continue

                    received_packets.add(packet_number)
                    bytes_received += len(payload)

                    if total_packets:
                        progress = (len(received_packets) * 100) // total_packets
                        if progress - last_progress >= 10:
                            print(f"{Colors.BLUE}UDP #{connection_id} Progress: {Colors.CYAN}{progress}%{Colors.ENDC}")
                            last_progress = progress

                except socket.timeout:
                    if total_packets and len(received_packets) == total_packets:
                        break
                    if time.time() - start_time > TIMEOUT:
                        break

            end_time = time.time()
            duration = end_time - start_time
            speed = (bytes_received * 8) / duration if duration > 0 else 0

            if total_packets:
                success_rate = (len(received_packets) / total_packets) * 100
                print(
                    f"{Colors.GREEN}✓ UDP transfer #{connection_id} complete{Colors.ENDC}\n"
                    f"  {Colors.BLUE}├─ Received: {Colors.CYAN}{format_size(bytes_received)}{Colors.ENDC}\n"
                    f"  {Colors.BLUE}├─ Time: {Colors.CYAN}{duration:.2f}s{Colors.ENDC}\n"
                    f"  {Colors.BLUE}├─ Speed: {Colors.CYAN}{format_speed(speed)}{Colors.ENDC}\n"
                    f"  {Colors.BLUE}└─ Success rate: {Colors.CYAN}{success_rate:.1f}%{Colors.ENDC}"
                )

        except Exception as e:
            print(f"{Colors.RED}✗ UDP transfer #{connection_id} error: {e}{Colors.ENDC}")
        finally:
            udp_socket.close()


    def start_speed_test(self):
        self.transfer_threads = []

        # Start TCP transfers
        for i in range(self.tcp_connections):
            thread = threading.Thread(
                target=self.handle_tcp_transfer,
                args=(self.current_server[0], self.current_server[2], i + 1)
            )
            self.transfer_threads.append(thread)
            thread.start()

        # Start UDP transfers
        for i in range(self.udp_connections):
            thread = threading.Thread(
                target=self.handle_udp_transfer,
                args=(self.current_server[0], self.current_server[1], i + 1)
            )
            self.transfer_threads.append(thread)
            thread.start()

        # Wait for all transfers to complete
        for thread in self.transfer_threads:
            thread.join()

        print(f"\n{Colors.GREEN}{Colors.BOLD}✓ All transfers completed successfully!{Colors.ENDC}")
        self.transfers_completed = True

    def run(self):
        print(f"{Colors.HEADER}{Colors.BOLD}Speed Test Client Started{Colors.ENDC}")

        # Initial setup
        self.get_user_parameters()

        # Create UDP socket for offers
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.bind(("", UDP_PORT))
        udp_socket.settimeout(1)

        print(f"\n{Colors.BLUE}Client started, listening for offer requests...{Colors.ENDC}")

        while not self.transfers_completed and self.is_running:
            try:
                data, address = udp_socket.recvfrom(BUFFER_SIZE)
                magic_cookie, message_type, udp_port, tcp_port = struct.unpack('>IBHH', data)

                if magic_cookie == MAGIC_COOKIE and message_type == OFFER_TYPE:
                    print(
                        f"\n{Colors.GREEN}➜ Found server:{Colors.ENDC}\n"
                        f"  {Colors.BLUE}├─ IP: {Colors.CYAN}{address[0]}{Colors.ENDC}\n"
                        f"  {Colors.BLUE}├─ UDP Port: {Colors.CYAN}{udp_port}{Colors.ENDC}\n"
                        f"  {Colors.BLUE}└─ TCP Port: {Colors.CYAN}{tcp_port}{Colors.ENDC}"
                    )
                    self.current_server = (address[0], udp_port, tcp_port)
                    self.start_speed_test()
                    break  # Exit after completing transfers

            except socket.timeout:
                continue
            except Exception as e:
                print(f"{Colors.RED}✗ Error: {e}{Colors.ENDC}")
                time.sleep(1)

        print(f"{Colors.YELLOW}Client shutting down its UDP connection...{Colors.ENDC}")
        udp_socket.close()

        # Start new transfer after client received it's all content
        self.transfers_completed = False
        self.run()
        #sys.exit(0)


if __name__ == "__main__":
    client = SpeedTestClient()
    client.run()