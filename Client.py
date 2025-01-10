import socket
import struct
import threading
import time
from datetime import datetime
import sys

# Constants
MAGIC_COOKIE = 0xabcddcba
OFFER_TYPE = 0x2
UDP_PORT = 13117
BUFFER_SIZE = 1024


class SpeedTestClient:
    def __init__(self):
        self.state = "STARTUP"
        self.current_server = None
        self.transfer_threads = []
        self.transfers_completed = False

    def get_user_parameters(self):
        """Get test parameters from user."""
        while True:
            try:
                self.file_size = int(input("Enter file size to transfer (bytes): "))
                self.tcp_connections = int(input("Enter number of TCP connections: "))
                self.udp_connections = int(input("Enter number of UDP connections: "))
                if all(x >= 0 for x in [self.file_size, self.tcp_connections, self.udp_connections]):
                    break
                print("Please enter non-negative numbers")
            except ValueError:
                print("Please enter valid numbers")
        self.state = "LOOKING_FOR_SERVER"

    def handle_tcp_transfer(self, server_ip, tcp_port, connection_id):
        """Handle a single TCP transfer."""
        try:
            start_time = time.time()
            tcp_socket = socket.create_connection((server_ip, tcp_port))

            # Send file size request
            tcp_socket.sendall(f"{self.file_size}\n".encode())

            # Receive data
            bytes_received = 0
            while bytes_received < self.file_size:
                chunk = tcp_socket.recv(BUFFER_SIZE)
                if not chunk:
                    break
                bytes_received += len(chunk)

            end_time = time.time()
            duration = end_time - start_time
            speed = (bytes_received * 8) / duration  # bits per second

            print(f"\033[32mTCP transfer #{connection_id} finished, total time: {duration:.2f} seconds, "
                  f"total speed: {speed:.1f} bits/second\033[0m")

        except Exception as e:
            print(f"\033[31mError in TCP transfer #{connection_id}: {e}\033[0m")
        finally:
            tcp_socket.close()

    def handle_udp_transfer(self, server_ip, udp_port, connection_id):
        """Handle a single UDP transfer."""
        try:
            start_time = time.time()
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.settimeout(1)  # 1 second timeout as per requirements

            # Send request
            request = struct.pack(">IBQ", MAGIC_COOKIE, 0x3, self.file_size)
            udp_socket.sendto(request, (server_ip, udp_port))

            # Receive packets
            received_packets = set()
            total_packets = None
            bytes_received = 0

            while True:
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
                    break

            end_time = time.time()
            duration = end_time - start_time
            speed = (bytes_received * 8) / duration  # bits per second

            if total_packets:
                success_rate = (len(received_packets) / total_packets) * 100
                print(f"\033[34mUDP transfer #{connection_id} finished, total time: {duration:.2f} seconds, "
                      f"total speed: {speed:.1f} bits/second, "
                      f"percentage of packets received successfully: {success_rate:.1f}%\033[0m")

        except Exception as e:
            print(f"\033[31mError in UDP transfer #{connection_id}: {e}\033[0m")
        finally:
            udp_socket.close()

    def start_speed_test(self):
        """Start all transfers in parallel."""
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

        print("\033[33mAll transfers complete!\033[0m")
        self.transfers_completed = True

    def run(self):
        """Main client loop."""
        print("\033[36mSpeed Test Client Started\033[0m")

        # Initial setup
        self.get_user_parameters()

        # Create UDP socket for offers
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.bind(("", UDP_PORT))
        udp_socket.settimeout(1)  # Add timeout to allow checking transfers_completed flag

        print("\033[36mClient started, listening for offer requests...\033[0m")

        while not self.transfers_completed:
            try:
                # Wait for offer
                data, address = udp_socket.recvfrom(BUFFER_SIZE)
                magic_cookie, message_type, udp_port, tcp_port = struct.unpack('>IBHH', data)

                if magic_cookie == MAGIC_COOKIE and message_type == OFFER_TYPE:
                    print(f"\033[32mReceived offer from {address[0]}\033[0m")
                    self.current_server = (address[0], udp_port, tcp_port)
                    self.start_speed_test()

            except socket.timeout:
                continue  # Continue waiting if no offer received
            except Exception as e:
                print(f"\033[31mError: {e}\033[0m")
                time.sleep(1)  # Prevent tight loop on error

        print("\033[36mClient shutting down...\033[0m")
        udp_socket.close()
        sys.exit(0)


if __name__ == "__main__":
    client = SpeedTestClient()
    client.run()