"""เทสว่าโค้ดหากล่องพิมพ์ของ content.js หาเจอโดยไม่ต้องให้คนคลิกก่อน

จากวิดีโอผู้ใช้: แท็บ Messenger เป็นแท็บที่เลือกอยู่ หน้าต่างเห็นเต็ม ๆ หน้าโหลดเสร็จแล้ว
แต่ไม่ส่ง จนกระทั่งเอาเมาส์คลิกในกล่องพิมพ์ = ผ่านทาง document.activeElement (บรรทัด 307)
ซึ่งข้ามตัวกรองด้านล่างทั้งหมด แปลว่าตัวกรองหากล่องไม่เจอ

เทสจำลองหน้า /messages/t/... 3 แบบ ที่ตัวกรองเดิมพลาด แล้วเช็คว่าเลือกกล่องแชทถูกตัว
โดยไม่มีการคลิกใด ๆ เลย

รัน: python3 test_find_input.py   (ใช้ Chrome ในเครื่อง)
"""
import http.server
import json
import re
import socketserver
import subprocess
import sys
import threading
import time
import os

PORT = 8783
RESULTS = []
HERE = os.path.dirname(os.path.abspath(__file__))

# ดึงฟังก์ชันจริงจาก content.js มาเทส ไม่ก๊อปโค้ดมาวางซ้ำ (ไม่งั้นเทสไม่ได้เทสของจริง)
SRC = open(os.path.join(HERE, "content.js"), encoding="utf-8").read()
m = re.search(r"^function findInputEl\(.*?^\}", SRC, re.S | re.M)
if not m:
    sys.exit("FAIL: หา function findInputEl ใน content.js ไม่เจอ "
             "(ต้องแยกโค้ดหากล่องออกมาเป็นฟังก์ชันชื่อนี้ก่อน)")
FIND_INPUT_SRC = m.group(0)

# 3 หน้าจำลอง: กล่องแชทที่ตัวกรองเดิมพลาด + กล่องหลอกที่ต้องไม่โดนเลือก
CASES = {
    # aria-label ไม่ตรงลิสต์ที่ hardcode ไว้ (เทียบเท่าของจริงที่เป็น "เขียนข้อความ" ฯลฯ)
    "label_mismatch": '''
      <div role="textbox" contenteditable="true" aria-label="ค้นหา Messenger" id="decoy_search"></div>
      <div role="textbox" contenteditable="true" aria-label="เขียนข้อความ" id="composer"></div>''',
    # ไม่มี aria-label เลย มีแค่ aria-placeholder (กรณีแย่สุด)
    "no_label": '''
      <div role="textbox" contenteditable="true" aria-label="ค้นหา" id="decoy_search"></div>
      <div role="textbox" contenteditable="true" aria-placeholder="Aa" id="composer"></div>''',
    # ไม่ใช่ div[role=textbox] (Facebook เปลี่ยนโครงสร้างเมื่อไหร่ก็เจอ)
    "not_div_textbox": '''
      <div role="textbox" contenteditable="true" aria-label="ค้นหา" id="decoy_search"></div>
      <p contenteditable="true" aria-placeholder="Aa" id="composer"></p>''',
    # เคสที่เคยทำงานอยู่แล้ว ต้องไม่พัง
    "label_message": '''
      <div role="textbox" contenteditable="true" aria-label="ค้นหา" id="decoy_search"></div>
      <div role="textbox" contenteditable="true" aria-label="Message" id="composer"></div>''',
    # ห้ามไปโดนกล่องคอมเมนต์ ทั้งที่กล่องคอมเมนต์อยู่ล่างกว่าในหน้า
    "comment_box_below": '''
      <div role="textbox" contenteditable="true" aria-label="ข้อความ" id="composer"
           style="position:absolute;top:100px;width:300px;height:30px"></div>
      <div role="textbox" contenteditable="true" aria-label="เขียนความคิดเห็น"
           id="decoy_comment" style="position:absolute;top:500px;width:300px;height:30px"></div>''',
    # ป้ายจริงของกล่องแชทหน้าเพจ (ดู DOM จริงบน facebook.com/<เพจ>)
    # กล่องล่อไม่มีป้ายและอยู่ต่ำกว่า = ถ้าไม่รู้จักป้าย "write to" จะตกไปเดาตำแหน่งแล้วโดนตัวล่อ
    "page_chat_write_to": '''
      <div role="textbox" contenteditable="true" aria-label="Write to แปลมังงะ by Imtheone"
           id="composer" style="position:absolute;top:100px;width:300px;height:30px"></div>
      <div contenteditable="true" id="decoy_unlabeled"
           style="position:absolute;top:500px;width:300px;height:30px"></div>''',
    "page_chat_write_to_th": '''
      <div role="textbox" contenteditable="true" aria-label="เขียนถึง ร้านค้าตัวอย่าง"
           id="composer" style="position:absolute;top:100px;width:300px;height:30px"></div>
      <div contenteditable="true" id="decoy_unlabeled"
           style="position:absolute;top:500px;width:300px;height:30px"></div>''',
    # ไม่มีชื่อให้จับเลย + มีกล่องคอมเมนต์อยู่ล่างกว่า ต้องไม่ตกไปโดนกล่องคอมเมนต์
    "unlabeled_with_comment_below": '''
      <div contenteditable="true" id="composer"
           style="position:absolute;top:100px;width:300px;height:30px"></div>
      <div contenteditable="true" aria-label="แสดงความคิดเห็น" id="decoy_comment"
           style="position:absolute;top:500px;width:300px;height:30px"></div>''',
}

