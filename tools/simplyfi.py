import socket
import sys


def is_printable(text: bytearray) -> bool:
    for ch in text:
        if ch != 0xff and ch not in (ord('\r'), ord('\n'), ord('\t')):
            if not (0x20 <= ch <= 0x7E):
                return False
    return True

def find_xor_key(data: bytes, known_plaintext: str) -> str:
    known_bytes = known_plaintext.encode('utf-8')
    if len(known_bytes) > 17:
        print("error: The length of the known plaintext is greater than 16!", file=sys.stderr)
        return ""

    search_bytes = known_bytes[:16] if len(known_bytes) == 17 else known_bytes

    for pp in range(len(data) - len(search_bytes) + 1):
        partial_key = bytearray()
        for j in range(len(search_bytes)):
            partial_key.append(data[pp + j] ^ search_bytes[j])

        if is_printable(partial_key):
            for kl in range(len(partial_key), 17):
                for kp in range(kl):
                    expanded_key = bytearray(partial_key)
                    expanded_key.extend([0xff] * (kl - len(partial_key)))
                    expanded_key = expanded_key[kp:] + expanded_key[:kp]

                    decrypted_text = bytearray()
                    for x in range(len(data)):
                        k_byte = expanded_key[x % len(expanded_key)]
                        if k_byte == 0xff:
                            decrypted_text.append(0xff)
                        else:
                            decrypted_text.append(data[x] ^ k_byte)

                    if is_printable(decrypted_text):
                        if known_bytes in decrypted_text:
                            key_str = "".join(chr(c) for c in expanded_key if c != 0xff)
                            return key_str[:16]
    return ""

def find_xor_key_list(data: bytes, known_plaintexts: list) -> str:
    for kp in known_plaintexts:
        key = find_xor_key(data, kp)
        if key:
            return key
    return ""

def get_candy_simplyfi_data(device_ip: str, method: str, port: int = 80) -> bytes:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(10)
            sock.connect((device_ip, port))
            message = f"GET /http-{method}.json?encrypted=1 HTTP/1.1\nHost: {device_ip}\n\nConnection: close\r\n\r\n"
            sock.sendall(message.encode('utf-8'))

            response = b""
            while True:
                data = sock.recv(1024)
                if not data:
                    break
                response += data

        hex_content = response.decode('utf-8', errors='ignore')
        last_newline_idx = max(hex_content.rfind('\n'), hex_content.rfind('\r'))
        if last_newline_idx != -1:
            hex_content = hex_content[last_newline_idx + 1:]

        hex_content = hex_content.strip()
        if len(hex_content) % 2 == 1:
            hex_content = "0" + hex_content

        return bytes.fromhex(hex_content)
    except Exception as e:
        print(f"error: get_candySimplify_data, could not get data from server - {e}", file=sys.stderr)
        return b""

def xor_string(data: bytes, key: str) -> str:
    key_bytes = key.encode('utf-8')
    decrypted = bytearray()
    for i, b in enumerate(data):
        decrypted.append(b ^ key_bytes[i % len(key_bytes)])
    return decrypted.decode('utf-8', errors='ignore')

def show_header(error: bool = False):
    out = sys.stderr if error else sys.stdout
    print("## Candy Simply-Fi tool by Melvin Groenendaal ## (Python Port)", file=out)

def main():
    if (len(sys.argv) == 3 and sys.argv[2] != "getkey") or len(sys.argv) < 3 or len(sys.argv) > 4:
        show_header(True)
        print(f"Usage to retreive key: {sys.argv[0]} <ip> getkey", file=sys.stderr)
        print(f"Usage to get data    : {sys.argv[0]} <ip> <key> <method: config, getStatistics, read>", file=sys.stderr)
        sys.exit(-1)

    if sys.argv[2] == "getkey":
        show_header()
        data = get_candy_simplyfi_data(sys.argv[1], "read")
        if not data:
            print("error: get_candySimplify_data, could not get data from server", file=sys.stderr)
            sys.exit(-2)

        key = find_xor_key_list(data, [
            "{\"WiFiStatus\":\"0\"",
            "{\"WiFiStatus\":\"1\"",
            "{\"StatoWiFi\":\"0\"",
            "{\"StatoWiFi\":\"1\"",
            "\"CheckUpState\":\""
        ])

        if not key:
            print("error: find_xor_key_list, could not find key", file=sys.stderr)
            sys.exit(-3)
        else:
            print(f"Found key: {key}")
    else:
        ip = sys.argv[1]
        key = sys.argv[2]
        method = sys.argv[3]

        data = get_candy_simplyfi_data(ip, method)
        if not data:
            print("error: get_candySimplify_data, could not get data from server", file=sys.stderr)
            sys.exit(-4)

        print(xor_string(data, key))

if __name__ == "__main__":
    main()
