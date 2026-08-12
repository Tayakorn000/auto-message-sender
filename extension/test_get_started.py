"""เทสว่าบอทยังกดปุ่ม "เริ่มต้นใช้งาน" เองก่อนพิมพ์ ถึงแม้จะหากล่องพิมพ์เจอตั้งแต่รอบแรก

โค้ดหากล่องตัวใหม่เจอเร็วกว่าเดิมมาก ถ้าไม่รอ ปุ่ม "เริ่มต้นใช้งาน" ที่ยัง render ไม่เสร็จ
จะไม่ถูกกด แล้วพิมพ์ลงกล่องที่ยังใช้งานไม่ได้ = ส่งไม่ออก

ดึง forceSend + findInputEl ตัวจริงจาก content.js มารัน (ไม่ก๊อปโค้ดมาวางซ้ำ)
รัน: python3 test_get_started.py
"""
import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
import threading
import time

PORT = 8784
RESULTS = []
HERE = os.path.dirname(os.path.abspath(__file__))

SRC = open(os.path.join(HERE, "content.js"), encoding="utf-8").read()
FUNCS = []
for pat in (r"^let gsSettled = false;$", r"^const norm = .*?;$",
            r"^const isVisible = .*?;$",
            r"^const GS_LABELS = \[[\s\S]*?\];$"):
    m = re.search(pat, SRC, re.M)
    if not m:
        sys.exit("FAIL: หาโค้ดใน content.js ไม่เจอ -> %s" % pat)
    FUNCS.append(m.group(0))
for name in ("findGsBtns", "findInputEl", "whyNoInput", "forceSend"):
    m = re.search(r"^function %s\(.*?^\}" % name, SRC, re.S | re.M)
    if not m:
        sys.exit("FAIL: หา function %s ใน content.js ไม่เจอ" % name)
    FUNCS.append(m.group(0))
CODE = "\n\n".join(FUNCS)

