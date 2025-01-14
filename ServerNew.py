import socket
import time
import struct
import threading
import sys
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Manager
from Config import Colors, Config, Format
import math


class Server:
    def __init__(self):
        try:
            #statistics
            self.total_tcp_data_sent = 0
            self.total_udp_data_sent = 0
            self.tcp_connections = 0
            self.udp_connections = 0
            self.transfer_errors = 0


            #other things
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_socket.bind(('', 0))
            self.tcp_socket.settimeout(1.0)
            self.SERVER_TCP_PORT = self.tcp_socket.getsockname()[1]

            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.bind(('', 0))
            self.udp_socket.settimeout(1.0)
            self.SERVER_UDP_PORT = self.udp_socket.getsockname()[1]

            # Get server IP (unchanged)
            hostname = socket.gethostname()
            self.SERVER_IP = socket.gethostbyname(hostname)

            self.tcp_socket.listen(Config.MAX_CLIENTS)

            # Replace lock and dictionary with thread-safe dictionary
            manager = Manager()
            self.active_clients = manager.dict()

            self.is_running = True
            self.thread_pool = ThreadPoolExecutor(max_workers=Config.MAX_CLIENTS)

            print(f"{Colors.BLUE}Server IP address: {Colors.CYAN}{self.SERVER_IP}{Colors.ENDC}")
            print(f"{Colors.BLUE}TCP Port: {Colors.CYAN}{self.SERVER_TCP_PORT}{Colors.ENDC}")
            print(f"{Colors.BLUE}UDP Port: {Colors.CYAN}{self.SERVER_UDP_PORT}{Colors.ENDC}")

        except Exception as e:
            print(f"{Colors.RED}Failed to initialize server: {e}{Colors.ENDC}\n")
            sys.exit(1)

    def print_statistics(self):
        print(f"{Colors.GREEN}{Colors.BOLD}Server Statistics:{Colors.ENDC}")
        print(
            f"{Colors.BLUE}Total TCP data sent: {Colors.CYAN}{Format.format_size(self.total_tcp_data_sent)}{Colors.ENDC}")
        print(
            f"{Colors.BLUE}Total UDP data sent: {Colors.CYAN}{Format.format_size(self.total_udp_data_sent)}{Colors.ENDC}")
        print(f"{Colors.BLUE}TCP connections handled: {Colors.CYAN}{self.tcp_connections}{Colors.ENDC}")
        print(f"{Colors.BLUE}UDP connections handled: {Colors.CYAN}{self.udp_connections}{Colors.ENDC}")
        print(f"{Colors.RED}Transfer errors: {Colors.CYAN}{self.transfer_errors}{Colors.ENDC}")

    def run(self):
        try:
            # Start broadcast and UDP handler threads
            threading.Thread(target=self.offer_broadcast, daemon=True).start()
            threading.Thread(target=self.handle_udp_requests, daemon=True).start()
            threading.Thread(target=self.periodic_statistics, daemon=True).start()
            print(f"{Colors.GREEN}Server is running and listening on IP address {self.SERVER_IP}{Colors.ENDC}")
            while True:  # Keep the server running indefinitely
                try:
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


    def offer_broadcast(self):
        udp_broadcast = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_broadcast.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_broadcast.bind(("",0))

        while self.is_running:
            try:
                message = struct.pack(Config.OFFER_STRUCT_FORMAT,
                                      Config.MAGIC_COOKIE,
                                      Config.OFFER_TYPE,
                                      self.SERVER_UDP_PORT,
                                      self.SERVER_TCP_PORT)
                udp_broadcast.sendto(message, ('<broadcast>', Config.OFFER_UDP_PORT))
                time.sleep(1)

            except Exception as e:
                print(f"{Colors.RED}Broadcast error: {e}{Colors.ENDC}")
                time.sleep(1)
        udp_broadcast.close()


    def track_client(self, client_address, conn_type):
        if client_address not in self.active_clients:
            self.active_clients[client_address] = {'tcp_count': 0, 'udp_count': 0}

        client_data = self.active_clients[client_address]
        client_data[f'{conn_type}_count'] += 1
        self.active_clients[client_address] = client_data

    def untrack_client(self, client_address, conn_type):
        if client_address in self.active_clients:
            client_data = self.active_clients[client_address]
            client_data[f'{conn_type}_count'] -= 1
            if sum(client_data.values()) == 0:
                del self.active_clients[client_address]
            else:
                self.active_clients[client_address] = client_data

    def handle_tcp_client(self, connection, address):
        self.track_client(address[0], 'tcp')
        self.tcp_connections+=1
        connection.settimeout(30)

        try:
            request = connection.recv(Config.SERVER_BUFFER_SIZE).decode().strip()
            if not request:
                return

            file_size = int(request)
            if file_size <= 0:
                return

            print(f"{Colors.GREEN}➜ New TCP client connected from {Colors.CYAN}{address}{Colors.ENDC}")
            print(f"{Colors.BLUE}Requested size: {Colors.CYAN}{Format.format_size(file_size)}{Colors.ENDC}")
            bytes_sent = 0
            start_time = time.time()

            def generate_data():
                for _ in range(file_size // Config.CHUNK_SIZE):
                    yield b'A' * Config.CHUNK_SIZE
                # Handle the remainder
                yield b'A' * (file_size % Config.CHUNK_SIZE)

            for chunk in generate_data():
                try:

                    connection.sendall(chunk)
                    bytes_sent += len(chunk)
                except socket.timeout:
                    break
            self.total_tcp_data_sent += bytes_sent

            duration = time.time() - start_time
            speed = (bytes_sent * 8) / duration if duration > 0 else 0

            print(
                f"{Colors.GREEN}✓ TCP transfer complete to {Colors.CYAN}{address}{Colors.ENDC}\n"
                f"  {Colors.BLUE}├─ Sent: {Colors.CYAN}{Format.format_size(bytes_sent)}{Colors.ENDC}\n"
                f"  {Colors.BLUE}├─ Time: {Colors.CYAN}{duration:.2f}s{Colors.ENDC}\n"
                f"  {Colors.BLUE}└─ Speed: {Colors.CYAN}{Format.format_speed(speed)}{Colors.ENDC}"
            )

        except Exception as e:
            print(f"{Colors.RED}✗ Error handling TCP client {address}: {e}{Colors.ENDC}")
            self.transfer_errors+=1
        finally:
            connection.close()
            self.untrack_client(address[0], 'tcp')

    def handle_udp_requests(self):
        while self.is_running:
            try:
                data, address = self.udp_socket.recvfrom(Config.SERVER_BUFFER_SIZE)

                if len(data) < struct.calcsize(Config.REQUEST_STRUCT_FORMAT):
                    continue

                self.track_client(address[0], 'udp')
                self.udp_connections+=1

                try:
                    magic_cookie, message_type, file_size = struct.unpack(Config.REQUEST_STRUCT_FORMAT, data)
                    if magic_cookie != Config.MAGIC_COOKIE or message_type != Config.REQUEST_TYPE:
                        continue

                    print(f"{Colors.GREEN}➜ New UDP request from {Colors.CYAN}{address}{Colors.ENDC}")
                    print(f"{Colors.BLUE}Requested size: {Colors.CYAN}{Format.format_size(file_size)}{Colors.ENDC}")

                    total_segments = math.ceil(file_size / Config.CHUNK_SIZE)
                    data_to_send=b'A'*file_size
                    start_time = time.time()
                    bytes_sent = 0

                    for segment_number in range(total_segments):
                        # Calculate payload for this segment
                        start = segment_number * Config.CHUNK_SIZE
                        end = start + Config.CHUNK_SIZE
                        payload = data_to_send[start:end]

                        response_format = f"{Config.PAYLOAD_STRUCT_FORMAT}{len(payload)}s"  # Struct format for the response
                        response_data = struct.pack(
                            response_format,
                            Config.MAGIC_COOKIE,  # Magic cookie (4 bytes)
                            Config.PAYLOAD_TYPE,  # Message type (1 byte)
                            total_segments,  # Total segment count (8 bytes)
                            segment_number + 1,  # Current segment number (8 bytes)
                            payload  # Actual payload (variable size)
                        )

                        # Send the response
                        self.udp_socket.sendto(response_data,address)
                        bytes_sent += len(response_data)


                    self.total_udp_data_sent+=bytes_sent
                    duration = time.time() - start_time
                    speed = (bytes_sent * 8) / duration if duration > 0 else 0
                    print(
                        f"{Colors.GREEN}✓ UDP transfer complete to {Colors.CYAN}{address}{Colors.ENDC}\n"
                        f"  {Colors.BLUE}├─ Sent: {Colors.CYAN}{Format.format_size(bytes_sent)}{Colors.ENDC}\n"
                        f"  {Colors.BLUE}├─ Packets: {Colors.CYAN}{total_segments}{Colors.ENDC}\n"
                        f"  {Colors.BLUE}├─ Time: {Colors.CYAN}{duration:.2f}s{Colors.ENDC}\n"
                        f"  {Colors.BLUE}└─ Speed: {Colors.CYAN}{Format.format_speed(speed)}{Colors.ENDC}"
                    )

                except Exception as e:
                    print(f"{Colors.RED}✗ UDP transfer error to {address}: {e}{Colors.ENDC}")
                finally:
                    self.untrack_client(address[0], 'udp')

            except socket.timeout:
                continue
            except Exception as e:
                print(f"{Colors.RED}✗ UDP handler error: {e}{Colors.ENDC}")
                self.transfer_errors += 1
                time.sleep(1)

    def periodic_statistics(self):
        while self.is_running:
            time.sleep(10)  # Print statistics every 10 seconds
            self.print_statistics()


if __name__ == '__main__':
    server = Server()
    print(f"{Colors.HEADER}{Colors.BOLD}Server Started{Colors.ENDC}")
    server.run()