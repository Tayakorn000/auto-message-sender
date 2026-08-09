import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import subprocess
import os
import re
import sys
import json
import io
import zipfile
import urllib.request
from flask import Flask, jsonify, request
from flask_cors import CORS

# ==========================================
# 0. อัปเดตอัตโนมัติ (ดูเวอร์ชันจาก GitHub Release)
# ==========================================
APP_VERSION = "1.6.5"
UPDATE_REPO = "Tayakorn000/auto-message-sender"
UPDATE_API = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"


def parse_version(s):
    """"V1.5.0" -> (1, 5, 0) เทียบกันได้ตรง ๆ ไม่ต้องพึ่ง packaging"""
    nums = re.findall(r"\d+", s or "")
    return tuple(int(n) for n in nums[:3]) if nums else (0,)


def check_update(timeout=10):
    """คืน (tag, url_exe, url_extension_zip) เมื่อมีเวอร์ชันใหม่กว่า / None เมื่อไม่มีหรือเช็คไม่ได้

    url_extension_zip เป็น None ได้ ถ้า release นั้นไม่ได้แนบ extension.zip มา

    ponytail: ดูแต่ tag ไม่โหลดไฟล์ = 1 request เล็ก ๆ ไม่กินเน็ต
    """
    try:
        req = urllib.request.Request(UPDATE_API, headers={"User-Agent": "AutoSender"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None  # เน็ตไม่ดี/รีโปเป็น private = ไม่ต้องรบกวนผู้ใช้

    tag = data.get("tag_name", "")
    if parse_version(tag) <= parse_version(APP_VERSION):
        return None
    exe_url = ext_url = None
    for a in data.get("assets", []):
        url = a.get("browser_download_url", "")
        name = a.get("name", "").lower()
        # ยึดโดเมน github.com เท่านั้น กัน URL แปลกปลอมใน release
        if not url.startswith("https://github.com/"):
            continue
        if name.endswith(".exe") and not exe_url:
            exe_url = url
        elif name == "extension.zip":
            ext_url = url
    return (tag, exe_url, ext_url) if exe_url else None


def base_dir():
    return os.path.dirname(os.path.abspath(
        sys.executable if getattr(sys, "frozen", False) else __file__))


CONFIG_PATH = os.path.join(base_dir(), "autosender_config.json")


def find_ext_dir():
    """โฟลเดอร์ส่วนขยายที่ Chrome โหลดอยู่ (Load unpacked)

    ponytail: ทุกโปรไฟล์ที่ Load unpacked จากโฟลเดอร์เดียวกัน = ไฟล์ชุดเดียวกันบนดิสก์
    ทับทีเดียวได้ทุกโปรไฟล์ ไม่ต้องไล่ทีละอัน (โปรไฟล์ที่ชี้คนละโฟลเดอร์จะโผล่ในคำเตือน
    เพราะส่วนขยายรายงานเวอร์ชันตัวเองมาทุกครั้งที่ถามงาน)
    """
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            d = json.load(f).get("ext_dir")
        if d and os.path.isfile(os.path.join(d, "manifest.json")):
            return d
    except Exception:
        pass
    d = os.path.join(base_dir(), "extension")
    return d if os.path.isfile(os.path.join(d, "manifest.json")) else None


def save_ext_dir(d):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"ext_dir": d}, f)


