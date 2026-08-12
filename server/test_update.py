"""เทสตัวเช็ค/ติดตั้งอัปเดต ยิงใส่เซิร์ฟเวอร์จำลองในเครื่อง ไม่แตะ GitHub จริง

เช็ค:
- เทียบเวอร์ชันถูก (ใหม่กว่า/เท่ากัน/เก่ากว่า/รูปแบบแปลก)
- เน็ตล่ม/รีโป private = คืน None ไม่โยน exception ใส่หน้าโปรแกรม
- รับเฉพาะไฟล์ .exe จากโดเมน github.com
- โหลดไฟล์ครบ เขียน .bat สลับไฟล์ถูก และไฟล์ไม่ครบต้องไม่ผ่าน

รัน: python3 test_update.py
"""
import http.server
import io
import json
import os
import socketserver
import sys
import tempfile
import threading
import types
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("AUTOSENDER_NO_UPDATE_CHECK", "1")
import main  # noqa: E402

PORT = 8786
STATE = {"release": {}, "exe": b"x" * 2_000_000, "zip": b""}


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


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
        elif self.path.endswith(".zip"):
            body = STATE["zip"]
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
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
check(got == ("V1.7.0", GH + "/V1.7.0/a.exe", None),
      "เวอร์ชันใหม่กว่าต้องเจอ ได้ %r" % (got,))

# มี extension.zip แนบมาด้วย ต้องคืน URL ของมันมาด้วย
release("V1.7.0", EXE + [{"name": "extension.zip",
                         "browser_download_url": GH + "/V1.7.0/extension.zip"}])
got = main.check_update()
check(got == ("V1.7.0", GH + "/V1.7.0/a.exe", GH + "/V1.7.0/extension.zip"),
      "ต้องคืน URL ของ extension.zip ด้วย ได้ %r" % (got,))
release("V1.7.0", EXE + [{"name": "extension.zip",
                         "browser_download_url": "https://evil.example.com/extension.zip"}])
check(main.check_update()[2] is None, "extension.zip นอก github.com ต้องไม่รับ")

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
bat = os.path.join(os.path.dirname(fake_exe), "autosender_update.bat")
check(os.path.exists(new_file), "ต้องมีไฟล์ .new")
check(os.path.getsize(new_file) == len(STATE["exe"]), "ไฟล์ .new ต้องครบ")
check(os.path.exists(bat), "ต้องเขียน .bat")
check(launched, "ต้องสั่งรัน .bat")
check(seen and seen[-1][0] == len(STATE["exe"]), "ต้องรายงานความคืบหน้าจนครบ")
body = open(bat, encoding="ascii").read()
check("move /y" in body and fake_exe in body, ".bat ต้องสลับไฟล์ตัวจริง")
check('start "" "%s"' % fake_exe in body, ".bat ต้องเปิดโปรแกรมกลับมา")
check("if %n% lss 30" in body, ".bat ต้องมีเพดานรอบ ไม่วนค้างตลอดกาล")

# --- โฟลเดอร์ชื่อไทย: เดิมพังทันที "ascii codec can't encode characters" ---
thai_dir = os.path.join(tmp, "โปรแกรมส่งข้อความ")
os.makedirs(thai_dir, exist_ok=True)
thai_exe = os.path.join(thai_dir, "main.exe")
open(thai_exe, "wb").write(b"old")
main.sys = types.SimpleNamespace(frozen=True, executable=thai_exe)
launched.clear()
main.download_and_restart(BASE + "/a.exe")
thai_bat = os.path.join(main.short_path(thai_dir), "autosender_update.bat")
check(os.path.exists(thai_bat), "path ไทยต้องเขียน .bat ได้ ไม่ใช่ throw")
check(os.path.exists(thai_exe + ".new"), "path ไทยต้องโหลดไฟล์ใหม่ได้")
check(launched, "path ไทยต้องสั่งรัน .bat")
raw = open(thai_bat, "rb").read()
check(b"move /y" in raw and b"start" in raw, ".bat ของ path ไทยต้องมีคำสั่งครบ")
os.remove(thai_bat)
os.remove(thai_exe + ".new")
main.sys = types.SimpleNamespace(frozen=True, executable=fake_exe)

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

# --- อัปเดตส่วนขยาย (โฟลเดอร์เดียว ทุกโปรไฟล์ได้หมด) ---
ext_dir = os.path.join(tmp, "extension")
os.makedirs(ext_dir)
open(os.path.join(ext_dir, "manifest.json"), "w").write('{"version":"1.0"}')
open(os.path.join(ext_dir, "content.js"), "w").write("old")

STATE["zip"] = make_zip({"manifest.json": '{"version":"1.7.0"}', "content.js": "new",
                         "popup/popup.js": "p"})
