from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def healthy(url):
    try:
        with urllib.request.urlopen(url + "/_stcore/health", timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def main():
    folder = ROOT / "DAILY_BASEBALL"
    folder.mkdir(exist_ok=True)
    state_file = folder / "dashboard.json"
    try:
        saved = json.loads(state_file.read_text())
        os.kill(int(saved["pid"]), 0)
        url = f"http://localhost:{int(saved['port'])}"
        if 8510 <= int(saved["port"]) < 8530 and healthy(url):
            webbrowser.open(url)
            print(url)
            return
    except (OSError, ValueError, KeyError):
        pass
    port = 8510
    while port < 8530:
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                break
        port += 1
    if port == 8530:
        raise SystemExit("No free dashboard port between 8510 and 8529.")
    with (folder / "dashboard.log").open("a") as log:
        process = subprocess.Popen([sys.executable, "-B", "-m", "streamlit", "run", str(ROOT / "scripts/daily_baseball_app.py"),
                                    "--server.address", "127.0.0.1", "--server.port", str(port), "--server.headless", "true"], cwd=ROOT,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    url = f"http://localhost:{port}"
    for _ in range(50):
        if healthy(url):
            state_file.write_text(json.dumps({"pid": process.pid, "port": port}))
            webbrowser.open(url)
            print(url)
            return
        time.sleep(.2)
    raise SystemExit("Dashboard did not start. See DAILY_BASEBALL/dashboard.log.")


if __name__ == "__main__":
    main()