PAGE = """<!doctype html><meta charset=utf-8><title>get started probe</title>
<body style="font-family:sans-serif">
<div id="stage"></div>
<script>
CODE_

const order = [];
// stub: แทนการพิมพ์จริง แค่บันทึกว่าถูกเรียกตอนไหน
function executeSendSteps(inputEl, text, resolve, mode) {
  order.push("type:" + (inputEl.id || inputEl.tagName));
  resolve();
}

const COMPOSER = '<div role="textbox" contenteditable="true" aria-label="ข้อความ" ' +
                 'id="composer" style="width:300px;height:30px"></div>';

function btn(label, text, id) {
  const b = document.createElement('div');
  b.setAttribute('role', 'button');
  if (label !== null) b.setAttribute('aria-label', label);
  b.id = id;
  b.innerText = text;
  b.style.cssText = 'width:200px;height:30px';
  b.addEventListener('click', () => order.push('click:' + id));
  return b;
}

function addGetStarted() {
  const b = document.createElement('div');
  b.setAttribute('role', 'button');
  b.id = 'gs';
  b.style.cssText = 'width:120px;height:30px';
  b.innerText = 'เริ่มต้นใช้งาน';
  b.addEventListener('click', () => order.push('click:gs'));
  document.getElementById('stage').appendChild(b);
}

// แบบที่ Facebook ใช้จริงบ่อยกว่า: span[role=button] ข้อความซ้อนใน span ลูก + มี NBSP
function addGetStartedSpan() {
  const b = document.createElement('span');
  b.setAttribute('role', 'button');
  b.setAttribute('aria-label', 'เริ่มต้นใช้งาน');
  b.id = 'gs';
  b.style.cssText = 'display:inline-block;width:120px;height:30px';
  b.innerHTML = '<span dir="auto">\\u00a0เริ่มต้นใช้งาน </span>';
  b.addEventListener('click', () => order.push('click:gs'));
  document.getElementById('stage').appendChild(b);
}

// เปิดหน้าใหม่ = เริ่มนับปุ่มใหม่ (gsSettled อยู่ระดับ module จริง ๆ ค้างข้ามการส่ง)
function freshPage(html) {
  gsSettled = false;
  order.length = 0;
  document.getElementById('stage').innerHTML = html || '';
}

async function run() {
  const out = {};
  const stage = document.getElementById('stage');

  // เคส 1: กล่องพิมพ์มีตั้งแต่แรก ปุ่มเพิ่งโผล่ตอน 100 ms ต้องกดปุ่มก่อนพิมพ์
  freshPage(COMPOSER);
  setTimeout(addGetStarted, 100);
  let t0 = performance.now();
  await forceSend('hi', 'messenger', false);
  out.late_button = { order: order.slice(), ms: Math.round(performance.now() - t0) };

  // เคส 2: หน้าโหลดช้า กล่องพิมพ์เพิ่งมา 500 ms ปุ่มตาม 600 ms
  // (เคสนี้พังถ้าไปใช้ retryCount ร่วมกับลูปหากล่อง เพราะโควตาถูกใช้หมดก่อน)
  freshPage('');
  setTimeout(() => { stage.innerHTML = COMPOSER; }, 500);
  setTimeout(addGetStarted, 600);
  t0 = performance.now();
  await forceSend('hi', 'messenger', false);
  out.slow_page = { order: order.slice(), ms: Math.round(performance.now() - t0) };

  // เคส 3: ปุ่มเป็น span[role=button] ข้อความซ้อนใน span ลูก + NBSP (แบบที่ Facebook ใช้จริง)
  freshPage(COMPOSER);
  setTimeout(addGetStartedSpan, 100);
  t0 = performance.now();
  await forceSend('hi', 'messenger', false);
  out.span_button = { order: order.slice(), ms: Math.round(performance.now() - t0) };

  // เคส 4: ไม่มีปุ่มเลย ต้องพิมพ์ได้ ไม่ค้าง
  freshPage(COMPOSER);
  t0 = performance.now();
  await forceSend('hi', 'messenger', false);
  out.no_button = { order: order.slice(), ms: Math.round(performance.now() - t0) };

  // เคส 5: ส่งซ้ำในหน้าเดิมที่รู้แล้วว่าไม่มีปุ่ม ต้องไม่รอซ้ำ (ส่ง 1000 ครั้งจะได้ไม่ช้า)
  order.length = 0;   // ไม่ freshPage เพราะจงใจให้ gsSettled ค้างจากเคส 3
  t0 = performance.now();
  await forceSend('hi', 'messenger', false);
  out.repeat_send = { order: order.slice(), ms: Math.round(performance.now() - t0) };

  // ★ เคสจริงของลูกค้า: แชทที่ยังไม่เคยคุยกับเพจ = ไม่มีกล่องพิมพ์เลยจนกว่าจะกดปุ่ม
  freshPage('');
  const gsOnly = document.createElement('div');
  gsOnly.setAttribute('role', 'button');
  gsOnly.id = 'gs';
  gsOnly.style.cssText = 'width:120px;height:30px';
  gsOnly.innerHTML = '<span dir="auto">\u0e40\u0e23\u0e34\u0e48\u0e21\u0e15\u0e49\u0e19' +
                     '\u0e43\u0e0a\u0e49\u0e07\u0e32\u0e19 !</span>';
  gsOnly.addEventListener('click', () => {
    order.push('click:gs');
    setTimeout(() => { document.getElementById('stage').innerHTML += COMPOSER; }, 300);
  });
  document.getElementById('stage').appendChild(gsOnly);
  t0 = performance.now();
  await forceSend('hi', 'messenger', false);
  out.no_composer_until_click = { order: order.slice(), ms: Math.round(performance.now() - t0) };

  // ปุ่มหลอกที่ข้อความยาว ต้องไม่โดนกด และปุ่มจริงที่ป้ายเป็น aria-label ต้องโดน
  freshPage('');
  const decoy = btn(null, '\u0e40\u0e23\u0e34\u0e48\u0e21\u0e15\u0e49\u0e19' +
    '\u0e43\u0e0a\u0e49\u0e07\u0e32\u0e19\u0e01\u0e31\u0e1a\u0e42\u0e1b\u0e23\u0e41\u0e01\u0e23' +
    '\u0e19\u0e35\u0e49\u0e44\u0e14\u0e49\u0e07\u0e48\u0e32\u0e22 \u0e46 \u0e40\u0e1e\u0e35\u0e22' +
    '\u0e07\u0e01\u0e14\u0e1b\u0e38\u0e48\u0e21\u0e40\u0e14\u0e35\u0e22\u0e27', 'decoy_long');
  const real = document.createElement('div');
  real.setAttribute('role', 'button');
  real.setAttribute('aria-label', '\u0e40\u0e23\u0e34\u0e48\u0e21\u0e15\u0e49\u0e19' +
                                  '\u0e43\u0e0a\u0e49\u0e07\u0e32\u0e19');
  real.id = 'real_gs';
  real.style.cssText = 'width:120px;height:30px';
  real.addEventListener('click', () => {
    order.push('click:real_gs');
    setTimeout(() => { document.getElementById('stage').innerHTML += COMPOSER; }, 200);
  });
  document.getElementById('stage').appendChild(decoy);
  document.getElementById('stage').appendChild(real);
  await forceSend('hi', 'messenger', false);
  out.aria_only_button = { order: order.slice() };

  // หน้าที่ไม่มีกล่องพิมพ์เลย: ข้อความ error ต้องบอกสภาพหน้าจริง ไม่ใช่ประโยคลอย ๆ
  freshPage('<div role="button" aria-label="\u0e40\u0e23\u0e34\u0e48\u0e21\u0e15\u0e49\u0e19' +
            '\u0e43\u0e0a\u0e49\u0e07\u0e32\u0e19" style="width:99px;height:9px">x</div>');
  out.diag = whyNoInput();

  fetch('http://127.0.0.1:PORT_/result', {method:'POST', body: JSON.stringify(out)});
}
run();
</script>
</body>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGE.replace("CODE_", CODE).replace("PORT_", str(PORT))
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
    p = subprocess.Popen([chrome_path(), "--user-data-dir=/tmp/getstartedprobe",
                          "--no-first-run", "--headless=new",
                          "http://127.0.0.1:%d/" % PORT],
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

    # เคส 1-2 ไม่ได้บอกว่าเป็นลิงก์เพจเลย ต้องกดปุ่มให้เอง (ลูกค้าลืมติ๊กช่องก็ต้องทำงาน)
    for case in ("late_button", "slow_page", "span_button"):
        if res[case]["order"] != ["click:gs", "type:composer"]:
            sys.exit("FAIL: %s ไม่ได้กดปุ่มก่อนพิมพ์ -> %s" % (case, res[case]["order"]))
    if res["no_composer_until_click"]["order"] != ["click:gs", "type:composer"]:
        sys.exit("FAIL: แชทที่ยังไม่มีกล่องพิมพ์ ต้องกดปุ่มแล้วพิมพ์ได้ -> %s"
                 % res["no_composer_until_click"]["order"])
    if res["aria_only_button"]["order"] != ["click:real_gs", "type:composer"]:
        sys.exit("FAIL: ต้องกดปุ่มจริง (aria-label) ไม่ใช่ปุ่มหลอกข้อความยาว -> %s"
                 % res["aria_only_button"]["order"])
    for case in ("no_button", "repeat_send"):
        if res[case]["order"] != ["type:composer"]:
            sys.exit("FAIL: %s พิมพ์ไม่ได้ -> %s" % (case, res[case]["order"]))
    if res["no_button"]["ms"] > 1500:
        sys.exit("FAIL: ไม่มีปุ่ม แต่รอนานเกินไป %d ms" % res["no_button"]["ms"])
    if res["repeat_send"]["ms"] > 100:
        sys.exit("FAIL: ส่งซ้ำยังเสียเวลารอปุ่มอีก %d ms" % res["repeat_send"]["ms"])
    d = res["diag"]
    for want in ("กล่องพิมพ์ 0/0", "ปุ่มเริ่มต้นใช้งาน 1", "หน้า complete"):
        if want not in d:
            sys.exit("FAIL: ข้อความตอนหาไม่เจอควรมี %r -> %s" % (want, d))
    print("OK: กดปุ่มเริ่มต้นใช้งานก่อนพิมพ์เสมอ (ไม่ต้องพึ่งการติ๊กช่องลิงก์เพจ) "
          "ไม่ค้างเมื่อไม่มีปุ่ม และส่งซ้ำไม่เสียเวลารอ")


if __name__ == "__main__":
    main()
