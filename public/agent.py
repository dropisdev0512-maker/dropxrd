"""
DropX PC Agent
==============
The little server that runs on your PC and answers DropX's commands.

How to run:
  1. Install Python from python.org (tick "Add Python to PATH" during install).
  2. Open a terminal in this folder and run:  python agent.py
  3. Leave the window open. If the dot in DropX turns green, you're connected.

No extra packages needed — it uses only what Python ships with.
"""

import json
import os
import platform
import socket
import struct
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8765
WOL_MAC = ""  # Optional: "AA-BB-CC-DD-EE-FF" to wake a specific machine. Empty = this PC's MAC.

SYSTEM = platform.system()  # "Windows", "Linux" or "Darwin"
SHUTDOWN_TIMER = {"active": False}


def log(msg: str) -> None:
    print(f"[agent] {msg}", flush=True)


def send_wol(mac_hex: str) -> None:
    """Send a Wake-on-LAN magic packet on the local network."""
    mac = mac_hex.replace(":", "").replace("-", "").replace(".", "")
    if len(mac) != 12:
        raise ValueError("invalid MAC address")
    packet = b"\xff" * 6 + bytes.fromhex(mac) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(packet, ("255.255.255.255", 9))
        # Also try the Tailscale subnet broadcast, if one exists.
        try:
            s.sendto(packet, ("100.100.100.255", 9))
        except OSError:
            pass


def do_shutdown(delay: int) -> None:
    SHUTDOWN_TIMER["active"] = True
    if SYSTEM == "Windows":
        subprocess.run(["shutdown", "/s", "/t", str(delay)], check=False)
    elif SYSTEM == "Linux":
        subprocess.run(["shutdown", "-h", f"+{max(1, delay // 60)}"], check=False)
    elif SYSTEM == "Darwin":
        subprocess.run(["osascript", "-e", f'delay {delay} do shell script "shutdown -h now"'], check=False)


def do_cancel_shutdown() -> None:
    SHUTDOWN_TIMER["active"] = False
    if SYSTEM == "Windows":
        subprocess.run(["shutdown", "/a"], check=False)
    elif SYSTEM == "Linux":
        subprocess.run(["shutdown", "-c"], check=False)


def do_open(target: str, window_title: str) -> None:
    if SYSTEM == "Windows":
        if os.path.exists(target):
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            # Treat it as a command / app name, e.g. "code", "spotify"
            subprocess.Popen(["cmd", "/c", "start", "", target], shell=False)
    elif SYSTEM == "Darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])


def do_call(message: str) -> None:
    def popup() -> None:
        try:
            if SYSTEM == "Windows":
                import winsound
                winsound.MessageBeep()
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, message, "DropX", 0x40)
            else:
                print("\a", flush=True)
        except Exception as exc:
            log(f"call popup failed: {exc}")

    threading.Thread(target=popup, daemon=True).start()


def do_scaffold(kind: str, target: str) -> str:
    base = os.path.abspath(os.path.expanduser(target))
    os.makedirs(base, exist_ok=True)

    if kind == "python-cli":
        with open(os.path.join(base, "main.py"), "w", encoding="utf-8") as f:
            f.write('def main():\n    print("Hello from DropX scaffold!")\n\n\nif __name__ == "__main__":\n    main()\n')
        with open(os.path.join(base, "requirements.txt"), "w", encoding="utf-8") as f:
            f.write("")
        readme = "# Python CLI\n\nRun with: python main.py\n"
    elif kind == "fabric-mod":
        os.makedirs(os.path.join(base, "src", "main", "java", "com", "example"), exist_ok=True)
        with open(os.path.join(base, "src", "main", "java", "com", "example", "ExampleMod.java"), "w", encoding="utf-8") as f:
            f.write("package com.example;\n\npublic class ExampleMod {\n    // mod entry point\n}\n")
        with open(os.path.join(base, "fabric.mod.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"schemaVersion": 1, "id": "examplemod", "version": "1.0.0"}, indent=2))
        readme = "# Fabric Mod\n\nOpen in IntelliJ and build with Gradle.\n"
    elif kind == "web":
        with open(os.path.join(base, "index.html"), "w", encoding="utf-8") as f:
            f.write("<!doctype html>\n<html>\n<head><title>Web App</title></head>\n<body>\n  <h1>Hello</h1>\n</body>\n</html>\n")
        with open(os.path.join(base, "styles.css"), "w", encoding="utf-8") as f:
            f.write("body { font-family: system-ui; }\n")
        readme = "# Web Project\n\nOpen index.html in a browser.\n"
    else:
        raise ValueError(f"unknown scaffold kind: {kind}")

    with open(os.path.join(base, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)
    return f"scaffolded {kind} at {base}"


def do_qa(path: str) -> dict:
    base = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(base):
        return {"ok": False, "error": f"path not found: {base}"}
    file_count = 0
    py_files = 0
    for root, _dirs, files in os.walk(base):
        for name in files:
            file_count += 1
            if name.endswith(".py"):
                py_files += 1
    has_readme = os.path.exists(os.path.join(base, "README.md"))
    return {"ok": True, "files": file_count, "python_files": py_files, "has_readme": has_readme}


class Handler(BaseHTTPRequestHandler):
    server_version = "DropXAgent/1.0"

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        super().end_headers()

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/status":
            self._json({"ok": True, "host": socket.gethostname(), "platform": SYSTEM})
        else:
            self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        body = self._read_body()
        try:
            if self.path == "/wake":
                mac = WOL_MAC or str(uuid.getnode())
                send_wol(mac)
                log("wake: magic packet sent")
                self._json({"ok": True, "message": "magic packet sent"})

            elif self.path == "/shutdown":
                delay = int(body.get("delay") or 30)
                do_shutdown(delay)
                log(f"shutdown in {delay}s")
                self._json({"ok": True, "message": f"shutting down in {delay} seconds"})

            elif self.path == "/shutdown/cancel":
                do_cancel_shutdown()
                log("shutdown cancelled")
                self._json({"ok": True, "message": "shutdown cancelled"})

            elif self.path == "/scaffold":
                msg = do_scaffold(str(body.get("kind") or ""), str(body.get("target") or ""))
                log(f"scaffold: {msg}")
                self._json({"ok": True, "message": msg})

            elif self.path == "/qa":
                self._json(do_qa(str(body.get("path") or "")))

            elif self.path == "/open":
                do_open(str(body.get("target") or ""), str(body.get("window") or ""))
                log(f"open: {body.get('target')}")
                self._json({"ok": True, "message": f"opened {body.get('target')}"})

            elif self.path == "/call":
                do_call(str(body.get("message") or ""))
                log(f"call: {body.get('message')}")
                self._json({"ok": True, "message": "called"})

            elif self.path == "/dropx":
                self._json({"ok": True, "message": "Yes Drop, Sirr!"})

            else:
                self._json({"ok": False, "error": "not found"}, 404)

        except Exception as exc:
            log(f"error on {self.path}: {exc}")
            self._json({"ok": False, "error": str(exc)}, 500)


if __name__ == "__main__":
    log(f"DropX agent listening on 0.0.0.0:{PORT} ({SYSTEM})")
    try:
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        log("bye")
