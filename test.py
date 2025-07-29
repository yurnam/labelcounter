import socket
import time
import requests

PRINTER_IP = "10.10.10.221"
PRINTER_PORT = 9100
ZPL_FEED = "^XA^FO0,0^GB1,1,1^FS^XZ\n"
STATUS_URL = f"http://{PRINTER_IP}/index.html"
MEDIA_OUT_TEXT = "Fehler: KEIN PAPIER"
CANCEL_ALL_CMD = "~JA\n"  # Cancel all print jobs on the printer

def is_media_out():
    try:
        response = requests.get(STATUS_URL, timeout=2)
        if MEDIA_OUT_TEXT in response.text:
            print("[!] Detected media out from web interface.")
            return True
        return False
    except requests.RequestException as e:
        print(f"[!] Error fetching status page: {e}")
        return False  # Fail-safe: assume paper is present if unreachable

def feed_labels_until_web_detects_media_out():
    label_count = 0
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((PRINTER_IP, PRINTER_PORT))
            print("[✓] Connected to printer.")
            # Cancel any queued jobs before starting
            s.send(CANCEL_ALL_CMD.encode("utf-8"))
            print("[✓] Sent cancel all jobs command.")
            time.sleep(0.5)

            while True:
                # 1. Check web status before printing
                if is_media_out():
                    print("[!] Stopping: Media is already out.")
                    break

                # 2. Feed one label
                s.send(ZPL_FEED.encode("utf-8"))
                label_count += 1
                print(f"[✓] Fed label {label_count}")
                time.sleep(0.5)  # Let printer process before next check

                # 3. Stop when media runs out after printing
                if is_media_out():
                    print("[!] Media ran out while printing.")
                    break

    except Exception as e:
        print(f"[!] Connection error: {e}")

    print(f"\n[✔] Done. Total labels fed: {label_count}")

if __name__ == "__main__":
    feed_labels_until_web_detects_media_out()