n = main.update_extension(BASE + "/extension.zip", ext_dir)
check(n == 3, "ต้องเขียน 3 ไฟล์ ได้ %r" % n)
check(open(os.path.join(ext_dir, "content.js")).read() == "new", "ต้องทับไฟล์เดิม")
check('"1.7.0"' in open(os.path.join(ext_dir, "manifest.json")).read(), "manifest ต้องเป็นตัวใหม่")
check(os.path.isfile(os.path.join(ext_dir, "popup", "popup.js")), "ต้องสร้างโฟลเดอร์ย่อยให้ด้วย")

# ซิปที่ห่อไว้ในโฟลเดอร์ชั้นเดียว ต้องปอกออก ไม่ใช่ลง extension/extension/
STATE["zip"] = make_zip({"extension/manifest.json": '{"version":"1.8.0"}',
                         "extension/content.js": "wrapped"})
main.update_extension(BASE + "/extension.zip", ext_dir)
check(open(os.path.join(ext_dir, "content.js")).read() == "wrapped", "ซิปที่ห่อโฟลเดอร์ต้องถูกปอก")
check(not os.path.exists(os.path.join(ext_dir, "extension")), "ต้องไม่เกิดโฟลเดอร์ซ้อน")

# ทุกไฟล์อยู่ใต้โฟลเดอร์เดียวแต่ปอกแล้วไม่เจอ manifest ที่ราก ต้องไม่ปอก (แล้วตกที่เช็ค manifest)
STATE["zip"] = make_zip({"popup/a.js": "x", "popup/b.js": "y"})
try:
    main.update_extension(BASE + "/extension.zip", ext_dir)
    sys.exit("FAIL: ซิปที่ไม่มี manifest.json ที่รากต้อง raise")
except RuntimeError as e:
    check("manifest" in str(e), "ควรบอกว่าไม่ใช่ไฟล์ส่วนขยาย ได้ %r" % str(e))

# เช็คเวอร์ชันหลังแตกไฟล์: ซิปที่เวอร์ชันไม่ตรง tag ต้องไม่นับว่าสำเร็จ
STATE["zip"] = make_zip({"manifest.json": '{"version":"1.6.1"}', "content.js": "z"})
try:
    main.update_extension(BASE + "/extension.zip", ext_dir, expect_version="V1.7.0")
    sys.exit("FAIL: manifest เวอร์ชันไม่ตรง tag ต้อง raise")
except RuntimeError as e:
    check("1.6.1" in str(e), "ควรบอกว่าเวอร์ชันที่ได้คืออะไร ได้ %r" % str(e))
STATE["zip"] = make_zip({"manifest.json": '{"version":"1.7.0"}', "content.js": "z"})
check(main.update_extension(BASE + "/extension.zip", ext_dir, expect_version="V1.7.0") == 2,
      "เวอร์ชันตรง tag ต้องผ่าน")

# ซิปที่พยายามเขียนไฟล์นอกโฟลเดอร์ต้องไม่ผ่าน
outside = os.path.join(tmp, "pwned.txt")
STATE["zip"] = make_zip({"manifest.json": "{}", "../pwned.txt": "bad"})
try:
    main.update_extension(BASE + "/extension.zip", ext_dir)
    sys.exit("FAIL: ซิปที่มี ../ ต้อง raise")
except RuntimeError:
    pass
check(not os.path.exists(outside), "ห้ามเขียนไฟล์นอกโฟลเดอร์ส่วนขยาย")

# ซิปที่ไม่ใช่ส่วนขยาย (ไม่มี manifest.json) ต้องไม่ผ่าน
STATE["zip"] = make_zip({"readme.txt": "hello"})
try:
    main.update_extension(BASE + "/extension.zip", ext_dir)
    sys.exit("FAIL: ซิปที่ไม่มี manifest.json ต้อง raise")
except RuntimeError:
    pass
check(not os.path.exists(os.path.join(ext_dir, "readme.txt")), "ต้องไม่เขียนอะไรเลยเมื่อซิปผิด")

# โฟลเดอร์ที่ไม่ใช่ส่วนขยาย ต้องไม่ยอมทับ
try:
    main.update_extension(BASE + "/extension.zip", tmp)
    sys.exit("FAIL: โฟลเดอร์ที่ไม่มี manifest.json ต้อง raise")
except RuntimeError:
    pass

# หาโฟลเดอร์ส่วนขยาย: ค่าที่จำไว้ใช้ได้ / ชี้ไปที่ที่ไม่ใช่ต้องตกไป
main.CONFIG_PATH = os.path.join(tmp, "cfg.json")
main.save_ext_dir(ext_dir)
check(main.find_ext_dir() == ext_dir, "ต้องอ่าน path ที่จำไว้")
main.save_ext_dir(os.path.join(tmp, "ไม่มีอยู่"))
check(main.find_ext_dir() is None or main.find_ext_dir() != os.path.join(tmp, "ไม่มีอยู่"),
      "path ที่ไม่มี manifest.json ต้องไม่ถูกใช้")

