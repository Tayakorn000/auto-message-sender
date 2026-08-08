"""เทสตัวเช็ค/ติดตั้งอัปเดต ยิงใส่เซิร์ฟเวอร์จำลองในเครื่อง ไม่แตะ GitHub จริง

เช็ค:
- เทียบเวอร์ชันถูก (ใหม่กว่า/เท่ากัน/เก่ากว่า/รูปแบบแปลก)
- เน็ตล่ม/รีโป private = คืน None ไม่โยน exception ใส่หน้าโปรแกรม
- รับเฉพาะไฟล์ .exe จากโดเมน github.com
- โหลดไฟล์ครบ เขียน .bat สลับไฟล์ถูก และไฟล์ไม่ครบต้องไม่ผ่าน

รัน: python3 test_update.py
"""
import http.server
import json
import os
import socketserver
import sys
import tempfile
import threading
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("AUTOSENDER_NO_UPDATE_CHECK", "1")
import main  # noqa: E402

PORT = 8786
STATE = {"release": {}, "exe": b"x" * 2_000_000}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/release":
            body = json.dumps(STATE["release"]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        elif self.path == "/404":
            self.send_response(404)
            self.end_headers()
            return
        else:
            body = STATE["exe"]
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def check(cond, msg):
    if not cond:
        sys.exit("FAIL: " + msg)


socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % PORT
main.UPDATE_API = BASE + "/release"

# --- เทียบเวอร์ชัน ---
check(main.parse_version("V1.5.0") == (1, 5, 0), "parse V1.5.0")
check(main.parse_version("1.10.0") > main.parse_version("1.9.9"), "1.10 ต้องใหม่กว่า 1.9.9")
check(main.parse_version("") == (0,), "สตริงว่างต้องไม่พัง")

GH = "https://github.com/Tayakorn000/auto-message-sender/releases/download"
main.APP_VERSION = "1.6.0"


def release(tag, assets):
    STATE["release"] = {"tag_name": tag, "assets": assets}


EXE = [{"name": "Auto_message.V1.7.0.exe", "browser_download_url": GH + "/V1.7.0/a.exe"}]

release("V1.7.0", EXE)
got = main.check_update()
check(got == ("V1.7.0", GH + "/V1.7.0/a.exe"), "เวอร์ชันใหม่กว่าต้องเจอ ได้ %r" % (got,))

release("V1.6.0", EXE)
check(main.check_update() is None, "เวอร์ชันเท่ากันต้องไม่เตือน")

release("V1.5.0", EXE)
check(main.check_update() is None, "เวอร์ชันเก่ากว่าต้องไม่เตือน")

# ไฟล์ที่ไม่ใช่ .exe / โดเมนนอก github ต้องไม่รับ
release("V1.7.0", [{"name": "note.txt", "browser_download_url": GH + "/V1.7.0/note.txt"}])
check(main.check_update() is None, "asset ที่ไม่ใช่ .exe ต้องไม่รับ")
release("V1.7.0", [{"name": "a.exe", "browser_download_url": "https://evil.example.com/a.exe"}])
check(main.check_update() is None, "URL นอก github.com ต้องไม่รับ")

# เน็ตล่ม / รีโป private (404) ต้องคืน None ไม่โยน exception
main.UPDATE_API = BASE + "/404"
check(main.check_update() is None, "404 ต้องคืน None ไม่ throw")
main.UPDATE_API = "http://127.0.0.1:1/nope"
check(main.check_update(timeout=2) is None, "ต่อไม่ติดต้องคืน None ไม่ throw")

# --- โหลดไฟล์ + เขียน .bat ---
tmp = tempfile.mkdtemp()
fake_exe = os.path.join(tmp, "main.exe")
open(fake_exe, "wb").write(b"old")

launched = []
main.sys = types.SimpleNamespace(frozen=True, executable=fake_exe)
main.subprocess = types.SimpleNamespace(Popen=lambda *a, **k: launched.append(a),
                                        CREATE_NO_WINDOW=0)

seen = []
main.download_and_restart(BASE + "/a.exe", lambda g, t: seen.append((g, t)))

new_file = fake_exe + ".new"
bat = fake_exe + ".update.bat"
check(os.path.exists(new_file), "ต้องมีไฟล์ .new")
check(os.path.getsize(new_file) == len(STATE["exe"]), "ไฟล์ .new ต้องครบ")
check(os.path.exists(bat), "ต้องเขียน .bat")
check(launched, "ต้องสั่งรัน .bat")
check(seen and seen[-1][0] == len(STATE["exe"]), "ต้องรายงานความคืบหน้าจนครบ")
body = open(bat, encoding="ascii").read()
check("move /y" in body and fake_exe in body, ".bat ต้องสลับไฟล์ตัวจริง")
check('start "" "%s"' % fake_exe in body, ".bat ต้องเปิดโปรแกรมกลับมา")
check("if %n% lss 30" in body, ".bat ต้องมีเพดานรอบ ไม่วนค้างตลอดกาล")

# ไฟล์ไม่ครบต้องไม่ผ่าน และต้องลบทิ้ง
os.remove(new_file)
os.remove(bat)
STATE["exe"] = b"tiny"
try:
    main.download_and_restart(BASE + "/a.exe")
    sys.exit("FAIL: ไฟล์เล็กผิดปกติต้อง raise")
except RuntimeError:
    pass
check(not os.path.exists(new_file), "ไฟล์ที่โหลดไม่ครบต้องถูกลบทิ้ง")

# รันจากซอร์ส (ไม่ใช่ .exe) ต้องบอกให้ชัด ไม่ไปเขียนทับ python.exe
main.sys = types.SimpleNamespace(frozen=False, executable="/usr/bin/python3")
try:
    main.download_and_restart(BASE + "/a.exe")
    sys.exit("FAIL: รันจากซอร์สต้อง raise")
except RuntimeError as e:
    check("exe" in str(e), "ข้อความควรบอกว่าใช้ได้กับ .exe เท่านั้น")

# --- ส่วนขยายบอกเวอร์ชันมาทาง /api/get-task ---
main.app.config.update(TESTING=True)
client = main.app.test_client()
client.get("/api/get-task/profile_1/uid_a?v=1.6.0")
client.get("/api/get-task/profile_1/uid_b?v=1.0")
check(main.ext_versions == {"uid_a": "1.6.0", "uid_b": "1.0"},
      "ต้องเก็บเวอร์ชันส่วนขยายรายโปรไฟล์ ได้ %r" % main.ext_versions)

tab = main.tab_chrome
tab.refresh_ext_status()
txt = tab.lbl_ext.cget("text")
check("1.0" in txt and "Reload" in txt, "ต้องเตือนโปรไฟล์ที่ใช้ส่วนขยายเก่า ได้ %r" % txt)

main.ext_versions.pop("uid_b")
tab.refresh_ext_status()
check("✅" in tab.lbl_ext.cget("text"), "ทุกโปรไฟล์ล่าสุดแล้วต้องไม่เตือน")

srv.shutdown()
print("OK: เช็คเวอร์ชัน โหลดไฟล์ สคริปต์สลับไฟล์ และเตือนส่วนขยายเก่า ทำงานถูก")
