"""
DropX PC Agent (FastAPI)
========================
The brain + executor that runs on your PC. The phone app is a dumb terminal:
it sends what you said, this file decides what it means and does it.

SETUP
  1. Install Python 3.9+ from python.org (tick "Add Python to PATH").
  2. In a terminal in this folder:
        pip install fastapi uvicorn
  3. Start it:
        python agent.py
  4. Leave the window open. The dot in DropX turns green when connected.

Open http://localhost:8765/docs in a browser to poke every endpoint by hand.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI, Request, UploadFile, File
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
except ImportError:  # pragma: no cover
    raise SystemExit("Missing packages. Run:  pip install fastapi uvicorn")

PORT = 8765
OWNER = "Drop"
WOL_MAC = ""  # e.g. "AA-BB-CC-DD-EE-FF". Empty = this machine's MAC.
SYSTEM = platform.system()  # Windows / Linux / Darwin
HOME = os.path.expanduser("~")
DROPX_DIR = os.path.join(HOME, "DropX")
UPLOAD_DIR = os.path.join(DROPX_DIR, "uploads")
NOTES_FILE = os.path.join(DROPX_DIR, "notes.json")
REMINDERS_FILE = os.path.join(DROPX_DIR, "reminders.json")
MODS_DIR = os.path.join(DROPX_DIR, "mods")
HISTORY: List[Dict[str, Any]] = []
CALL_LOG: List[Dict[str, Any]] = []
MOD_JOBS: Dict[str, Dict[str, Any]] = {}

for _d in (DROPX_DIR, UPLOAD_DIR, MODS_DIR):
    os.makedirs(_d, exist_ok=True)

app = FastAPI(title="DropX Agent", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def log(msg: str) -> None:
    print(f"[dropx] {msg}", flush=True)


def now() -> str:
    return datetime.now().strftime("%H:%M")


def run(cmd: List[str] | str, shell: bool = False) -> str:
    try:
        out = subprocess.run(
            cmd, shell=shell, capture_output=True, text=True, timeout=25
        )
        return (out.stdout or out.stderr or "").strip()
    except Exception as exc:
        return f"error: {exc}"


def powershell(script: str) -> str:
    if SYSTEM != "Windows":
        return ""
    return run(["powershell", "-NoProfile", "-Command", script])


def load_json(path: str, fallback: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ───────────────────────────── actions ─────────────────────────────

def act_wake() -> str:
    mac = WOL_MAC or f"{uuid.getnode():012x}"
    mac = mac.replace(":", "").replace("-", "").replace(".", "")
    if len(mac) != 12:
        raise ValueError("invalid MAC address")
    packet = b"\xff" * 6 + bytes.fromhex(mac) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for addr in ("255.255.255.255", "100.100.100.255"):
            try:
                s.sendto(packet, (addr, 9))
            except OSError:
                pass
    return "magic packet sent"


def act_shutdown(delay: int = 30) -> str:
    if SYSTEM == "Windows":
        run(["shutdown", "/s", "/t", str(max(0, delay))])
    elif SYSTEM == "Linux":
        run(["shutdown", "-h", f"+{max(1, delay // 60)}"])
    else:
        run(["osascript", "-e", f'delay {delay}\ndo shell script "shutdown -h now"'])
    return f"shutting down in {delay} seconds"


def act_cancel_shutdown() -> str:
    if SYSTEM == "Windows":
        run(["shutdown", "/a"])
    elif SYSTEM == "Linux":
        run(["shutdown", "-c"])
    return "shutdown cancelled"


def act_lock() -> str:
    if SYSTEM == "Windows":
        run(["rundll32.exe", "user32.dll,LockWorkStation"])
    elif SYSTEM == "Darwin":
        run(["pmset", "displaysleepnow"])
    else:
        run("loginctl lock-session || xdg-screensaver lock", shell=True)
    return "locked"


def act_sleep() -> str:
    if SYSTEM == "Windows":
        run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
    elif SYSTEM == "Darwin":
        run(["pmset", "sleepnow"])
    else:
        run(["systemctl", "suspend"])
    return "going to sleep"


def act_screenshot() -> str:
    path = os.path.join(DROPX_DIR, f"shot-{int(time.time())}.png")
    if SYSTEM == "Windows":
        powershell(
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
            "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
            "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height; "
            "$g=[System.Drawing.Graphics]::FromImage($bmp); "
            "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size); "
            f"$bmp.Save('{path}')"
        )
    elif SYSTEM == "Darwin":
        run(["screencapture", path])
    else:
        run(["import", "-window", "root", path])
    return f"screenshot saved to {path}" if os.path.exists(path) else "screenshot failed"


def act_volume(direction: str) -> str:
    direction = (direction or "up").lower()
    if SYSTEM == "Windows":
        keys = {"up": 0xAF, "down": 0xAE, "mute": 0xAD}
        code = keys.get(direction, 0xAF)
        repeat = 1 if direction == "mute" else 5
        powershell(
            "$w=New-Object -ComObject WScript.Shell; "
            + f"1..{repeat} | %{{ $w.SendKeys([char]{code}) }}"
        )
    elif SYSTEM == "Darwin":
        expr = {
            "up": "set volume output volume (output volume of (get volume settings) + 10)",
            "down": "set volume output volume (output volume of (get volume settings) - 10)",
            "mute": "set volume with output muted",
        }.get(direction, "")
        run(["osascript", "-e", expr])
    else:
        arg = {"up": "5%+", "down": "5%-", "mute": "toggle"}.get(direction, "5%+")
        run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", arg])
    return f"volume {direction}"


def act_brightness(level: int) -> str:
    level = max(0, min(100, int(level)))
    if SYSTEM == "Windows":
        powershell(
            "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
            f".WmiSetBrightness(1,{level})"
        )
    elif SYSTEM == "Linux":
        run(["brightnessctl", "set", f"{level}%"])
    return f"brightness {level}%"


def act_media(action: str) -> str:
    action = (action or "play").lower()
    if SYSTEM == "Windows":
        codes = {"play": 0xB3, "pause": 0xB3, "next": 0xB0, "prev": 0xB1, "stop": 0xB2}
        powershell(
            "$w=New-Object -ComObject WScript.Shell; "
            f"$w.SendKeys([char]{codes.get(action, 0xB3)})"
        )
    elif SYSTEM == "Linux":
        run(["playerctl", {"prev": "previous"}.get(action, action)])
    else:
        run(["osascript", "-e", 'tell application "Music" to playpause'])
    return f"media {action}"


def act_window(action: str) -> str:
    action = (action or "minimize").lower()
    if SYSTEM == "Windows":
        seq = {
            "minimize": "%{F9}",
            "minimize_all": "^{ESC}",
            "maximize": "% x",
            "close": "%{F4}",
            "switch": "%{TAB}",
        }.get(action, "%{F9}")
        powershell(f"$w=New-Object -ComObject WScript.Shell; $w.SendKeys('{seq}')")
    return f"window {action}"


def act_wifi(state: str) -> str:
    on = str(state).lower() in ("on", "true", "1", "enable")
    if SYSTEM == "Windows":
        run(["netsh", "interface", "set", "interface", "Wi-Fi",
             "enable" if on else "disable"])
    elif SYSTEM == "Darwin":
        run(["networksetup", "-setairportpower", "en0", "on" if on else "off"])
    else:
        run(["nmcli", "radio", "wifi", "on" if on else "off"])
    return f"wifi {'on' if on else 'off'}"


def act_bluetooth(state: str) -> str:
    on = str(state).lower() in ("on", "true", "1", "enable")
    if SYSTEM == "Linux":
        run(["rfkill", "unblock" if on else "block", "bluetooth"])
    elif SYSTEM == "Darwin":
        run(["blueutil", "-p", "1" if on else "0"])
    return f"bluetooth {'on' if on else 'off'}"


def act_battery() -> Dict[str, Any]:
    percent, charging = None, None
    if SYSTEM == "Windows":
        out = powershell(
            "(Get-WmiObject Win32_Battery | Select-Object -First 1 "
            "-ExpandProperty EstimatedChargeRemaining)"
        )
        m = re.search(r"\d+", out or "")
        percent = int(m.group()) if m else None
        st = powershell(
            "(Get-WmiObject Win32_Battery | Select-Object -First 1 "
            "-ExpandProperty BatteryStatus)"
        )
        charging = st.strip() == "2" if st.strip().isdigit() else None
    elif SYSTEM == "Darwin":
        out = run(["pmset", "-g", "batt"])
        m = re.search(r"(\d+)%", out)
        percent = int(m.group(1)) if m else None
        charging = "AC Power" in out
    else:
        base = "/sys/class/power_supply/BAT0"
        if os.path.exists(base):
            try:
                percent = int(open(f"{base}/capacity").read().strip())
                charging = "Charging" in open(f"{base}/status").read()
            except Exception:
                pass
    return {"percent": percent, "charging": charging}


def act_disk() -> Dict[str, Any]:
    target = "C:\\" if SYSTEM == "Windows" else "/"
    try:
        total, used, free = shutil.disk_usage(target)
        gb = 1024 ** 3
        return {
            "drive": target,
            "total_gb": round(total / gb, 1),
            "used_gb": round(used / gb, 1),
            "free_gb": round(free / gb, 1),
            "percent_used": round(used / total * 100),
        }
    except Exception as exc:
        return {"error": str(exc)}


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def act_net() -> Dict[str, Any]:
    online = False
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=2).close()
        online = True
    except Exception:
        pass
    return {"ip": local_ip(), "host": socket.gethostname(), "online": online,
            "wifi": online}


def act_processes(limit: int = 15) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if SYSTEM == "Windows":
        out = powershell(
            "Get-Process | Sort-Object -Descending WS | Select-Object -First "
            f"{limit} Name,Id,WS | ConvertTo-Json -Compress"
        )
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            rows = [
                {"name": p.get("Name"), "pid": p.get("Id"),
                 "memory_mb": round((p.get("WS") or 0) / 1048576, 1)}
                for p in data
            ]
        except Exception:
            pass
    else:
        out = run(["ps", "-eo", "comm,pid,rss", "--sort=-rss"])
        for line in out.splitlines()[1: limit + 1]:
            parts = line.split()
            if len(parts) >= 3:
                rows.append({"name": parts[0], "pid": int(parts[1]),
                             "memory_mb": round(int(parts[2]) / 1024, 1)})
    return rows


def act_kill(name: str) -> str:
    if not name:
        raise ValueError("no process name")
    if SYSTEM == "Windows":
        run(["taskkill", "/IM", name if name.endswith(".exe") else f"{name}.exe", "/F"])
    else:
        run(["pkill", "-f", name])
    return f"closed {name}"


def clipboard_get() -> str:
    if SYSTEM == "Windows":
        return powershell("Get-Clipboard")
    if SYSTEM == "Darwin":
        return run(["pbpaste"])
    return run("xclip -selection clipboard -o", shell=True)


def clipboard_set(text: str) -> str:
    if SYSTEM == "Windows":
        powershell(f"Set-Clipboard -Value {json.dumps(text)}")
    elif SYSTEM == "Darwin":
        subprocess.run(["pbcopy"], input=text, text=True, check=False)
    else:
        subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True,
                       check=False)
    return "copied to clipboard"


APP_ALIASES = {
    "chrome": {"Windows": "chrome", "Darwin": "Google Chrome", "Linux": "google-chrome"},
    "edge": {"Windows": "msedge", "Darwin": "Microsoft Edge", "Linux": "microsoft-edge"},
    "firefox": {"Windows": "firefox", "Darwin": "Firefox", "Linux": "firefox"},
    "vscode": {"Windows": "code", "Darwin": "Visual Studio Code", "Linux": "code"},
    "code": {"Windows": "code", "Darwin": "Visual Studio Code", "Linux": "code"},
    "spotify": {"Windows": "spotify", "Darwin": "Spotify", "Linux": "spotify"},
    "discord": {"Windows": "discord", "Darwin": "Discord", "Linux": "discord"},
    "notepad": {"Windows": "notepad", "Darwin": "TextEdit", "Linux": "gedit"},
    "explorer": {"Windows": "explorer", "Darwin": "Finder", "Linux": "nautilus"},
    "terminal": {"Windows": "wt", "Darwin": "Terminal", "Linux": "gnome-terminal"},
    "steam": {"Windows": "steam", "Darwin": "Steam", "Linux": "steam"},
    "minecraft": {"Windows": "Minecraft.exe", "Darwin": "Minecraft", "Linux": "minecraft-launcher"},
}

SITE_ALIASES = {
    "youtube": "https://youtube.com",
    "github": "https://github.com",
    "google": "https://google.com",
    "gmail": "https://mail.google.com",
    "instagram": "https://instagram.com",
    "whatsapp": "https://web.whatsapp.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "reddit": "https://reddit.com",
    "netflix": "https://netflix.com",
    "chatgpt": "https://chat.openai.com",
    "lovable": "https://lovable.dev",
    "spotify web": "https://open.spotify.com",
}


def act_url(url: str) -> str:
    if not url:
        raise ValueError("no url")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if SYSTEM == "Windows":
        subprocess.Popen(["cmd", "/c", "start", "", url])
    elif SYSTEM == "Darwin":
        subprocess.Popen(["open", url])
    else:
        subprocess.Popen(["xdg-open", url])
    return f"opened {url}"


def act_app(name: str) -> str:
    if not name:
        raise ValueError("no app name")
    key = name.strip().lower()
    target = APP_ALIASES.get(key, {}).get(SYSTEM, name)
    if SYSTEM == "Windows":
        subprocess.Popen(["cmd", "/c", "start", "", target])
    elif SYSTEM == "Darwin":
        subprocess.Popen(["open", "-a", target])
    else:
        subprocess.Popen([target])
    return f"opened {name}"


def act_open(target: str) -> str:
    if not target:
        raise ValueError("nothing to open")
    expanded = os.path.expanduser(target)
    if os.path.exists(expanded):
        if SYSTEM == "Windows":
            os.startfile(expanded)  # type: ignore[attr-defined]
        elif SYSTEM == "Darwin":
            subprocess.Popen(["open", expanded])
        else:
            subprocess.Popen(["xdg-open", expanded])
        return f"opened {expanded}"
    low = target.strip().lower()
    if low in SITE_ALIASES:
        return act_url(SITE_ALIASES[low])
    if "." in low and " " not in low:
        return act_url(target)
    return act_app(target)


def act_close() -> str:
    return act_window("close")


def act_call(reason: str = "manual") -> str:
    entry = {"id": uuid.uuid4().hex[:8], "reason": reason, "status": "popup",
             "time": now()}
    CALL_LOG.insert(0, entry)

    def popup() -> None:
        try:
            if SYSTEM == "Windows":
                import ctypes
                import winsound
                winsound.MessageBeep()
                ctypes.windll.user32.MessageBoxW(0, f"DropX: {reason}", "DropX", 0x40)
            elif SYSTEM == "Darwin":
                run(["osascript", "-e",
                     f'display notification "{reason}" with title "DropX"'])
            else:
                run(["notify-send", "DropX", reason])
                print("\a", flush=True)
        except Exception as exc:
            log(f"call popup failed: {exc}")

    threading.Thread(target=popup, daemon=True).start()
    return f"calling you: {reason}"


def act_notes_add(text: str) -> Dict[str, Any]:
    notes = load_json(NOTES_FILE, [])
    note = {"id": uuid.uuid4().hex[:8], "text": text,
            "created": datetime.now().isoformat(timespec="seconds")}
    notes.insert(0, note)
    save_json(NOTES_FILE, notes)
    return note


def act_reminder(text: str, when: str) -> Dict[str, Any]:
    items = load_json(REMINDERS_FILE, [])
    item = {"id": uuid.uuid4().hex[:8], "text": text, "when": when}
    items.append(item)
    save_json(REMINDERS_FILE, items)
    return item


def act_scaffold(kind: str, target: str) -> str:
    base = os.path.abspath(os.path.expanduser(target or os.path.join(DROPX_DIR, kind)))
    os.makedirs(base, exist_ok=True)
    if kind == "python-cli":
        open(os.path.join(base, "main.py"), "w", encoding="utf-8").write(
            'def main():\n    print("Hello from DropX!")\n\n\n'
            'if __name__ == "__main__":\n    main()\n'
        )
        open(os.path.join(base, "requirements.txt"), "w", encoding="utf-8").write("")
        readme = "# Python CLI\n\nRun: python main.py\n"
    elif kind == "web":
        open(os.path.join(base, "index.html"), "w", encoding="utf-8").write(
            "<!doctype html>\n<html><head><title>Web App</title>"
            '<link rel="stylesheet" href="styles.css"></head>\n'
            "<body><h1>Hello</h1></body></html>\n"
        )
        open(os.path.join(base, "styles.css"), "w", encoding="utf-8").write(
            "body { font-family: system-ui; }\n"
        )
        readme = "# Web project\n\nOpen index.html.\n"
    elif kind in ("fabric-mod", "forge-mod", "neoforge-mod"):
        return mod_new(kind.split("-")[0], "1.20.1", os.path.basename(base),
                       os.path.basename(base).lower(), "com.example", [])["message"]
    else:
        raise ValueError(f"unknown scaffold kind: {kind}")
    open(os.path.join(base, "README.md"), "w", encoding="utf-8").write(readme)
    return f"scaffolded {kind} at {base}"


def act_qa(path: str) -> Dict[str, Any]:
    base = os.path.abspath(os.path.expanduser(path or DROPX_DIR))
    if not os.path.isdir(base):
        return {"ok": False, "error": f"path not found: {base}"}
    files = py = java = 0
    for root, _dirs, names in os.walk(base):
        for n in names:
            files += 1
            if n.endswith(".py"):
                py += 1
            if n.endswith(".java"):
                java += 1
    return {"ok": True, "path": base, "files": files, "python_files": py,
            "java_files": java,
            "has_readme": os.path.exists(os.path.join(base, "README.md"))}


# ───────────────────────────── mods ─────────────────────────────

def mod_new(loader: str, version: str, name: str, mod_id: str, package: str,
            features: List[str]) -> Dict[str, Any]:
    job_id = uuid.uuid4().hex[:8]
    base = os.path.join(MODS_DIR, name or mod_id or job_id)
    MOD_JOBS[job_id] = {"job_id": job_id, "progress": 0, "state": "running",
                        "name": name, "loader": loader, "version": version,
                        "path": base, "log": []}

    def build() -> None:
        job = MOD_JOBS[job_id]
        steps = [
            ("creating folders", 15),
            ("writing metadata", 35),
            ("generating sources", 60),
            ("writing gradle files", 85),
            ("done", 100),
        ]
        try:
            pkg_path = os.path.join(base, "src", "main", "java",
                                    *(package or "com.example").split("."))
            os.makedirs(pkg_path, exist_ok=True)
            os.makedirs(os.path.join(base, "src", "main", "resources"), exist_ok=True)
            for label, pct in steps:
                job["log"].append(label)
                job["progress"] = pct
                if label == "writing metadata":
                    meta = {"schemaVersion": 1, "id": mod_id or "examplemod",
                            "version": "1.0.0", "name": name or "Example Mod",
                            "environment": "*",
                            "depends": {"minecraft": version or "1.20.1"}}
                    fname = "fabric.mod.json" if loader == "fabric" else "mods.toml"
                    out = os.path.join(base, "src", "main", "resources", fname)
                    if loader == "fabric":
                        save_json(out, meta)
                    else:
                        open(out, "w", encoding="utf-8").write(
                            f'modLoader="javafml"\nloaderVersion="[40,)"\n'
                            f'[[mods]]\nmodId="{mod_id}"\nversion="1.0.0"\n'
                            f'displayName="{name}"\n'
                        )
                if label == "generating sources":
                    cls = (name or "Example").replace(" ", "") + "Mod"
                    body = [f"package {package or 'com.example'};", "",
                            f"public class {cls} {{"]
                    for feat in features or []:
                        body.append(f"    // TODO: {feat}")
                    body += ["    public void onInitialize() {}", "}", ""]
                    open(os.path.join(pkg_path, f"{cls}.java"), "w",
                         encoding="utf-8").write("\n".join(body))
                if label == "writing gradle files":
                    open(os.path.join(base, "build.gradle"), "w",
                         encoding="utf-8").write(
                        f"// {loader} mod for Minecraft {version}\n"
                        "plugins { id 'java' }\n"
                    )
                    open(os.path.join(base, "README.md"), "w",
                         encoding="utf-8").write(
                        f"# {name}\n\n{loader} mod for Minecraft {version}.\n"
                        "Open in IntelliJ and run `gradlew build`.\n"
                    )
                time.sleep(0.4)
            job["state"] = "done"
        except Exception as exc:
            job["state"] = "failed"
            job["error"] = str(exc)
        act_call(f"mod build {job['state']}: {name}")

    threading.Thread(target=build, daemon=True).start()
    return {"ok": True, "job_id": job_id, "message": f"building {name} ({loader} {version})"}


def mod_list() -> List[Dict[str, Any]]:
    rows = []
    for entry in sorted(os.listdir(MODS_DIR)) if os.path.isdir(MODS_DIR) else []:
        p = os.path.join(MODS_DIR, entry)
        if not os.path.isdir(p):
            continue
        size = sum(
            os.path.getsize(os.path.join(r, f))
            for r, _d, fs in os.walk(p) for f in fs
        )
        rows.append({
            "name": entry,
            "path": p,
            "size_kb": round(size / 1024, 1),
            "date": datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M"),
        })
    return rows


# ───────────────────────────── intent engine ─────────────────────────────
# The phone never parses anything. Everything below is decided here.

NUM_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "sixty": 60}


def seconds_from(text: str, default: int = 30) -> int:
    m = re.search(r"(\d+)\s*(second|sec|minute|min|hour|hr)", text)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        return n * (60 if unit.startswith("min") else 3600 if unit.startswith("h") else 1)
    for word, n in NUM_WORDS.items():
        if re.search(rf"\b{word}\b\s*(minute|min)", text):
            return n * 60
        if re.search(rf"\b{word}\b\s*(second|sec)", text):
            return n
    if "now" in text or "immediately" in text:
        return 0
    return default


def find_target(text: str) -> Optional[str]:
    for site in SITE_ALIASES:
        if site in text:
            return site
    for app_name in APP_ALIASES:
        if re.search(rf"\b{re.escape(app_name)}\b", text):
            return app_name
    m = re.search(r"(?:open|launch|start|go to|goto|visit|run)\s+(.+)", text)
    if m:
        target = m.group(1).strip(" .!?")
        target = re.sub(r"^(the|my|up)\s+", "", target)
        return target or None
    return None


def understand(raw: str) -> Dict[str, Any]:
    """Return { reply, actions, speak } — the whole brain."""
    text = (raw or "").strip()
    low = text.lower()
    actions: List[Dict[str, Any]] = []

    def done(reply: str, speak: bool = True) -> Dict[str, Any]:
        return {"ok": True, "reply": reply, "actions": actions, "speak": speak}

    if not low:
        return done(f"I'm listening, {OWNER}.")

    # greetings / identity
    if re.fullmatch(r"(hi|hey|hello|yo|dropx|drop x)[\s!.]*", low):
        return done(f"Yes {OWNER}, Sirr! What do you need?")
    if "who are you" in low or "your name" in low:
        return done("I'm DropX, your PC. I run the machine so you don't have to.")
    if "thank" in low:
        return done("Anytime.")
    if "how are you" in low:
        b = act_battery()
        pct = f"{b['percent']}% battery" if b.get("percent") is not None else "running fine"
        return done(f"All good — {pct}, {socket.gethostname()} online.")
    if "what time" in low or low.startswith("time"):
        return done(datetime.now().strftime("It's %H:%M on %A."))

    # cancel first (so "cancel shutdown" never shuts down)
    if "cancel" in low and ("shut" in low or "power off" in low or "restart" in low):
        actions.append({"type": "shutdown_cancel", "result": act_cancel_shutdown()})
        return done("Shutdown cancelled.")

    # power
    if any(k in low for k in ("wake", "turn on", "power on", "boot")):
        actions.append({"type": "wake", "result": act_wake()})
        return done("Magic packet sent — waking the PC.")
    if any(k in low for k in ("shut down", "shutdown", "power off", "turn off pc",
                              "turn it off")):
        delay = seconds_from(low, 30)
        actions.append({"type": "shutdown", "result": act_shutdown(delay)})
        return done(f"Shutting down in {delay} seconds. Say cancel to stop me.")
    if "lock" in low:
        actions.append({"type": "lock", "result": act_lock()})
        return done("Locked.")
    if "sleep" in low or "suspend" in low:
        actions.append({"type": "sleep", "result": act_sleep()})
        return done("Going to sleep.")

    # system
    if "screenshot" in low or "screen shot" in low or "capture screen" in low:
        actions.append({"type": "screenshot", "result": act_screenshot()})
        return done("Screenshot taken.")
    if "mute" in low:
        actions.append({"type": "volume", "result": act_volume("mute")})
        return done("Muted.")
    if "volume" in low or "louder" in low or "quieter" in low:
        direction = "down" if any(k in low for k in ("down", "lower", "quieter")) else "up"
        actions.append({"type": "volume", "result": act_volume(direction)})
        return done(f"Volume {direction}.")
    if "brightness" in low:
        m = re.search(r"(\d{1,3})", low)
        level = int(m.group(1)) if m else (30 if "down" in low or "dim" in low else 80)
        actions.append({"type": "brightness", "result": act_brightness(level)})
        return done(f"Brightness at {level} percent.")
    if any(k in low for k in ("pause music", "play music", "next song", "next track",
                              "previous song", "skip song", "resume music")):
        action = ("next" if "next" in low or "skip" in low else
                  "prev" if "previous" in low else "play")
        actions.append({"type": "media", "result": act_media(action)})
        return done(f"Media {action}.")
    if "wifi" in low or "wi-fi" in low:
        state = "off" if "off" in low or "disable" in low else "on"
        actions.append({"type": "wifi", "result": act_wifi(state)})
        return done(f"Wi-Fi {state}.")
    if "bluetooth" in low:
        state = "off" if "off" in low or "disable" in low else "on"
        actions.append({"type": "bluetooth", "result": act_bluetooth(state)})
        return done(f"Bluetooth {state}.")
    if "battery" in low or "charge" in low:
        b = act_battery()
        actions.append({"type": "battery", "result": b})
        if b.get("percent") is None:
            return done("No battery here — this machine runs on mains power.")
        state = "charging" if b.get("charging") else "on battery"
        return done(f"Battery is at {b['percent']} percent, {state}.")
    if "disk" in low or "storage" in low or "space" in low:
        d = act_disk()
        actions.append({"type": "disk", "result": d})
        if "error" in d:
            return done("I couldn't read the disk.")
        return done(f"{d['free_gb']} gigabytes free of {d['total_gb']} on {d['drive']}.")
    if "ip" in low.split() or "network" in low or "internet" in low:
        n = act_net()
        actions.append({"type": "net", "result": n})
        return done(f"Local IP {n['ip']}, internet {'up' if n['online'] else 'down'}.")
    if "clipboard" in low and ("read" in low or "what" in low or "get" in low):
        text_cb = clipboard_get()
        actions.append({"type": "clipboard_get", "result": text_cb[:500]})
        return done(f"Clipboard says: {text_cb[:200] or 'nothing'}")
    if "copy" in low and "clipboard" in low:
        payload = re.sub(r".*copy\s+", "", text, flags=re.I)
        payload = re.sub(r"\s*to (the )?clipboard.*", "", payload, flags=re.I)
        actions.append({"type": "clipboard_set", "result": clipboard_set(payload)})
        return done("Copied.")
    if "process" in low or "task manager" in low or "what's running" in low:
        rows = act_processes(10)
        actions.append({"type": "processes", "result": rows})
        top = ", ".join(r["name"] for r in rows[:3])
        return done(f"Heaviest right now: {top}.")
    if low.startswith("kill ") or "close process" in low or "force close" in low:
        target = re.sub(r"^(kill|close process|force close)\s+", "", low).strip()
        actions.append({"type": "kill", "result": act_kill(target)})
        return done(f"Killed {target}.")

    # window
    if "minimize" in low:
        actions.append({"type": "window", "result": act_window(
            "minimize_all" if "all" in low else "minimize")})
        return done("Minimized.")
    if "maximize" in low or "full screen" in low:
        actions.append({"type": "window", "result": act_window("maximize")})
        return done("Maximized.")
    if "switch window" in low or "alt tab" in low:
        actions.append({"type": "window", "result": act_window("switch")})
        return done("Switched.")
    if low.startswith("close") and "process" not in low:
        rest = low.replace("close", "", 1).strip()
        if rest and rest not in ("window", "this", "it"):
            actions.append({"type": "kill", "result": act_kill(rest)})
            return done(f"Closed {rest}.")
        actions.append({"type": "window", "result": act_close()})
        return done("Closed the window.")

    # notes & reminders
    if "note" in low and ("add" in low or "save" in low or "write" in low or
                          low.startswith("note")):
        payload = re.sub(r"^(add|save|write|make)?\s*(a\s+)?note\s*(that|:)?\s*", "",
                         text, flags=re.I).strip()
        note = act_notes_add(payload or text)
        actions.append({"type": "note", "result": note})
        return done("Noted.")
    if "remind" in low:
        when = ""
        m = re.search(r"(at|in)\s+(.+)$", low)
        if m:
            when = m.group(0)
        item = act_reminder(text, when)
        actions.append({"type": "reminder", "result": item})
        return done(f"Reminder set{(' ' + when) if when else ''}.")

    # calls
    if "call me" in low or low.startswith("call"):
        reason = re.sub(r".*call( me)?( about| for| when)?\s*", "", text, flags=re.I)
        actions.append({"type": "call", "result": act_call(reason or "manual")})
        return done("Calling you now.")

    # dev
    if "scaffold" in low or "new project" in low:
        kind = ("python-cli" if "python" in low else
                "fabric-mod" if "fabric" in low else
                "forge-mod" if "forge" in low else "web")
        actions.append({"type": "scaffold", "result": act_scaffold(
            kind, os.path.join(DROPX_DIR, f"project-{int(time.time())}"))})
        return done(f"Scaffolded a {kind} project in your DropX folder.")
    if low.startswith("qa") or "check project" in low or "quality check" in low:
        path = re.sub(r"^(qa|check project|quality check)\s*", "", low).strip()
        result = act_qa(path or DROPX_DIR)
        actions.append({"type": "qa", "result": result})
        if not result.get("ok"):
            return done("I couldn't find that folder.")
        return done(f"{result['files']} files, README {'present' if result['has_readme'] else 'missing'}.")

    # mods
    if "mod" in low and ("new" in low or "make" in low or "create" in low or
                         "build" in low):
        loader = ("forge" if "forge" in low and "neo" not in low else
                  "neoforge" if "neoforge" in low else "fabric")
        mv = re.search(r"1\.\d{2}(\.\d)?", low)
        version = mv.group(0) if mv else "1.20.1"
        name = f"DropXMod{int(time.time()) % 10000}"
        job = mod_new(loader, version, name, name.lower(), "com.dropx", [])
        actions.append({"type": "mod_new", "result": job})
        return done(f"Building a {loader} mod for {version}. I'll ping you when it's done.")
    if "list mods" in low or ("mods" in low and "list" in low):
        rows = mod_list()
        actions.append({"type": "mod_list", "result": rows})
        return done(f"{len(rows)} mods in your folder." if rows else "No mods yet.")

    # open anything — last, because it's the widest net
    if any(k in low for k in ("open", "launch", "start", "go to", "goto", "visit",
                              "play ", "show me")):
        target = find_target(low)
        if target:
            result = act_open(SITE_ALIASES.get(target, target))
            actions.append({"type": "open", "result": result})
            return done(f"Opening {target}.")

    # bare site/app name with no verb, e.g. "youtube"
    bare = find_target(low)
    if bare and len(low.split()) <= 3:
        actions.append({"type": "open", "result": act_open(SITE_ALIASES.get(bare, bare))})
        return done(f"Opening {bare}.")

    return done(f"I heard you, {OWNER}, but that's not something I can do yet. "
                "Try wake, shutdown, lock, screenshot, volume, open something, "
                "notes, mods or PC stats.")


def remember(kind: str, text: str, reply: str, actions: List[Dict[str, Any]]) -> None:
    HISTORY.insert(0, {"id": uuid.uuid4().hex[:8], "kind": kind, "text": text,
                       "reply": reply,
                       "actions": [a.get("type") for a in actions],
                       "time": now()})
    del HISTORY[200:]


# ───────────────────────────── routes ─────────────────────────────

def ok(**kw: Any) -> JSONResponse:
    return JSONResponse({"ok": True, **kw})


def fail(error: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": error}, status_code=status)


async def body(request: Request) -> Dict[str, Any]:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@app.get("/status")
def status() -> JSONResponse:
    return ok(host=socket.gethostname(), platform=SYSTEM, owner=OWNER,
              ip=local_ip(), time=now(), version="2.0")


@app.post("/voice")
@app.post("/type")
async def voice(request: Request) -> JSONResponse:
    data = await body(request)
    text = str(data.get("text") or "")
    log(f"heard: {text}")
    try:
        result = understand(text)
    except Exception as exc:
        log(f"brain error: {exc}")
        return ok(reply="That one tripped me up. Try again?", actions=[], speak=True)
    remember("voice", text, result["reply"], result["actions"])
    return ok(**result)


@app.get("/history")
def history() -> JSONResponse:
    return ok(history=HISTORY[:50])


# power
@app.post("/wake")
def wake() -> JSONResponse:
    return ok(message=act_wake())


@app.post("/shutdown")
async def shutdown(request: Request) -> JSONResponse:
    data = await body(request)
    return ok(message=act_shutdown(int(data.get("delay") or 30)))


@app.post("/shutdown/cancel")
def shutdown_cancel() -> JSONResponse:
    return ok(message=act_cancel_shutdown())


@app.post("/lock")
def lock() -> JSONResponse:
    return ok(message=act_lock())


@app.post("/sleep")
def sleep_route() -> JSONResponse:
    return ok(message=act_sleep())


# system
@app.post("/screenshot")
def screenshot() -> JSONResponse:
    return ok(message=act_screenshot())


@app.post("/volume")
async def volume(request: Request) -> JSONResponse:
    data = await body(request)
    return ok(message=act_volume(str(data.get("direction") or "up")))


@app.post("/brightness")
async def brightness(request: Request) -> JSONResponse:
    data = await body(request)
    return ok(message=act_brightness(int(data.get("level") or 80)))


@app.post("/wifi")
async def wifi(request: Request) -> JSONResponse:
    data = await body(request)
    return ok(message=act_wifi(str(data.get("state") or "on")))


@app.post("/bluetooth")
async def bluetooth(request: Request) -> JSONResponse:
    data = await body(request)
    return ok(message=act_bluetooth(str(data.get("state") or "on")))


@app.post("/media")
async def media(request: Request) -> JSONResponse:
    data = await body(request)
    return ok(message=act_media(str(data.get("action") or "play")))


@app.post("/window")
async def window(request: Request) -> JSONResponse:
    data = await body(request)
    return ok(message=act_window(str(data.get("action") or "minimize")))


@app.get("/battery")
def battery() -> JSONResponse:
    return ok(**act_battery())


@app.get("/disk")
def disk() -> JSONResponse:
    return ok(**act_disk())


@app.get("/net")
def net() -> JSONResponse:
    return ok(**act_net())


@app.get("/processes")
def processes() -> JSONResponse:
    return ok(processes=act_processes())


@app.post("/kill")
async def kill(request: Request) -> JSONResponse:
    data = await body(request)
    try:
        return ok(message=act_kill(str(data.get("name") or "")))
    except Exception as exc:
        return fail(str(exc))


@app.post("/clipboard/get")
def clipboard_read() -> JSONResponse:
    return ok(text=clipboard_get())


@app.post("/clipboard/set")
async def clipboard_write(request: Request) -> JSONResponse:
    data = await body(request)
    return ok(message=clipboard_set(str(data.get("text") or "")))


# apps & files
@app.post("/app")
async def app_open(request: Request) -> JSONResponse:
    data = await body(request)
    try:
        return ok(message=act_app(str(data.get("name") or "")))
    except Exception as exc:
        return fail(str(exc))


@app.post("/url")
async def url_open(request: Request) -> JSONResponse:
    data = await body(request)
    try:
        return ok(message=act_url(str(data.get("url") or "")))
    except Exception as exc:
        return fail(str(exc))


@app.post("/open")
async def open_route(request: Request) -> JSONResponse:
    data = await body(request)
    try:
        return ok(message=act_open(str(data.get("target") or "")))
    except Exception as exc:
        return fail(str(exc))


@app.post("/close")
def close_route() -> JSONResponse:
    return ok(message=act_close())


@app.post("/upload")
async def upload(file: UploadFile = File(...)) -> JSONResponse:
    dest = os.path.join(UPLOAD_DIR, os.path.basename(file.filename or "upload.bin"))
    with open(dest, "wb") as f:
        f.write(await file.read())
    return ok(message=f"saved to {dest}", path=dest)


@app.post("/command")
async def command(request: Request) -> JSONResponse:
    data = await body(request)
    cmd = str(data.get("cmd") or "").strip()
    if not cmd:
        return fail("no command")
    log(f"command: {cmd}")
    return ok(output=run(cmd, shell=True)[:4000])


# notes & reminders
@app.post("/notes")
async def notes_add(request: Request) -> JSONResponse:
    data = await body(request)
    return ok(note=act_notes_add(str(data.get("text") or "")))


@app.get("/notes/list")
def notes_list() -> JSONResponse:
    return ok(notes=load_json(NOTES_FILE, []))


@app.post("/notes/delete")
async def notes_delete(request: Request) -> JSONResponse:
    data = await body(request)
    nid = str(data.get("id") or "")
    notes = [n for n in load_json(NOTES_FILE, []) if n.get("id") != nid]
    save_json(NOTES_FILE, notes)
    return ok(message="deleted")


@app.post("/reminder")
async def reminder(request: Request) -> JSONResponse:
    data = await body(request)
    return ok(reminder=act_reminder(str(data.get("text") or ""),
                                    str(data.get("when") or "")))


@app.get("/reminders/list")
def reminders_list() -> JSONResponse:
    return ok(reminders=load_json(REMINDERS_FILE, []))


# dev
@app.post("/scaffold")
async def scaffold(request: Request) -> JSONResponse:
    data = await body(request)
    try:
        return ok(message=act_scaffold(str(data.get("kind") or ""),
                                       str(data.get("target") or "")))
    except Exception as exc:
        return fail(str(exc))


@app.post("/qa")
async def qa(request: Request) -> JSONResponse:
    data = await body(request)
    return JSONResponse(act_qa(str(data.get("path") or "")))


# email — credentials stay on the PC. Configure below to go live.
MAIL_CONFIG = {"imap": "", "smtp": "", "user": "", "password": ""}
MAIL_RULES = {"auto_reply": False, "whitelist": [], "window": ["09:00", "21:00"],
              "template": "Hi, got your mail — I'll get back to you shortly."}
MAIL_SENT: List[Dict[str, Any]] = []


def mail_ready() -> bool:
    return bool(MAIL_CONFIG["imap"] and MAIL_CONFIG["user"] and MAIL_CONFIG["password"])


@app.get("/mail/unread")
def mail_unread() -> JSONResponse:
    if not mail_ready():
        return ok(configured=False, messages=[],
                  message="Mail isn't set up on the PC yet.")
    import email
    import imaplib
    msgs: List[Dict[str, Any]] = []
    try:
        box = imaplib.IMAP4_SSL(MAIL_CONFIG["imap"])
        box.login(MAIL_CONFIG["user"], MAIL_CONFIG["password"])
        box.select("INBOX")
        _typ, ids = box.search(None, "UNSEEN")
        for mid in (ids[0].split() or [])[-20:][::-1]:
            _t, raw = box.fetch(mid, "(RFC822)")
            msg = email.message_from_bytes(raw[0][1])
            body_text = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body_text = part.get_payload(decode=True).decode(
                            "utf-8", "ignore")
                        break
            else:
                body_text = (msg.get_payload(decode=True) or b"").decode(
                    "utf-8", "ignore")
            msgs.append({"id": mid.decode(), "from": msg.get("From", ""),
                         "subject": msg.get("Subject", ""),
                         "date": msg.get("Date", ""),
                         "snippet": body_text.strip()[:160], "body": body_text[:5000]})
        box.logout()
        return ok(configured=True, messages=msgs)
    except Exception as exc:
        return ok(configured=True, messages=[], error=str(exc))


@app.get("/mail/{mail_id}")
def mail_get(mail_id: str) -> JSONResponse:
    if not mail_ready():
        return ok(configured=False, message="Mail isn't set up on the PC yet.")
    return ok(configured=True, id=mail_id,
              message="Open the inbox list to read full messages.")


@app.post("/mail/draft")
async def mail_draft(request: Request) -> JSONResponse:
    data = await body(request)
    original = str(data.get("original") or "")
    first = original.strip().splitlines()[0][:80] if original.strip() else "your message"
    draft = (f"Hi,\n\nThanks for writing about {first}. "
             "I've seen this and I'll come back to you with a proper answer soon.\n\n"
             f"Best,\n{OWNER}")
    return ok(draft=draft)


@app.post("/mail/send")
async def mail_send(request: Request) -> JSONResponse:
    data = await body(request)
    to, subject, text = (str(data.get("to") or ""), str(data.get("subject") or ""),
                         str(data.get("body") or ""))
    if not mail_ready():
        return ok(sent=False, message="Mail isn't set up on the PC yet.")
    import smtplib
    from email.message import EmailMessage
    try:
        msg = EmailMessage()
        msg["From"] = MAIL_CONFIG["user"]
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        with smtplib.SMTP_SSL(MAIL_CONFIG["smtp"], 465) as s:
            s.login(MAIL_CONFIG["user"], MAIL_CONFIG["password"])
            s.send_message(msg)
        MAIL_SENT.insert(0, {"to": to, "subject": subject, "time": now()})
        return ok(sent=True, message=f"sent to {to}")
    except Exception as exc:
        return fail(str(exc))


@app.post("/mail/save")
async def mail_save(request: Request) -> JSONResponse:
    data = await body(request)
    path = os.path.join(DROPX_DIR, "drafts.json")
    drafts = load_json(path, [])
    drafts.insert(0, {**data, "time": now(), "id": uuid.uuid4().hex[:8]})
    save_json(path, drafts)
    return ok(message="draft saved on PC")


@app.get("/mail/rules")
def mail_rules_get() -> JSONResponse:
    return ok(rules=MAIL_RULES, configured=mail_ready(), sent=MAIL_SENT[:20])


@app.post("/mail/rules")
async def mail_rules_set(request: Request) -> JSONResponse:
    data = await body(request)
    MAIL_RULES.update(data.get("config") or data)
    return ok(rules=MAIL_RULES)


# calls
@app.post("/call")
async def call(request: Request) -> JSONResponse:
    data = await body(request)
    return ok(message=act_call(str(data.get("reason") or "manual")))


@app.get("/calls/log")
def calls_log() -> JSONResponse:
    return ok(calls=CALL_LOG[:20])


@app.post("/voice/note")
async def voice_note(file: UploadFile = File(...)) -> JSONResponse:
    dest = os.path.join(UPLOAD_DIR, f"note-{int(time.time())}.webm")
    with open(dest, "wb") as f:
        f.write(await file.read())
    act_call("voice message from your phone")
    return ok(message="voice note delivered", path=dest)


# DMs — read-only placeholders until you plug in a client on the PC
DM_RULES: Dict[str, Dict[str, Any]] = {
    p: {"auto_reply": False, "whitelist": [], "window": ["09:00", "21:00"]}
    for p in ("instagram", "whatsapp", "discord")
}
DM_SENT: List[Dict[str, Any]] = []


@app.get("/dms/{platform}/unread")
def dms_unread(platform: str) -> JSONResponse:
    return ok(platform=platform, configured=False, threads=[],
              message=f"{platform} isn't linked on the PC yet.")


@app.post("/dms/{platform}/reply")
async def dms_reply(platform: str, request: Request) -> JSONResponse:
    data = await body(request)
    DM_SENT.insert(0, {"platform": platform, **data, "time": now()})
    return ok(sent=False, message=f"{platform} isn't linked on the PC yet.")


@app.post("/dms/{platform}/draft")
async def dms_draft(platform: str, request: Request) -> JSONResponse:
    data = await body(request)
    text = str(data.get("text") or "")
    return ok(draft=f"Hey! Saw your message about {text[:60] or 'this'} — "
                    "give me a bit and I'll reply properly.")


@app.get("/dms/{platform}/rules")
def dms_rules_get(platform: str) -> JSONResponse:
    return ok(platform=platform, rules=DM_RULES.get(platform, {}), sent=DM_SENT[:20])


@app.post("/dms/{platform}/rules")
async def dms_rules_set(platform: str, request: Request) -> JSONResponse:
    data = await body(request)
    DM_RULES.setdefault(platform, {}).update(data.get("config") or data)
    return ok(rules=DM_RULES[platform])


# mods
@app.post("/mod/new")
async def mod_new_route(request: Request) -> JSONResponse:
    data = await body(request)
    return JSONResponse(mod_new(
        str(data.get("loader") or "fabric"),
        str(data.get("version") or "1.20.1"),
        str(data.get("name") or "ExampleMod"),
        str(data.get("id") or "examplemod"),
        str(data.get("package") or "com.example"),
        list(data.get("features") or []),
    ))


@app.get("/mod/status/{job_id}")
def mod_status(job_id: str) -> JSONResponse:
    job = MOD_JOBS.get(job_id)
    if not job:
        return fail("unknown job", 404)
    return ok(**job)


@app.get("/mod/list")
def mod_list_route() -> JSONResponse:
    return ok(mods=mod_list())


@app.post("/mod/build")
async def mod_build(request: Request) -> JSONResponse:
    data = await body(request)
    name = str(data.get("name") or "")
    path = os.path.join(MODS_DIR, name)
    if not os.path.isdir(path):
        return fail("mod not found", 404)
    gradle = os.path.join(path, "gradlew.bat" if SYSTEM == "Windows" else "gradlew")
    if os.path.exists(gradle):
        threading.Thread(target=lambda: run([gradle, "build"]), daemon=True).start()
        return ok(message=f"gradle build started for {name}")
    return ok(message=f"{name} has no gradle wrapper yet — open it in IntelliJ once.")


@app.post("/dropx")
def dropx() -> JSONResponse:
    return ok(message=f"Yes {OWNER}, Sirr!")


if __name__ == "__main__":
    import uvicorn

    log(f"DropX agent on http://0.0.0.0:{PORT}  ({SYSTEM})")
    log(f"docs: http://localhost:{PORT}/docs")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
