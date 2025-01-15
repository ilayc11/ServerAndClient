import socket
import struct
import threading
import time
import sys
from queue import Queue
from Config import Colors,Config,Format


class Client:
    def __init__(self):
        self.state = "STARTUP"
        self.current_server = None
        self.transfer_threads = []
        self.transfers_completed = False
        self.error_queue = Queue()
        self.is_running = True

        #statistics
        self.total_data_received = 0
        self.failed_transfers = 0
        self.tcp_transfers = 0
        self.udp_transfers = 0

    def print_statistics(self):
        print(f"{Colors.GREEN}{Colors.BOLD}Client Statistics:{Colors.ENDC}")
        print(f"{Colors.BLUE}Total data received: {Colors.CYAN}{Format.format_size(self.total_data_received)}{Colors.ENDC}")
        print(f"{Colors.BLUE}TCP transfers completed: {Colors.CYAN}{self.tcp_transfers}{Colors.ENDC}")
        print(f"{Colors.BLUE}UDP transfers completed: {Colors.CYAN}{self.udp_transfers}{Colors.ENDC}")
        print(f"{Colors.RED}Failed transfers: {Colors.CYAN}{self.failed_transfers}{Colors.ENDC}")

    def run(self):
        self.get_user_parameters()

        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.bind(("", Config.OFFER_UDP_PORT))
        udp_socket.settimeout(1)

        print(f"{Colors.BLUE}Client started, listening for offer requests...{Colors.ENDC}")

        while not self.transfers_completed and self.is_running:
            try:
                data, address = udp_socket.recvfrom(Config.CLIENT_BUFFER_SIZE)
                magic_cookie, message_type, udp_port, tcp_port = struct.unpack('>IBHH', data)

                if magic_cookie == Config.MAGIC_COOKIE and message_type == Config.OFFER_TYPE:
                    print(
                        f"  {Colors.BLUE}➜ Received offer from {Colors.CYAN}{address[0]}{Colors.ENDC}\n"
                        f"  {Colors.BLUE}├─ UDP Port: {Colors.CYAN}{udp_port}{Colors.ENDC}\n"
                        f"  {Colors.BLUE}└─ TCP Port: {Colors.CYAN}{tcp_port}{Colors.ENDC}\n"
                    )
                    self.current_server = (address[0], udp_port, tcp_port)
                    self.start_connections()
                    break  # Exit after completing transfers

            except socket.timeout:
                continue
            except Exception as e:
                print(f"{Colors.RED}✗ Error: {e}{Colors.ENDC}")
                time.sleep(1)

        print(f"{Colors.YELLOW}Client statistics at shutdown:{Colors.ENDC}")
        self.print_statistics()
        print(f"{Colors.YELLOW}Client shutting down its Connection and starting again...{Colors.ENDC}")
        udp_socket.close()
        self.transfers_completed = False
        self.run()


    def get_user_parameters(self):
        try:
            print(f"{Colors.CYAN}Please enter the following parameters:{Colors.ENDC}")
            while True:
                try:
                    self.file_size = int(input(f"{Colors.YELLOW}File size to transfer (bytes): {Colors.ENDC}"))
                    self.tcp_connections = int(input(f"{Colors.YELLOW}Number of TCP connections: {Colors.ENDC}"))
                    self.udp_connections = int(input(f"{Colors.YELLOW}Number of UDP connections: {Colors.ENDC}"))

                    if self.file_size > 0 and self.tcp_connections >= 0 and self.udp_connections >= 0:
                        if(self.tcp_connections + self.udp_connections > 0):
                            break
                    print(f"{Colors.RED}Please enter valid numbers (file size > 0, at least one connection){Colors.ENDC}\b")
                except ValueError:
                    print(f"{Colors.RED}Please enter valid numbers{Colors.ENDC}\b")

            print(
                f"  {Colors.GREEN}Configuration:{Colors.ENDC}\n"
                f"  {Colors.BLUE}├─ File size: {Colors.CYAN}{Format.format_size(self.file_size)}{Colors.ENDC}\n"
                f"  {Colors.BLUE}├─ TCP connections: {Colors.CYAN}{self.tcp_connections}{Colors.ENDC}\n"
                f"  {Colors.BLUE}└─ UDP connections: {Colors.CYAN}{self.udp_connections}{Colors.ENDC}\n"
            )
            self.state = "LOOKING_FOR_SERVER"

        except KeyboardInterrupt:
            print(f"{Colors.YELLOW}Client shutdown requested{Colors.ENDC}\n")
            sys.exit(0)

    def start_connections(self):
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

        print(f"{Colors.GREEN}{Colors.BOLD}✓ All transfers completed successfully!{Colors.ENDC}")
        self.transfers_completed = True

    def handle_tcp_transfer(self, server_ip, tcp_port, connection_id):
        for retry in range(Config.MAX_RETRIES):
            tcp_socket = None
            try:
                start_time = time.time()
                tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                timeout = 1.0 + retry * 0.5
                tcp_socket.settimeout(timeout)

                print(f"{Colors.BLUE}Starting TCP transfer #{connection_id}...{Colors.ENDC}")
                tcp_socket.connect((server_ip, tcp_port))
                self.tcp_transfers+=1
                tcp_socket.sendall(f"{self.file_size}\n".encode())

                bytes_received = 0
                while bytes_received < self.file_size and self.is_running:
                    chunk = tcp_socket.recv(Config.CLIENT_BUFFER_SIZE)
                    if not chunk:
                        if bytes_received < self.file_size:
                            raise ConnectionError("Server closed connection prematurely")
                        break
                    bytes_received += len(chunk)


                end_time = time.time()
                duration = end_time - start_time
                speed = (bytes_received * 8) / duration if duration > 0 else 0
                self.total_data_received+=bytes_received

                print(
                    f"  {Colors.GREEN}✓ TCP transfer #{connection_id} complete{Colors.ENDC}\n"
                    f"  {Colors.BLUE}├─ Received: {Colors.CYAN}{Format.format_size(bytes_received)}{Colors.ENDC}\n"
                    f"  {Colors.BLUE}├─ Time: {Colors.CYAN}{duration:.2f}s{Colors.ENDC}\n"
                    f"  {Colors.BLUE}└─ Speed: {Colors.CYAN}{Format.format_speed(speed)}{Colors.ENDC}\n"
                )
                break

            except Exception as e:
                print(f"{Colors.RED}✗ TCP transfer #{connection_id} error: {e}{Colors.ENDC}")
                self.failed_transfers+=1
                if retry < Config.MAX_RETRIES - 1:
                    print(f"{Colors.YELLOW}Retrying TCP transfer #{connection_id}...{Colors.ENDC}")
                    time.sleep(1)
            finally:
                if tcp_socket:
                    tcp_socket.close()

    def handle_udp_transfer(self, server_ip, udp_port, connection_id):
        try:
            start_time = time.time()
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.settimeout(1)

            print(f"{Colors.BLUE}Starting UDP transfer #{connection_id}...{Colors.ENDC}")
            self.udp_transfers+=1
            request = struct.pack(Config.REQUEST_STRUCT_FORMAT, Config.MAGIC_COOKIE,Config.REQUEST_TYPE, self.file_size)
            udp_socket.sendto(request, (server_ip, udp_port))
            received_packets = set()
            total_packets = None
            bytes_received = 0

            while self.is_running:
                try:
                    data, _ = udp_socket.recvfrom(Config.CLIENT_BUFFER_SIZE)
                    if len(data) < struct.calcsize(Config.PAYLOAD_STRUCT_FORMAT):
                        continue

                    header = data[:struct.calcsize(Config.PAYLOAD_STRUCT_FORMAT)]
                    payload = data[struct.calcsize(Config.PAYLOAD_STRUCT_FORMAT):]
                    magic_cookie, message_type, total_packets, packet_number = struct.unpack(
                        Config.PAYLOAD_STRUCT_FORMAT, header
                    )
                    if magic_cookie != Config.MAGIC_COOKIE or message_type != Config.PAYLOAD_TYPE:
                        continue

                    received_packets.add(packet_number)
                    bytes_received += len(payload)


                except socket.timeout:
                    if total_packets and len(received_packets) == total_packets:
                        break
                    if time.time() - start_time > Config.TIMEOUT:
                        break

            end_time = time.time()
            duration = end_time - start_time
            speed = (bytes_received * 8) / duration if duration > 0 else 0
            self.total_data_received+=bytes_received

            if total_packets:
                success_rate = (len(received_packets) / total_packets) * 100
                print(
                    f"  {Colors.GREEN}✓ UDP transfer #{connection_id} complete{Colors.ENDC}\n"
                    f"  {Colors.BLUE}├─ Received: {Colors.CYAN}{Format.format_size(bytes_received)}{Colors.ENDC}\n"
                    f"  {Colors.BLUE}├─ Time: {Colors.CYAN}{duration:.2f}s{Colors.ENDC}\n"
                    f"  {Colors.BLUE}├─ Speed: {Colors.CYAN}{Format.format_speed(speed)}{Colors.ENDC}\n"
                    f"  {Colors.BLUE}└─ Success rate: {Colors.CYAN}{success_rate:.1f}%{Colors.ENDC}\n"
                )

        except Exception as e:
            print(f"{Colors.RED}✗ UDP transfer #{connection_id} error: {e}{Colors.ENDC}\n")
            self.failed_transfers+=1
        finally:
            udp_socket.close()


if __name__ == "__main__":
    client = Client()
    print(f"{Colors.HEADER}{Colors.BOLD}Client Started{Colors.ENDC}")
    client.run()