def update_extension(url, ext_dir, expect_version=None, timeout=60):
    """โหลด extension.zip มาทับโฟลเดอร์ส่วนขยาย คืนจำนวนไฟล์ที่เขียน

    ปิด Chrome ให้หมดแล้วเปิดใหม่ ทุกโปรไฟล์ที่ Load unpacked จากโฟลเดอร์นี้จะได้ไฟล์ชุดใหม่
    (ขั้นตอน "เปิด Chrome Profiles" ก็ต้องปิด Chrome อยู่แล้ว)
    ถ้าเปิดใหม่แล้วยังขึ้นเตือนว่าเวอร์ชันเก่า ให้กด Reload ที่ chrome://extensions ครั้งเดียว
    """
    root = os.path.abspath(ext_dir)
    if not os.path.isfile(os.path.join(root, "manifest.json")):
        raise RuntimeError("ไม่พบ manifest.json ในโฟลเดอร์ส่วนขยาย")

    req = urllib.request.Request(url, headers={"User-Agent": "AutoSender"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        blob = r.read()

    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        entries = [n for n in z.namelist() if not n.endswith("/")]
        if not entries:
            raise RuntimeError("ซิปว่าง")
        # ซิปที่ห่อไว้ในโฟลเดอร์ชั้นเดียว (extension/...) ให้ปอกออกก่อน ไม่งั้นไฟล์ลงผิดที่
        # ปอกเฉพาะตอนที่ปอกแล้วเจอ manifest.json ที่ราก ไม่งั้นเสี่ยงปอกผิด
        # (เช่นซิปที่ทุกไฟล์บังเอิญอยู่ใต้ popup/ อันเดียว)
        tops = {n.split("/")[0] for n in entries}
        strip = (len(tops) == 1 and all("/" in n for n in entries)
                 and any(n.split("/", 1)[1] == "manifest.json" for n in entries))
        plan = []
        for n in entries:
            rel = n.split("/", 1)[1] if strip else n
            # กันซิปที่ใส่ ../ หรือ path เต็ม มาเขียนไฟล์นอกโฟลเดอร์ส่วนขยาย
            p = os.path.normpath(os.path.join(root, rel))
            if p != root and not p.startswith(root + os.sep):
                raise RuntimeError("ไฟล์ในซิปมี path ผิดปกติ: %s" % n)
            plan.append((n, p))
        if not any(os.path.basename(p) == "manifest.json" for _, p in plan):
            raise RuntimeError("ซิปไม่มี manifest.json ไม่ใช่ไฟล์ส่วนขยาย")
        for n, p in plan:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(z.read(n))

    # อ่าน manifest กลับมาเช็คว่าเวอร์ชันเปลี่ยนจริง ไม่ใช่แค่เขียนไฟล์ผ่าน
    # (ซิปที่โหลดมาไม่ครบก็ยังแตกได้บางไฟล์ แล้วขึ้นว่าสำเร็จทั้งที่ของเก่ายังอยู่)
    if expect_version:
        try:
            with open(os.path.join(root, "manifest.json"), encoding="utf-8") as f:
                got = json.load(f).get("version")
        except Exception:
            got = None
        if parse_version(got) != parse_version(expect_version):
            raise RuntimeError("อัปเดตแล้วแต่ manifest ยังเป็น %s (ควรเป็น %s)"
                               % (got, expect_version))
    return len(plan)


def download_and_restart(url, on_progress=None):
    """โหลดไฟล์ใหม่ แล้วให้ .bat สลับไฟล์ตอนโปรแกรมปิด (Windows แทนที่ .exe ที่รันอยู่ไม่ได้)"""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("ตอนนี้รันจากซอร์ส (main.py) อัปเดตอัตโนมัติใช้กับ .exe เท่านั้น")

    exe = os.path.abspath(sys.executable)
    new = exe + ".new"

    req = urllib.request.Request(url, headers={"User-Agent": "AutoSender"})
    with urllib.request.urlopen(req, timeout=60) as r, open(new, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(262144)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if on_progress:
                on_progress(got, total)

    if os.path.getsize(new) < 1_000_000:  # exe จริงหลายสิบ MB ได้เท่านี้แปลว่าโหลดไม่ครบ
        os.remove(new)
        raise RuntimeError("ไฟล์ที่โหลดมาไม่สมบูรณ์")

    bat = exe + ".update.bat"
    # วนรอจนโปรแกรมปิดจริงแล้วค่อยสลับไฟล์ ครบ 30 รอบ (~30 วิ) แล้วยอมแพ้ ไม่วนค้าง
    with open(bat, "w", encoding="ascii") as f:
        f.write(
            '@echo off\r\n'
            'set /a n=0\r\n'
            ':wait\r\n'
            'ping -n 2 127.0.0.1 >nul\r\n'
            f'move /y "{new}" "{exe}" >nul 2>&1\r\n'
            'if not errorlevel 1 goto done\r\n'
            'set /a n+=1\r\n'
            'if %n% lss 30 goto wait\r\n'
            ':done\r\n'
            f'start "" "{exe}"\r\n'
            'del "%~f0"\r\n'
        )
    subprocess.Popen(["cmd", "/c", bat], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return True

# ==========================================
# 1. ข้อมูลส่วนกลาง
# ==========================================
presets_data = {
    "profile_1": {"is_system_on": False, "mode": "messenger", "url_messenger": "", "url_live": "", "url_post": "",
                  "message_text": "ทักครับ", "msg_limit": 1, "current_task_id": 0, "action_type": "",
                  "is_page_link": False},
    "profile_2": {"is_system_on": False, "mode": "messenger", "url_messenger": "", "url_live": "", "url_post": "",
                  "message_text": "ทักครับ", "msg_limit": 1, "current_task_id": 0, "action_type": "",
                  "is_page_link": False},
    "profile_3": {"is_system_on": False, "mode": "messenger", "url_messenger": "", "url_live": "", "url_post": "",
                  "message_text": "ทักครับ", "msg_limit": 1, "current_task_id": 0, "action_type": "",
                  "is_page_link": False},
    "profile_all": {"is_system_on": False, "mode": "messenger", "url_messenger": "", "url_live": "", "url_post": "",
                    "message_text": "ทักครับ", "msg_limit": 1, "current_task_id": 0, "action_type": "",
                    "is_page_link": False}
}

profiles_completed = {}
ui_command_queue = []
ext_versions = {}  # uid ของแต่ละโปรไฟล์ Chrome -> เวอร์ชันส่วนขยายที่รันอยู่
ext_profiles = {}  # uid -> preset ที่โปรไฟล์นั้นเลือกไว้ (เอาไว้บอกว่าโปรไฟล์ไหนตกรุ่น)

# หน้าต่างที่ถูกบัง/ไม่ได้อยู่หน้าสุด Chrome จะหน่วง timer เหลือ 1 ครั้ง/วินาที
# ทำให้บอทค้างจนกว่าคนจะไปคลิกจอนั้นเอง แฟล็กชุดนี้ปิดการหน่วงทั้งหมด
CHROME_NO_THROTTLE_FLAGS = [
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling",
]

# ==========================================
# 2. API Server (Flask)
# ==========================================
app = Flask(__name__)
CORS(app)


@app.route('/api/get-task/<preset_group>/<unique_id>')
def get_task(preset_group, unique_id):
    # ส่วนขยายบอกเวอร์ชันตัวเองมาด้วย เอาไว้เตือนเมื่อลืมกด Reload หลังอัปเดต
    # ponytail: ตัวเก่ากว่า 1.6.0 ไม่ส่ง v มาเลย ต้องนับเป็นเก่าที่สุด ("0")
    # ไม่งั้นเคสที่ต้องจับที่สุด (ไม่เคยเอาโฟลเดอร์ใหม่ไปวางเลย) จะเงียบสนิท ไม่ขึ้นเตือนอะไร
    ext_versions[unique_id] = request.args.get("v") or "0"
    ext_profiles[unique_id] = preset_group

    task = presets_data.get(preset_group)
    if not task or not task["is_system_on"] or task["current_task_id"] == 0:
        return jsonify({"status": "no_task"})

    task_id = task["current_task_id"]
    if int(time.time()) - task_id > 20:
        return jsonify({"status": "no_task"})

    last_done = profiles_completed.get(unique_id, 0)
    if last_done < task_id:
        return jsonify({
            "status": "has_task",
            "task_id": task_id,
            "action_type": task["action_type"],
            "mode": task["mode"],
            "url_messenger": task["url_messenger"],
            "url_live": task["url_live"],
            "url_post": task["url_post"],
            "message": task["message_text"],
            "limit": task["msg_limit"],
            "is_page_link": task.get("is_page_link", False)
        })
    else:
        return jsonify({"status": "no_task"})


@app.route('/api/mark-done/<unique_id>/<int:task_id>')
def mark_done(unique_id, task_id):
    profiles_completed[unique_id] = task_id
    return jsonify({"status": "success"})


@app.route('/api/turn-off-auto')
def turn_off_auto():
    ui_command_queue.append("turn_off_auto")
    return jsonify({"status": "success"})


def run_api_server():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    # ponytail: build แบบ --windowed ทำให้ sys.stdout/stderr เป็น None
    # werkzeug พิมพ์ banner ตอนสตาร์ท -> thread ตายเงียบ ๆ API ไม่ขึ้นเลย
    # (วัดแล้ว: รันจาก main.py ตอบ /api/get-task ปกติ แต่ .exe ไม่ listen port 5000)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    app.run(port=5000, debug=False, use_reloader=False)


# ==========================================
# 3. Custom Toggle Switch Widget
# ==========================================
class ToggleSwitch(tk.Canvas):
    def __init__(self, parent, state=False, command=None, bg_color="#f4f6f9", *args, **kwargs):
        super().__init__(parent, width=46, height=24, bg=bg_color, highlightthickness=0, takefocus=0, *args, **kwargs)
        self.state = state
        self.command = command
        self.bg_color = bg_color
        self.bind("<Button-1>", self.toggle)
        self.draw()

    def draw(self):
        self.delete("all")
        if self.state:
            self.create_oval(2, 2, 22, 22, fill="#2196f3", outline="#2196f3")
            self.create_oval(24, 2, 44, 22, fill="#2196f3", outline="#2196f3")
            self.create_rectangle(12, 2, 34, 22, fill="#2196f3", outline="#2196f3")
            self.create_oval(24, 4, 42, 20, fill="white", outline="white")
        else:
            self.create_oval(2, 2, 22, 22, fill="#cccccc", outline="#cccccc")
            self.create_oval(24, 2, 44, 22, fill="#cccccc", outline="#cccccc")
            self.create_rectangle(12, 2, 34, 22, fill="#cccccc", outline="#cccccc")
            self.create_oval(4, 4, 22, 20, fill="white", outline="white")

    def toggle(self, event):
        self.state = not self.state
        self.draw()
        if self.command:
            self.command(self.state)

    def set_state(self, state):
        self.state = state
        self.draw()


# ==========================================
# 4. หน้าจอ UI (Class สำหรับสร้าง Tab)
# ==========================================

# 🟢 คลาสใหม่: หน้าต่างเปิด Google Chrome Profiles
class SetupChromeTab:
    def __init__(self, notebook):
        self.frame = ttk.Frame(notebook)

        # 🟢 ตัวแปรตั้งค่า Max Profile
        self.max_profiles = 50

        # ค้นหา Path ของ Chrome
        self.chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if not os.path.exists(self.chrome_path):
            self.chrome_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

        self.setup_ui()

    def setup_ui(self):
        frame_top = ttk.LabelFrame(self.frame, text=" 🌐 ตัวจัดการ Google Chrome Profiles ", padding=15)
        frame_top.pack(fill="both", expand=True, padx=10, pady=10)

        tk.Label(frame_top, text="จำนวนโปรไฟล์ Chrome ที่ต้องการเปิดพร้อมกัน:", font=("Angsana New", 18, "bold"),
                 bg="#f4f6f9").pack(anchor="w", pady=(0, 5))

        frame_input = tk.Frame(frame_top, bg="#f4f6f9")
        frame_input.pack(fill="x", pady=(0, 15))

        self.spin_count = ttk.Spinbox(frame_input, from_=1, to=self.max_profiles, width=10,
                                      font=("Angsana New", 20, "bold"))
        self.spin_count.set(1)
        self.spin_count.pack(side="left")

        tk.Label(frame_input, text=f"(สูงสุด {self.max_profiles} โปรไฟล์)", font=("Angsana New", 16), bg="#f4f6f9",
                 fg="#6c757d").pack(side="left", padx=10)

        tk.Button(frame_top, text="🚀 เปิด Chrome Profiles (คลิกที่นี่)", bg="#0dcaf0", fg="black",
                  font=("Angsana New", 18, "bold"), relief="flat", pady=10, command=self.action_open_chrome).pack(
            fill="x")

        self.lbl_status = tk.Label(frame_top,
                                   text="สถานะ: รอคำสั่ง...\n⚠️ ปิด Chrome ให้หมดก่อนกดปุ่มนี้ (ถ้า Chrome เปิดค้างอยู่ ค่าปิดการหน่วงจะไม่ถูกใช้)",
                                   font=("Angsana New", 16), fg="#495057", bg="#f4f6f9", justify="left")
        self.lbl_status.pack(anchor="w", pady=(15, 0))

        # --- อัปเดตโปรแกรม ---
        frame_up = ttk.LabelFrame(self.frame, text=" ⬆️ อัปเดตโปรแกรม ", padding=10)
        frame_up.pack(fill="x", padx=10, pady=(0, 10))

        self.lbl_ver = tk.Label(frame_up, text=f"เวอร์ชันที่ใช้อยู่: {APP_VERSION}",
                                font=("Angsana New", 16, "bold"), bg="#f4f6f9", fg="#495057")
        self.lbl_ver.pack(anchor="w")

        self.lbl_update = tk.Label(frame_up, text="กำลังเช็คเวอร์ชันใหม่...", font=("Angsana New", 14),
                                   bg="#f4f6f9", fg="#6c757d", justify="left", wraplength=480)
        self.lbl_update.pack(anchor="w", pady=(2, 5))

        self.btn_update = tk.Button(frame_up, text="⬇️ ดาวน์โหลดและติดตั้งเวอร์ชันใหม่", bg="#0d6efd", fg="white",
                                    font=("Angsana New", 16, "bold"), relief="flat", pady=4, takefocus=0,
                                    command=self.action_update)
        self.new_release = None

        self.ext_note = ""      # ข้อความค้างจากการอัปเดตส่วนขยายอัตโนมัติ (ตั้งจากอีกเธรด)
        self.lbl_ext = tk.Label(frame_up, text="", font=("Angsana New", 14), bg="#f4f6f9",
                                fg="#dc3545", justify="left", wraplength=480)
        self.lbl_ext.pack(anchor="w", pady=(5, 0))
        self.refresh_ext_status()

        # เช็คตอนเปิดโปรแกรม ครั้งเดียว ไม่ต้องกดเอง (เทสตั้ง AUTOSENDER_NO_UPDATE_CHECK กันยิงเน็ตจริง)
        if not os.environ.get("AUTOSENDER_NO_UPDATE_CHECK"):
            threading.Thread(target=self._check_update_thread, daemon=True).start()

    def refresh_ext_status(self):
        """เตือนเมื่อมีโปรไฟล์ที่ยังใช้ส่วนขยายเวอร์ชันเก่า (ลืมกด Reload)

        บอกชื่อ preset ของโปรไฟล์นั้นด้วย — โปรไฟล์ที่ Load unpacked จากคนละโฟลเดอร์
        จะไม่ถูกอัปเดตพร้อมโฟลเดอร์หลัก ต้องเห็นว่าเป็นตัวไหน
        """
        old = sorted({"%s: %s" % (ext_profiles.get(uid, "?"),
                                  "เก่ามาก ไม่บอกเวอร์ชัน" if v == "0" else v)
                      for uid, v in ext_versions.items()
                      if parse_version(v) < parse_version(APP_VERSION)})
        # เอาเวอร์ชันขึ้นหัวหน้าต่างด้วย ถ่ายรูปหน้าจอส่งมารูปเดียวก็รู้แล้วว่าตัวไหนตกรุ่น
        seen = sorted({"เก่ามาก" if v == "0" else v for v in ext_versions.values()})
        self.frame.winfo_toplevel().title(
            "Auto Messenger v%s%s" % (APP_VERSION,
                                      " | ส่วนขยาย " + ", ".join(seen) if seen else ""))
        if old:
            self.lbl_ext.config(
                text="⚠️ โปรไฟล์ที่ยังใช้ส่วนขยายเวอร์ชันเก่า (%s)\n"
                     "ปิด Chrome ให้หมดแล้วเปิดใหม่ ถ้ายังเตือนอยู่แปลว่าโปรไฟล์นั้น "
                     "Load unpacked มาจากคนละโฟลเดอร์" % ", ".join(old))
        elif self.ext_note:
            self.lbl_ext.config(text=self.ext_note, fg="#dc3545")
        elif ext_versions:
            self.lbl_ext.config(text="✅ ส่วนขยายทุกโปรไฟล์เป็นเวอร์ชันล่าสุด", fg="#198754")
        else:
            self.lbl_ext.config(text="")
        self.frame.after(3000, self.refresh_ext_status)

    def _ui(self, fn):
        """สั่งงาน widget จากเธรดอื่นไม่ได้ ต้องโยนกลับเข้าลูปหลักก่อน"""
        self.frame.after(0, fn)

    def _auto_update_extension(self, tag, ext_url):
        """ทับโฟลเดอร์ส่วนขยายให้เลยตอนเปิดโปรแกรม ไม่ต้องรอใครกด

        ponytail: ส่วนขยายเป็นแค่ไฟล์บนดิสก์ ทับได้ทันที Chrome อ่านของใหม่ตอนเปิดครั้งหน้าเอง
        ตัวโปรแกรมเองทำแบบนี้ไม่ได้ (Windows แทนที่ .exe ที่รันอยู่ไม่ได้) เลยยังต้องมีปุ่ม
        หาโฟลเดอร์ไม่เจอก็เงียบไว้ ไม่เด้งถาม — ค่อยไปถามตอนกดปุ่มอัปเดต
        """
        d = find_ext_dir()
        if not d:
            return
        try:
            with open(os.path.join(d, "manifest.json"), encoding="utf-8") as f:
                if parse_version(json.load(f).get("version")) >= parse_version(tag):
                    return   # ทับไปแล้วรอบก่อน ไม่ต้องโหลดซ้ำ
            update_extension(ext_url, d, expect_version=tag)
        except Exception as e:
            # แค่ตั้งตัวแปร ไม่แตะ widget เลย เธรดไหนตั้งก็ได้ refresh_ext_status เอาไปแสดงเอง
            self.ext_note = "⚠️ อัปเดตส่วนขยายอัตโนมัติไม่สำเร็จ: %s" % e
            return
        # ไม่ต้องขึ้นข้อความบอก — refresh_ext_status จะเตือนเองว่า Chrome ยังใช้ตัวเก่าอยู่
        self.ext_note = ""

    def _check_update_thread(self):
        found = check_update()
        if found and found[2]:
            self._auto_update_extension(found[0], found[2])
        def show():
            if not found:
                self.lbl_update.config(text="✅ ใช้เวอร์ชันล่าสุดอยู่แล้ว", fg="#198754")
                self.btn_update.pack_forget()
                return
            tag, url, ext_url = found
            self.new_release = (tag, url, ext_url)
            self.lbl_update.config(text=f"🎉 มีเวอร์ชันใหม่: {tag}", fg="#dc3545")
            self.btn_update.pack(fill="x")
        self._ui(show)

    def action_update(self):
        if not self.new_release:
            return
        tag, url, ext_url = self.new_release
        self.btn_update.config(state="disabled")

        # หาโฟลเดอร์ส่วนขยายตอนนี้เลย ยังอยู่บนเธรดหลัก เปิดหน้าต่างเลือกโฟลเดอร์ได้
        ext_dir = find_ext_dir() if ext_url else None
        if ext_url and not ext_dir:
            messagebox.showinfo("หาโฟลเดอร์ส่วนขยายไม่เจอ",
                                "ไม่พบโฟลเดอร์ extension ข้าง ๆ โปรแกรม\n"
                                "เลือกโฟลเดอร์ที่ Chrome โหลดส่วนขยายอยู่ (โฟลเดอร์ที่มี manifest.json)")
            picked = filedialog.askdirectory(title="เลือกโฟลเดอร์ส่วนขยาย")
            if picked and os.path.isfile(os.path.join(picked, "manifest.json")):
                save_ext_dir(picked)   # จำไว้ ครั้งหน้าไม่ต้องถามอีก
                ext_dir = picked

        def worker():
            def prog(got, total):
                pct = f"{got * 100 // total}%" if total else f"{got // 1048576} MB"
                self._ui(lambda: self.lbl_update.config(text=f"⏳ กำลังโหลด {tag} ... {pct}", fg="#ffc107"))

            # ส่วนขยายก่อน เพราะขั้นถัดไปโปรแกรมจะปิดตัวเองเพื่อสลับ .exe
            # พลาดตรงนี้ไม่ล้มทั้งงาน แค่ต้องเอาโฟลเดอร์ไปวางเองเหมือนเดิม
            if ext_url and not ext_dir:
                self._ui(lambda: self.lbl_ext.config(
                    text="⚠️ ไม่ได้เลือกโฟลเดอร์ส่วนขยาย จะอัปเดตให้แค่ตัวโปรแกรม\n"
                         "ส่วนขยายต้องเอาไปวางทับเอง", fg="#dc3545"))
            elif ext_url:
                self._ui(lambda: self.lbl_update.config(text="⏳ กำลังอัปเดตส่วนขยาย...", fg="#ffc107"))
                try:
                    n = update_extension(ext_url, ext_dir, expect_version=tag)
                    self._ui(lambda: self.lbl_ext.config(
                        text="✅ อัปเดตส่วนขยายแล้ว %d ไฟล์ — ปิด Chrome ให้หมดแล้วเปิดใหม่\n"
                             "ถ้ายังขึ้นเตือนว่าเวอร์ชันเก่า กด Reload ที่ chrome://extensions "
                             "ครั้งเดียว" % n, fg="#198754"))
                except Exception as e:
                    m = str(e)
                    self._ui(lambda: self.lbl_ext.config(
                        text="⚠️ อัปเดตส่วนขยายไม่สำเร็จ: %s" % m, fg="#dc3545"))
            try:
                download_and_restart(url, prog)
            except Exception as e:
                msg = str(e)
                self._ui(lambda: self.lbl_update.config(text=f"❌ อัปเดตไม่สำเร็จ: {msg}", fg="#dc3545"))
                self._ui(lambda: self.btn_update.config(state="normal"))
                return
            self._ui(lambda: self.lbl_update.config(text="✅ โหลดเสร็จ กำลังปิดโปรแกรมเพื่อติดตั้ง...", fg="#198754"))
            self._ui(lambda: self.frame.after(1200, root.destroy))

        threading.Thread(target=worker, daemon=True).start()

    def _open_chrome_thread(self, count):
        self.lbl_status.config(text=f"⏳ กำลังทะยอยเปิด Chrome... (0/{count})", fg="#ffc107")

        for i in range(1, count + 1):
            profile_name = f"Profile {10+i}"
            try:
                subprocess.Popen([self.chrome_path, f"--profile-directory={profile_name}"] + CHROME_NO_THROTTLE_FLAGS)
            except Exception as e:
                print(f"Error: {e}")

            # อัปเดตสถานะให้ผู้ใช้เห็น
            self.lbl_status.config(text=f"⏳ กำลังทะยอยเปิด Chrome... ({i}/{count}) [โพรไฟล์: {profile_name}]")
            # หน่วงเวลา 0.5 วินาทีต่อหน้าต่าง เพื่อไม่ให้ CPU โหลดหนักจนคอมค้าง
            time.sleep(0.5)

        self.lbl_status.config(text=f"✅ เปิด Chrome เสร็จสิ้นจำนวน {count} หน้าต่างเรียบร้อยแล้ว!", fg="#198754")

    def action_open_chrome(self):
        try:
            count = int(self.spin_count.get())
            if count < 1 or count > self.max_profiles:
                messagebox.showwarning("แจ้งเตือน", f"กรุณาใส่จำนวนระหว่าง 1 ถึง {self.max_profiles}")
                return

            if not os.path.exists(self.chrome_path):
                messagebox.showerror("ข้อผิดพลาด",
                                     f"ไม่พบ Google Chrome ในเครื่องของคุณที่ Path:\n{self.chrome_path}\nกรุณาติดตั้งหรือเช็ค Path")
                return

            # สั่งให้การเปิด Chrome ทำงานแบบเบื้องหลัง (Thread) โปรแกรมจะได้ไม่ค้าง
            threading.Thread(target=self._open_chrome_thread, args=(count,), daemon=True).start()

        except ValueError:
            messagebox.showerror("ข้อผิดพลาด", "กรุณาใส่ตัวเลขให้ถูกต้อง")


class PresetTab:
    def __init__(self, notebook, preset_key):
        self.preset_key = preset_key
        self.frame = ttk.Frame(notebook)

        self.var_sys_on = tk.BooleanVar(value=False)
        self.var_mode = tk.StringVar(value="messenger")
        self.var_is_page = tk.BooleanVar(value=False)
        self.var_mode.trace_add("write", self.update_mode_label)

        self.setup_ui()

    def update_preview(self, event=None):
        msg = self.text_msg.get("1.0", tk.END).strip()
        limit = self.spin_limit.get()
        if not msg: msg = "(ว่าง)"
        self.lbl_preview_msg.config(text=f'"{msg}"')
        self.lbl_preview_limit.config(text=f'(🔥 ส่งต่อเนื่องทั้งหมด {limit} ครั้ง)')

    def on_switch_toggle(self, state):
        self.var_sys_on.set(state)
        self.lbl_sys_text.config(fg="#198754" if state else "#dc3545")

    def action_toggle_reload(self, state):
        if not self.var_sys_on.get():
            messagebox.showwarning("แจ้งเตือน", "กรุณาเปิดระบบก่อนสั่งงาน!")
            self.sw_reload.set_state(False)
            return

        self.lbl_reload_text.config(fg="#198754" if state else "#6c757d")

        task_id = int(time.time())
        action = "start_auto_monitor" if state else "stop_auto_monitor"

        p_data = presets_data[self.preset_key]
        p_data["is_system_on"] = True
        p_data["mode"] = self.var_mode.get()
        p_data["url_post"] = self.entry_url_post.get().strip()
        p_data["message_text"] = self.text_msg.get("1.0", tk.END).strip()
        p_data["is_page_link"] = self.var_is_page.get()
        try:
            p_data["msg_limit"] = int(self.spin_limit.get())
        except ValueError:
            p_data["msg_limit"] = 1
        p_data["action_type"] = action
        p_data["current_task_id"] = task_id

        targets = ["profile_1", "profile_2", "profile_3"] if self.preset_key == "profile_all" else [self.preset_key]
        for k in targets:
            if k != self.preset_key:
                presets_data[k]["is_system_on"] = True
                presets_data[k]["mode"] = p_data["mode"]
                presets_data[k]["url_post"] = p_data["url_post"]
                presets_data[k]["message_text"] = p_data["message_text"]
                presets_data[k]["msg_limit"] = p_data["msg_limit"]
                presets_data[k]["is_page_link"] = p_data["is_page_link"]
                presets_data[k]["action_type"] = action
                presets_data[k]["current_task_id"] = task_id

        self.update_display_db()

    def set_msg_widgets_visible(self, visible):
        widgets = [(self.lbl_msg_head, {"anchor": "w"}),
                   (self.text_msg, {"fill": "x", "pady": (2, 5)}),
                   (self.frame_limit, {"fill": "x"}),
                   (self.frame_preview, {"fill": "x", "pady": 5})]
        for w, opts in widgets:
            w.pack_forget()
        if visible:
            for w, opts in widgets:
                w.pack(before=self.btn_send, **opts)

    def update_mode_label(self, *args):
        mode = self.var_mode.get()
        self.lbl_url_msg.pack_forget()
        self.entry_url_msg.pack_forget()
        self.chk_is_page.pack_forget()
        self.lbl_url_live.pack_forget()
        self.entry_url_live.pack_forget()
        self.lbl_url_post.pack_forget()
        self.entry_url_post.pack_forget()
        self.frame_reload.pack_forget()

        # ไลค์/แชร์ ไม่ต้องพิมพ์ข้อความ ใช้แค่ URL โพสต์
        # ponytail: ซ่อนแค่ช่องข้อความ ไม่ย้ายปุ่มส่ง ย้าย widget ข้าม frame แล้วลำดับเพี้ยน
        if mode in ["like", "share"]:
            self.lbl_url_post.config(text="👍 URL โพสต์ที่จะกดไลค์:" if mode == "like"
                                          else "🔁 URL โพสต์ที่จะแชร์:")
            self.lbl_url_post.pack(anchor="w", pady=(2, 0))
            self.entry_url_post.pack(fill="x", pady=(0, 2))
            self.set_msg_widgets_visible(False)
            self.btn_send.config(text="👍 2. กดไลค์ [ปุ่ม Enter]" if mode == "like"
                                      else "🔁 2. แชร์โพสต์ [ปุ่ม Enter]")
            return

        self.lbl_url_post.config(text="📝 URL โปรไฟล์ (คอมเมนต์โพสต์ล่าสุด):")
        self.btn_send.config(text="🚀 2. ส่งข้อความ / คอมเมนต์ [ปุ่ม Enter]")
        self.set_msg_widgets_visible(True)

        if mode in ["messenger", "all"]:
            self.lbl_url_msg.pack(anchor="w", pady=(2, 0))
            self.entry_url_msg.pack(fill="x", pady=(0, 2))
            self.chk_is_page.pack(anchor="w", pady=(0, 5))
        if mode in ["live", "all"]:
            self.lbl_url_live.pack(anchor="w", pady=(2, 0))
            self.entry_url_live.pack(fill="x", pady=(0, 2))
        if mode in ["post", "all"]:
            self.lbl_url_post.pack(anchor="w", pady=(2, 0))
            self.entry_url_post.pack(fill="x", pady=(0, 2))
            self.frame_reload.pack(anchor="w", pady=(2, 5))

    def action_paste_url(self):
        try:
            clipboard_text = self.frame.clipboard_get().strip()
            mode = self.var_mode.get()

            if mode in ["messenger", "all"]:
                self.entry_url_msg.delete(0, tk.END)
                self.entry_url_msg.insert(0, clipboard_text)
            if mode in ["live", "all"]:
                self.entry_url_live.delete(0, tk.END)
                self.entry_url_live.insert(0, clipboard_text)
            if mode in ["post", "all", "like", "share"]:
                self.entry_url_post.delete(0, tk.END)
                self.entry_url_post.insert(0, clipboard_text)
        except tk.TclError:
            pass

    def action_setup(self):
        if not self.var_sys_on.get():
            messagebox.showwarning("แจ้งเตือน", f"กรุณาเปิดระบบก่อนสั่งงาน!")
            return

        self.sw_reload.set_state(False)
        self.lbl_reload_text.config(fg="#6c757d")

        task_id = int(time.time())

        p_data = presets_data[self.preset_key]
        p_data["is_system_on"] = True
        p_data["mode"] = self.var_mode.get()
        p_data["url_messenger"] = self.entry_url_msg.get().strip()
        p_data["url_live"] = self.entry_url_live.get().strip()
        p_data["url_post"] = self.entry_url_post.get().strip()
        p_data["is_page_link"] = self.var_is_page.get()
        p_data["action_type"] = "setup"
        p_data["current_task_id"] = task_id

        targets = ["profile_1", "profile_2", "profile_3"] if self.preset_key == "profile_all" else [self.preset_key]

        for k in targets:
            if k != self.preset_key:
                presets_data[k]["is_system_on"] = True
                presets_data[k]["mode"] = self.var_mode.get()
                presets_data[k]["url_messenger"] = self.entry_url_msg.get().strip()
                presets_data[k]["url_live"] = self.entry_url_live.get().strip()
                presets_data[k]["url_post"] = self.entry_url_post.get().strip()
                presets_data[k]["is_page_link"] = self.var_is_page.get()
                presets_data[k]["action_type"] = "setup"
                presets_data[k]["current_task_id"] = task_id

        self.update_display_db()

    def action_send(self):
        if not self.var_sys_on.get():
            messagebox.showwarning("แจ้งเตือน", f"กรุณาเปิดระบบก่อนสั่งงาน!")
            return

        self.sw_reload.set_state(False)
        self.lbl_reload_text.config(fg="#6c757d")

        task_id = int(time.time())

        p_data = presets_data[self.preset_key]
        p_data["is_system_on"] = True
        p_data["mode"] = self.var_mode.get()
        p_data["url_messenger"] = self.entry_url_msg.get().strip()
        p_data["url_live"] = self.entry_url_live.get().strip()
        p_data["url_post"] = self.entry_url_post.get().strip()
        p_data["message_text"] = self.text_msg.get("1.0", tk.END).strip()
        p_data["is_page_link"] = self.var_is_page.get()
        try:
            p_data["msg_limit"] = int(self.spin_limit.get())
        except ValueError:
            p_data["msg_limit"] = 1

        p_data["action_type"] = "send"
        p_data["current_task_id"] = task_id

        targets = ["profile_1", "profile_2", "profile_3"] if self.preset_key == "profile_all" else [self.preset_key]

        for k in targets:
            if k != self.preset_key:
                presets_data[k]["is_system_on"] = True
                presets_data[k]["mode"] = self.var_mode.get()
                presets_data[k]["message_text"] = p_data["message_text"]
                presets_data[k]["msg_limit"] = p_data["msg_limit"]
                presets_data[k]["url_messenger"] = p_data["url_messenger"]
                presets_data[k]["url_live"] = p_data["url_live"]
                presets_data[k]["url_post"] = p_data["url_post"]
                presets_data[k]["is_page_link"] = p_data["is_page_link"]
                presets_data[k]["action_type"] = "send"
                presets_data[k]["current_task_id"] = task_id

        self.update_display_db()

    def update_display_db(self):
        p_data = presets_data[self.preset_key]
        self.lbl_db_sys.config(text="เปิด" if p_data["is_system_on"] else "ปิด",
                               fg="#198754" if p_data["is_system_on"] else "#dc3545")

        mode_str = "Messenger"
        if p_data["mode"] == "live":
            mode_str = "Live Comment"
        elif p_data["mode"] == "post":
            mode_str = "Post Comment"
        elif p_data["mode"] == "like":
            mode_str = "👍 กดไลค์โพสต์"
        elif p_data["mode"] == "share":
            mode_str = "🔁 แชร์โพสต์"
        elif p_data["mode"] == "all":
            mode_str = "ทั้งหมด (Msg+Live+Post)"

        if p_data["mode"] in ["messenger", "all"] and p_data.get("is_page_link"):
            mode_str += " (ทักหน้าเพจ)"

        self.lbl_db_mode.config(text=mode_str)

        url_display = "-"
        if p_data["mode"] == "messenger":
            url_display = p_data["url_messenger"]
        elif p_data["mode"] == "live":
            url_display = p_data["url_live"]
        elif p_data["mode"] in ("post", "like", "share"):
            url_display = p_data["url_post"]
        elif p_data["mode"] == "all":
            url_display = f"1: {p_data['url_messenger']}\n2: {p_data['url_live']}\n3: {p_data['url_post']}"

        self.lbl_db_url.config(text=url_display if url_display.strip() else "-")
        self.lbl_db_action.config(text=p_data["action_type"].upper() if p_data["action_type"] else "-")

    def setup_ui(self):
        frame_top = ttk.LabelFrame(self.frame, text=" ⚙️ 1. โหมดการทำงาน & เป้าหมาย ", padding=5)
        frame_top.pack(fill="x", padx=10, pady=2)
        self.frame_top = frame_top

        frame_switch = tk.Frame(frame_top, bg="#f4f6f9")
        frame_switch.pack(anchor="w", pady=(0, 5))

        self.sw_sys = ToggleSwitch(frame_switch, state=self.var_sys_on.get(), command=self.on_switch_toggle,
                                   bg_color="#f4f6f9")
        self.sw_sys.pack(side="left")

        self.lbl_sys_text = tk.Label(frame_switch, text="เปิดใช้งานระบบ (System ON)", font=("Angsana New", 16, "bold"),
                                     bg="#f4f6f9", fg="#dc3545")
        self.lbl_sys_text.pack(side="left", padx=(10, 0))

        frame_mode = tk.Frame(frame_top, bg="#e9ecef", padx=5, pady=5)
        frame_mode.pack(fill="x", pady=(0, 5))
        tk.Label(frame_mode, text="เลือกโหมดทำงาน:", bg="#e9ecef", font=("Angsana New", 14, "bold")).pack(anchor="w",
                                                                                                          pady=(0, 0))

        ttk.Radiobutton(frame_mode, text="💬 Messenger", variable=self.var_mode, value="messenger", takefocus=0).pack(
            side="left", padx=(0, 10))
        ttk.Radiobutton(frame_mode, text="🔴 คอมเมนต์ไลฟ์", variable=self.var_mode, value="live", takefocus=0).pack(
            side="left", padx=(0, 10))
        ttk.Radiobutton(frame_mode, text="📝 คอมเมนต์โพสต์", variable=self.var_mode, value="post", takefocus=0).pack(
            side="left", padx=(0, 10))
        ttk.Radiobutton(frame_mode, text="🔥 ทั้งหมด", variable=self.var_mode, value="all", takefocus=0).pack(
            side="left")

        frame_mode2 = tk.Frame(frame_top, bg="#e9ecef", padx=5, pady=5)
        frame_mode2.pack(fill="x", pady=(0, 5))
        ttk.Radiobutton(frame_mode2, text="👍 กดไลค์โพสต์", variable=self.var_mode, value="like",
                        takefocus=0).pack(side="left", padx=(0, 10))
        ttk.Radiobutton(frame_mode2, text="🔁 แชร์โพสต์", variable=self.var_mode, value="share",
                        takefocus=0).pack(side="left")

        self.frame_urls = tk.Frame(frame_top, bg="#f4f6f9")
        self.frame_urls.pack(fill="x", pady=(2, 5))

        self.lbl_url_msg = ttk.Label(self.frame_urls, text="🔗 URL Messenger เป้าหมาย:")
        self.entry_url_msg = ttk.Entry(self.frame_urls, width=50, font=("Angsana New", 14))

        self.chk_is_page = ttk.Checkbutton(self.frame_urls,
                                           text="✅ นี่คือลิงก์หน้าเพจ (บอทจะกด 'ส่งข้อความ' และ 'เริ่มต้นใช้งาน' ให้อัตโนมัติ)",
                                           variable=self.var_is_page, takefocus=0)

        self.lbl_url_live = ttk.Label(self.frame_urls, text="🔴 URL สตรีมไลฟ์สด:")
        self.entry_url_live = ttk.Entry(self.frame_urls, width=50, font=("Angsana New", 14))

        self.lbl_url_post = ttk.Label(self.frame_urls, text="📝 URL โปรไฟล์ (คอมเมนต์โพสต์ล่าสุด):")
        self.entry_url_post = ttk.Entry(self.frame_urls, width=50, font=("Angsana New", 14))

        self.frame_reload = tk.Frame(self.frame_urls, bg="#f4f6f9")
        self.sw_reload = ToggleSwitch(self.frame_reload, state=False, command=self.action_toggle_reload,
                                      bg_color="#f4f6f9")
        self.sw_reload.pack(side="left")
        self.lbl_reload_text = tk.Label(self.frame_reload, text="Auto Comment (จับตาดูรูปล่าสุด & พิมพ์ให้อัตโนมัติ)",
                                        font=("Angsana New", 14, "bold"), bg="#f4f6f9", fg="#6c757d")
        self.lbl_reload_text.pack(side="left", padx=(10, 0))

        frame_setup_btns = tk.Frame(frame_top, bg="#f4f6f9")
        frame_setup_btns.pack(fill="x", pady=(2, 0))

        btn_bg = "#dc3545" if self.preset_key == "profile_all" else "#0dcaf0"
        btn_fg = "white" if self.preset_key == "profile_all" else "black"

        tk.Button(frame_setup_btns, text="🛠 1. สั่งเปิดหน้าเว็บ (Setup Tab)", bg=btn_bg, fg=btn_fg,
                  font=("Angsana New", 16, "bold"), relief="flat", pady=2, takefocus=0, command=self.action_setup).pack(
            side="left", fill="x", expand=True, padx=(0, 5))

        tk.Button(frame_setup_btns, text="📋 วาง URL (กดปุ่ม V / อ)", bg="#ffc107", fg="black",
                  font=("Angsana New", 16, "bold"), relief="flat", pady=2, takefocus=0,
                  command=self.action_paste_url).pack(side="right")

        frame_msg = ttk.LabelFrame(self.frame, text=" 💬 2. ตั้งค่าข้อความ ", padding=5)
        frame_msg.pack(fill="x", padx=10, pady=2)
        self.frame_msg = frame_msg

        self.lbl_msg_head = ttk.Label(frame_msg, text="ข้อความที่จะส่ง:")
        self.lbl_msg_head.pack(anchor="w")

        self.text_msg = tk.Text(frame_msg, height=2, width=50, font=("Angsana New", 16), relief="solid", bd=1)
        self.text_msg.insert("1.0", "ทักครับ")
        self.text_msg.pack(fill="x", pady=(2, 5))
        self.text_msg.bind("<KeyRelease>", self.update_preview)

        self.frame_limit = ttk.Frame(frame_msg)
        self.frame_limit.pack(fill="x")
        ttk.Label(self.frame_limit, text="จำนวนครั้งที่ส่ง:").pack(side="left")
        self.spin_limit = ttk.Spinbox(self.frame_limit, from_=1, to=1000, width=5, font=("Angsana New", 14),
                                      command=self.update_preview)
        self.spin_limit.set(1)
        self.spin_limit.pack(side="left", padx=5)
        self.spin_limit.bind("<KeyRelease>", self.update_preview)

        self.frame_preview = tk.Frame(frame_msg, bg="#e9ecef", padx=5, pady=5)
        self.frame_preview.pack(fill="x", pady=5)
        tk.Label(self.frame_preview, text="👀 พรีวิวการทำงาน:", bg="#e9ecef", font=("Angsana New", 14, "bold"),
                 fg="#495057").pack(anchor="w")

        self.lbl_preview_msg = tk.Label(self.frame_preview, text='"ทักครับ"', bg="#e9ecef",
                                        font=("Angsana New", 20, "bold"),
                                        fg="#0d6efd", justify="left", wraplength=350)
        self.lbl_preview_msg.pack(anchor="w", pady=(0, 0))
        self.lbl_preview_limit = tk.Label(self.frame_preview, text='(🔥 ส่งต่อเนื่องทั้งหมด 1 ครั้ง)', bg="#e9ecef",
                                          font=("Angsana New", 14), fg="#0d6efd", justify="left")
        self.lbl_preview_limit.pack(anchor="w", pady=(0, 0))

        self.btn_send = tk.Button(frame_msg, text="🚀 2. ส่งข้อความ / คอมเมนต์ [ปุ่ม Enter]", bg="#198754",
                                  fg="white", font=("Angsana New", 16, "bold"), relief="flat", pady=2, takefocus=0,
                                  command=self.action_send)
        self.btn_send.pack(fill="x")

        # เรียกทีหลังสุด ต้องให้ widget ทุกตัวมีอยู่ก่อน (โหมดไลค์/แชร์สั่งซ่อนช่องข้อความ)
        self.update_mode_label()

        frame_status = ttk.LabelFrame(self.frame, text=" 📊 สถานะล่าสุด ", padding=5)
        frame_status.pack(fill="both", expand=True, padx=10, pady=2)

        ttk.Label(frame_status, text="ระบบ:").grid(row=0, column=0, sticky="e", pady=0)
        self.lbl_db_sys = tk.Label(frame_status, text="ปิด", fg="#dc3545", bg="#f4f6f9",
                                   font=("Angsana New", 14, "bold"))
        self.lbl_db_sys.grid(row=0, column=1, sticky="w", padx=5)

        ttk.Label(frame_status, text="โหมด:").grid(row=1, column=0, sticky="e", pady=0)
        self.lbl_db_mode = tk.Label(frame_status, text="-", fg="#6f42c1", bg="#f4f6f9",
                                    font=("Angsana New", 14, "bold"))
        self.lbl_db_mode.grid(row=1, column=1, sticky="w", padx=5)

        ttk.Label(frame_status, text="คำสั่งล่าสุด:").grid(row=2, column=0, sticky="e", pady=0)
        self.lbl_db_action = tk.Label(frame_status, text="-", fg="#0d6efd", bg="#f4f6f9",
                                      font=("Angsana New", 14, "bold"))
        self.lbl_db_action.grid(row=2, column=1, sticky="w", padx=5)

        ttk.Label(frame_status, text="URL:").grid(row=3, column=0, sticky="ne", pady=0)
        self.lbl_db_url = tk.Label(frame_status, text="-", bg="#f4f6f9", font=("Angsana New", 12), wraplength=320,
                                   justify="left")
        self.lbl_db_url.grid(row=3, column=1, sticky="w", padx=5)


# --- สร้างหน้าต่างหลัก ---
root = tk.Tk()
root.title(f"Auto Messenger v{APP_VERSION}")
root.geometry("580x995+0+0")
root.resizable(True, True)
root.configure(bg="#f4f6f9")

style = ttk.Style()
style.theme_use('clam')
style.configure("TFrame", background="#f4f6f9")
style.configure("TLabelframe", background="#f4f6f9", font=("Angsana New", 16, "bold"))
style.configure("TLabel", background="#f4f6f9", font=("Angsana New", 14))
style.configure("TRadiobutton", background="#f4f6f9", font=("Angsana New", 14, "bold"))

tk.Label(root, text="Auto Messenger and comment", font=("Angsana New", 20, "bold"), bg="#f4f6f9", fg="#2c3e50").pack(
    pady=5)

notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True, padx=10, pady=5)

tabs_list = []

tab1 = PresetTab(notebook, "profile_1")
notebook.add(tab1.frame, text="📁Preset 1 ")
tabs_list.append(tab1)

tab2 = PresetTab(notebook, "profile_2")
notebook.add(tab2.frame, text="📁Preset 2 ")
tabs_list.append(tab2)

tab3 = PresetTab(notebook, "profile_3")
notebook.add(tab3.frame, text="📁Preset 3 ")
tabs_list.append(tab3)

tab4 = PresetTab(notebook, "profile_all")
notebook.add(tab4.frame, text="🌐Preset 4 (ส่งทั้งหมด) ")
tabs_list.append(tab4)

# 🟢 เพิ่มแท็บ Setup Chrome ไว้เป็นแท็บสุดท้าย
tab_chrome = SetupChromeTab(notebook)
notebook.add(tab_chrome.frame, text="🌐 Setup Chrome ")


def process_ui_commands():
    while ui_command_queue:
        cmd = ui_command_queue.pop(0)
        if cmd == "turn_off_auto":
            for tab in tabs_list:
                tab.sw_reload.set_state(False)
                tab.lbl_reload_text.config(fg="#6c757d")
                presets_data[tab.preset_key]["action_type"] = "stop_auto_monitor"
                tab.update_display_db()
    root.after(500, process_ui_commands)


# ==========================================
# 5. ฟังก์ชันจัดการ Keyboard Shortcuts (แบบเจาะจงรายปุ่ม)
# ==========================================

def handle_select_all(event):
    widget = event.widget
    w_class = widget.winfo_class()
    if w_class in ('Entry', 'Text', 'TEntry', 'TSpinbox'):
        if w_class == 'Text':
            widget.tag_add("sel", "1.0", "end")
        else:
            widget.select_range(0, tk.END)
            widget.icursor(tk.END)
        return "break"

def handle_copy(event):
    widget = event.widget
    if widget.winfo_class() in ('Entry', 'Text', 'TEntry', 'TSpinbox'):
        widget.event_generate("<<Copy>>")
        return "break"

def handle_paste(event):
    widget = event.widget
    if widget.winfo_class() in ('Entry', 'Text', 'TEntry', 'TSpinbox'):
        widget.event_generate("<<Paste>>")
        return "break"

def handle_cut(event):
    widget = event.widget
    if widget.winfo_class() in ('Entry', 'Text', 'TEntry', 'TSpinbox'):
        widget.event_generate("<<Cut>>")
        return "break"

def handle_undo(event):
    widget = event.widget
    if widget.winfo_class() in ('Entry', 'Text', 'TEntry', 'TSpinbox'):
        widget.event_generate("<<Undo>>")
        return "break"

def shortcut_send(event):
    """ ปุ่ม Enter สำหรับส่งข้อความ """
    widget_class = event.widget.winfo_class()
    if widget_class == 'Text' and (event.state & 0x0001): # Shift+Enter ใน Text
        return
    current_tab_idx = notebook.index("current")
    if current_tab_idx < len(tabs_list):
        current_tab = tabs_list[current_tab_idx]
        current_tab.action_send()
        return "break" # คืนค่า break เฉพาะเมื่ออยู่ในหน้า Preset

def global_paste_handler(event):
    """ ฟังก์ชันสำหรับกดปุ่ม v หรือ อ เพื่อวาง URL อัตโนมัติ (เมื่อไม่ได้อยู่ในช่องพิมพ์) """
    widget_class = event.widget.winfo_class()
    # ถ้าโฟกัสอยู่ในช่องกรอกข้อมูล ให้ทำงานเป็นตัวอักษรปกติ ไม่ต้องวาง URL
    if widget_class in ('Entry', 'Text', 'TEntry', 'TSpinbox'):
        return

    char = getattr(event, "char", "")
    keysym = event.keysym.lower()
    
    # เช็คว่าใช่ปุ่ม v/V หรือ อ/ฮ หรือไม่
    is_v = char in ('v', 'V', 'อ', 'ฮ') or keysym in ('v', 'th_kokaile')
    
    if is_v:
        current_tab_idx = notebook.index("current")
        if current_tab_idx < len(tabs_list):
            current_tab = tabs_list[current_tab_idx]
            current_tab.action_paste_url()
            return "break" # คืนค่า break เฉพาะเมื่อวาง URL จริงๆ เท่านั้น

# --- การ Binding แบบเจาะจง (Specific Binding) ---

def safe_bind(event_str, func):
    try:
        root.bind_all(event_str, func)
    except:
        pass

# --- การ Binding แบบเจาะจงราย Class เพื่อป้องกันการวางเบิ้ล (Double Paste Fix) ---
for cls in ('Entry', 'Text', 'TEntry', 'TSpinbox'):
    root.bind_class(cls, "<Control-a>", handle_select_all)
    root.bind_class(cls, "<Control-A>", handle_select_all)
    root.bind_class(cls, "<Control-c>", handle_copy)
    root.bind_class(cls, "<Control-C>", handle_copy)
    root.bind_class(cls, "<Control-v>", handle_paste)
    root.bind_class(cls, "<Control-V>", handle_paste)
    root.bind_class(cls, "<Control-x>", handle_cut)
    root.bind_class(cls, "<Control-X>", handle_cut)
    root.bind_class(cls, "<Control-z>", handle_undo)
    root.bind_class(cls, "<Control-Z>", handle_undo)

# --- คืนค่าปุ่มลัดพิเศษสำหรับวาง URL (v / อ) แบบเจาะจงรายปุ่ม ---
safe_bind("v", global_paste_handler)
safe_bind("V", global_paste_handler)
safe_bind("อ", global_paste_handler)
safe_bind("ฮ", global_paste_handler)
safe_bind("<Key-v>", global_paste_handler)
safe_bind("<Key-V>", global_paste_handler)
safe_bind("<Key-อ>", global_paste_handler)
safe_bind("<Key-ฮ>", global_paste_handler)

# ปุ่ม Enter สำหรับส่งข้อความ (จำเป็นต้องมี)
root.bind_all("<Return>", shortcut_send)

# ใช้ <Key> เพื่อดักจับ 'อ' ในระดับ Global (ฟังก์ชัน global_paste_handler จะเช็ค Widget เอง)
root.bind_all("<Key>", global_paste_handler)

if __name__ == '__main__':
    threading.Thread(target=run_api_server, daemon=True).start()
    root.after(500, process_ui_commands)
    root.mainloop()