# --- ส่วนขยายบอกเวอร์ชันมาทาง /api/get-task ---
main.app.config.update(TESTING=True)
client = main.app.test_client()
client.get("/api/get-task/profile_1/uid_a?v=1.6.0")
client.get("/api/get-task/profile_1/uid_b?v=1.0")
check(main.ext_versions == {"uid_a": "1.6.0", "uid_b": "1.0"},
      "ต้องเก็บเวอร์ชันส่วนขยายรายโปรไฟล์ ได้ %r" % main.ext_versions)
client.get("/api/get-task/profile_2/uid_b?v=1.0")  # โปรไฟล์นี้ย้าย preset

tab = main.tab_chrome
tab.refresh_ext_status()
txt = tab.lbl_ext.cget("text")
check("1.0" in txt, "ต้องเตือนโปรไฟล์ที่ใช้ส่วนขยายเก่า ได้ %r" % txt)
check("profile_2" in txt, "ต้องบอกด้วยว่าโปรไฟล์ไหน ได้ %r" % txt)

# --- ทับส่วนขยายให้เองตอนเปิดโปรแกรม ไม่ต้องกดปุ่ม ---
main.save_ext_dir(ext_dir)
open(os.path.join(ext_dir, "manifest.json"), "w").write('{"version":"1.0"}')
open(os.path.join(ext_dir, "content.js"), "w").write("old")
STATE["zip"] = make_zip({"manifest.json": '{"version":"1.7.0"}', "content.js": "auto"})
tab._auto_update_extension("V1.7.0", BASE + "/extension.zip")
check(open(os.path.join(ext_dir, "content.js")).read() == "auto",
      "เปิดโปรแกรมแล้วต้องทับส่วนขยายให้เลย ไม่ต้องรอกดปุ่ม")
check(tab.ext_note == "", "สำเร็จแล้วต้องไม่มีข้อความเตือนค้าง ได้ %r" % tab.ext_note)

# ทับไปแล้วรอบก่อน ต้องไม่โหลดซ้ำ (ซิปพังก็ต้องไม่พัง เพราะไม่ควรแตะเลย)
STATE["zip"] = "ไม่ใช่ซิป".encode()
tab._auto_update_extension("V1.7.0", BASE + "/extension.zip")
check(open(os.path.join(ext_dir, "content.js")).read() == "auto", "เวอร์ชันตรงแล้วต้องข้าม")

# ซิปพังจริงตอนที่ต้องอัปเดต ต้องขึ้นเตือน ไม่ใช่เงียบ
open(os.path.join(ext_dir, "manifest.json"), "w").write('{"version":"1.0"}')
tab._auto_update_extension("V1.7.0", BASE + "/extension.zip")
check("ไม่สำเร็จ" in tab.ext_note, "อัปเดตอัตโนมัติพังต้องเก็บข้อความเตือน ได้ %r" % tab.ext_note)
saved, main.ext_versions = dict(main.ext_versions), {}   # ไม่มีโปรไฟล์เก่าบัง จะได้เห็นข้อความนี้
tab.refresh_ext_status()
check("ไม่สำเร็จ" in tab.lbl_ext.cget("text"),
      "อัปเดตอัตโนมัติพังต้องขึ้นบนหน้าจอ ได้ %r" % tab.lbl_ext.cget("text"))
main.ext_versions = saved
tab.ext_note = ""

# ส่วนขยายรุ่นก่อน 1.6.0 ไม่ส่ง v มาเลย ต้องยังจับได้ ไม่ใช่เงียบ
client.get("/api/get-task/profile_3/uid_c")
check(main.ext_versions.get("uid_c") == "0",
      "poll ที่ไม่มี v ต้องนับเป็นเวอร์ชันเก่าสุด ได้ %r" % main.ext_versions.get("uid_c"))
tab.refresh_ext_status()
txt = tab.lbl_ext.cget("text")
check("profile_3" in txt and "เก่ามาก" in txt, "ต้องเตือนตัวที่ไม่บอกเวอร์ชัน ได้ %r" % txt)
check("เก่ามาก" in tab.frame.winfo_toplevel().title(),
      "หัวหน้าต่างต้องบอกเวอร์ชันส่วนขยายด้วย ได้ %r" % tab.frame.winfo_toplevel().title())

main.ext_versions.pop("uid_b")
main.ext_versions.pop("uid_c")
tab.refresh_ext_status()
check("✅" in tab.lbl_ext.cget("text"), "ทุกโปรไฟล์ล่าสุดแล้วต้องไม่เตือน")
check("1.6.0" in tab.frame.winfo_toplevel().title(),
      "หัวหน้าต่างต้องขึ้นเวอร์ชันส่วนขยายที่ล่าสุดแล้ว ได้ %r" % tab.frame.winfo_toplevel().title())

srv.shutdown()
print("OK: เช็คเวอร์ชัน โหลดไฟล์ สคริปต์สลับไฟล์ อัปเดตส่วนขยาย และเตือนโปรไฟล์ที่ตกรุ่น ทำงานถูก")
