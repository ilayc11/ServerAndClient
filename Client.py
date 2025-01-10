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
        print("\nShutting down client...")
        self.is_running = False
        self.transfers_completed = True

    def get_user_parameters(self):
        try:
            while True:
                try:
                    self.file_size = int(input("Enter file size to transfer (bytes): "))
                    self.tcp_connections = int(input("Enter number of TCP connections: "))
                    self.udp_connections = int(input("Enter number of UDP connections: "))

                    if self.file_size > 0 and self.tcp_connections >= 0 and self.udp_connections >= 0:
                        if self.tcp_connections + self.udp_connections > 0:
                            break
                    print("Please enter valid numbers (file size > 0, at least one connection)")
                except ValueError:
                    print("Please enter valid numbers")

            self.state = "LOOKING_FOR_SERVER"

        except KeyboardInterrupt:
            print("\nClient shutdown requested")
            sys.exit(0)

    def handle_tcp_transfer(self, server_ip, tcp_port, connection_id):
        for retry in range(MAX_RETRIES):
            tcp_socket = None
            try:
                start_time = time.time()
                tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                tcp_socket.settimeout(TIMEOUT)

                tcp_socket.connect((server_ip, tcp_port))
                tcp_socket.sendall(f"{self.file_size}\n".encode())

                bytes_received = 0
                while bytes_received < self.file_size and self.is_running:
                    chunk = tcp_socket.recv(BUFFER_SIZE)
                    if not chunk:
                        if bytes_received < self.file_size:
                            raise ConnectionError("Server closed connection prematurely")
                        break
                    bytes_received += len(chunk)

                end_time = time.time()
                duration = end_time - start_time
                speed = (bytes_received * 8) / duration if duration > 0 else 0

                print(f"TCP transfer #{connection_id} finished, total time: {duration:.2f} seconds, "
                      f"total speed: {speed:.1f} bits/second")
                break

            except Exception as e:
                print(f"TCP transfer #{connection_id} error: {e}")
                if retry < MAX_RETRIES - 1:
                    print(f"Retrying TCP transfer #{connection_id}...")
                    time.sleep(1)
            finally:
                if tcp_socket:
                    tcp_socket.close()

    def handle_udp_transfer(self, server_ip, udp_port, connection_id):
        try:
            start_time = time.time()
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.settimeout(1)

            request = struct.pack(">IBQ", MAGIC_COOKIE, 0x3, self.file_size)
            udp_socket.sendto(request, (server_ip, udp_port))

            received_packets = set()
            total_packets = None
            bytes_received = 0

            while self.is_running:
                try:
                    data, _ = udp_socket.recvfrom(BUFFER_SIZE)
                    if len(data) < struct.calcsize(">IBQQ"):
                        continue

                    header = data[:struct.calcsize(">IBQQ")]
                    payload = data[struct.calcsize(">IBQQ"):]
                    magic_cookie, message_type, total_packets, packet_number = struct.unpack(
                        ">IBQQ", header
                    )

                    if magic_cookie != MAGIC_COOKIE or message_type != 0x4:
                        continue

                    received_packets.add(packet_number)
                    bytes_received += len(payload)

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
                print(f"UDP transfer #{connection_id} finished, total time: {duration:.2f} seconds, "
                      f"total speed: {speed:.1f} bits/second, "
                      f"percentage of packets received successfully: {success_rate:.1f}%")

        except Exception as e:
            print(f"UDP transfer #{connection_id} error: {e}")
        finally:
            udp_socket.close()

    def start_speed_test(self):
        self.transfer_threads = []

        for i in range(self.tcp_connections):
            thread = threading.Thread(
                target=self.handle_tcp_transfer,
                args=(self.current_server[0], self.current_server[2], i + 1)
            )
            self.transfer_threads.append(thread)
            thread.start()

        for i in range(self.udp_connections):
            thread = threading.Thread(
                target=self.handle_udp_transfer,
                args=(self.current_server[0], self.current_server[1], i + 1)
            )
            self.transfer_threads.append(thread)
            thread.start()

        for thread in self.transfer_threads:
            thread.join()

        print("All transfers complete!")
        self.transfers_completed = True

    def run(self):
        print("Speed Test Client Started")
        self.get_user_parameters()

        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.bind(("", UDP_PORT))
        udp_socket.settimeout(1)

        print("Client started, listening for offer requests...")

        while not self.transfers_completed and self.is_running:
            try:
                data, address = udp_socket.recvfrom(BUFFER_SIZE)
                magic_cookie, message_type, udp_port, tcp_port = struct.unpack('>IBHH', data)

                if magic_cookie == MAGIC_COOKIE and message_type == OFFER_TYPE:
                    print(f"Received offer from {address[0]}")
                    self.current_server = (address[0], udp_port, tcp_port)
                    self.start_speed_test()
                    break  # Exit after completing transfers

            except socket.timeout:
                continue

            except Exception as e:
                print(f"Error: {e}")
                time.sleep(1)


        print("Client shutting down...")
        udp_socket.close()
        sys.exit(0)

if __name__ == "__main__":
    client = SpeedTestClient()
    client.run()
