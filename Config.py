
class Config:
    MAGIC_COOKIE = 0xabcddcba

    OFFER_TYPE = 0x2
    REQUEST_TYPE=0x3
    PAYLOAD_TYPE=0x4

    OFFER_STRUCT_FORMAT="!IBHH"
    REQUEST_STRUCT_FORMAT="!IBQ"
    PAYLOAD_STRUCT_FORMAT="!IBQQ"

    OFFER_UDP_PORT = 13117

    CLIENT_BUFFER_SIZE = 4096
    SERVER_BUFFER_SIZE = 4096

    MAX_CLIENTS=5
    CHUNK_SIZE = 1024
    MAX_RETRIES=3

    TIMEOUT=3

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

class Format:
    @staticmethod
    def format_size(size_bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"

    @staticmethod
    def format_speed(bits_per_second):
        for unit in ['bps', 'Kbps', 'Mbps', 'Gbps']:
            if bits_per_second < 1000.0:
                return f"{bits_per_second:.2f} {unit}"
            bits_per_second /= 1000.0
        return f"{bits_per_second:.2f} Tbps"