PAGE = """<!doctype html><meta charset=utf-8><title>find input probe</title>
<body style="font-family:sans-serif">
<div id="stage"></div>
<script>
FIND_INPUT_SRC_

const CASES = CASES_JSON_;
const out = {};
for (const [name, html] of Object.entries(CASES)) {
  const stage = document.getElementById('stage');
  stage.innerHTML = html;
  // ไม่คลิกอะไรเลย = สภาพเดียวกับตอนบอทสั่งเองแล้วไม่มีคนแตะจอ
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  let el = null, err = null;
  try { el = findInputEl("messenger", false); } catch (e) { err = String(e); }
  out[name] = { picked: el ? el.id : null, error: err,
                activeWas: document.activeElement ? document.activeElement.tagName : null };
}
fetch('http://127.0.0.1:PORT_/result', {method:'POST', body: JSON.stringify(out)});
</script>
</body>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = (PAGE.replace("FIND_INPUT_SRC_", FIND_INPUT_SRC)
                    .replace("CASES_JSON_", json.dumps(CASES))
                    .replace("PORT_", str(PORT)))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        RESULTS.append(json.loads(self.rfile.read(n) or b"{}"))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


def chrome_path():
    for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(p):
            return p
    sys.exit("ไม่พบ Chrome")


def main():
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    p = subprocess.Popen([chrome_path(), "--user-data-dir=/tmp/findinputprobe",
                          "--no-first-run", "--headless=new",
                          f"http://127.0.0.1:{PORT}/"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 30
    while time.time() < deadline and not RESULTS:
        time.sleep(0.3)
    p.terminate()
    srv.shutdown()

    if not RESULTS:
        sys.exit("FAIL: หน้าเทสไม่ตอบกลับ")
    res = RESULTS[0]
    print(json.dumps(res, ensure_ascii=False, indent=1))
    bad = [k for k, v in res.items() if v.get("picked") != "composer"]
    if bad:
        sys.exit(f"FAIL: เลือกกล่องผิด/หาไม่เจอ ในกรณี {bad}")
    print("OK: หากล่องแชทเจอทุกกรณีโดยไม่ต้องคลิก")


if __name__ == "__main__":
    main()
