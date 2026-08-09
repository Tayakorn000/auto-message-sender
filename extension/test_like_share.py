"""เทสปุ่มไลค์/แชร์ ดึงโค้ดตัวจริงจาก content.js มารันใน headless Chrome ไม่มีการคลิกของคนเลย

เช็ค 3 อย่าง:
- กดถูกปุ่ม (ไม่ไปโดน "แชร์แล้ว 12 ครั้ง" / ปุ่มคอมเมนต์)
- โพสต์ที่ไลค์ไว้แล้ว ต้องไม่กดซ้ำ (กดซ้ำ = เอาไลค์ออก)
- แชร์ครบ flow ทั้งแบบ "แชร์ตอนนี้" (จบเลย) และแบบเปิดกล่องแล้วต้องกดโพสต์อีกที

รัน: python3 test_like_share.py
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

PORT = 8785
RESULTS = []
HERE = os.path.dirname(os.path.abspath(__file__))

SRC = open(os.path.join(HERE, "content.js"), encoding="utf-8").read()

# ดึงของจริงมาเทส ไม่ก๊อปโค้ดมาวางซ้ำ
PARTS = []
for pat in (r"^const isVisible = .*?;$", r"^const norm = .*?;$",
            r"^const ariaOf = .*?;$", r"^const textOf = .*?;$",
            r"^function waitFor\(.*?^\}", r"^function postScope\(.*?^\}",
            r"^function postButtons\(.*?^\}", r"^const LIKE_LABELS = .*?;$",
            r"^const UNLIKE_LABELS = .*?;$", r"^function findLikeBtn\(.*?^\}",
            r"^async function clickLike\(.*?^\}", r"^const SHARE_EXACT = .*?;$",
            r"^const SHARE_ARIA_PART = .*?;$", r"^const SHARE_NOW = .*?;$",
            r"^const POST_BTN = .*?;$", r"^async function clickShare\(.*?^\}"):
    m = re.search(pat, SRC, re.S | re.M)
    if not m:
        sys.exit("FAIL: หาโค้ดไม่เจอใน content.js -> %s" % pat)
    PARTS.append(m.group(0))
CODE = "\n".join(PARTS)

PAGE = """<!doctype html><meta charset=utf-8><title>like/share probe</title>
<body style="font-family:sans-serif">
<div id="stage"></div>
<script>
CODE_

const clicked = [];
function btn(label, text, id, extra) {
  const b = document.createElement('div');
  b.setAttribute('role', 'button');
  if (label !== null) b.setAttribute('aria-label', label);
  if (extra) for (const k in extra) b.setAttribute(k, extra[k]);
  b.id = id;
  b.innerText = text;
  b.style.cssText = 'width:120px;height:30px';
  b.addEventListener('click', () => clicked.push(id));
  return b;
}
function stage(...els) {
  const s = document.getElementById('stage');
  s.innerHTML = '';
  els.forEach(e => s.appendChild(e));
  clicked.length = 0;
}

async function run() {
  const out = {};

  // ยังไม่ไลค์ + มีปุ่มหลอกที่ข้อความมีคำว่า "ถูกใจ" อยู่ด้วย
  stage(btn('ถูกใจ 24 คน', 'ถูกใจ 24 คน', 'decoy_count'),
        btn('ถูกใจ', 'ถูกใจ', 'like'),
        btn('แสดงความคิดเห็น', 'แสดงความคิดเห็น', 'comment'));
  // หลังกดไลค์ ปุ่มต้องเปลี่ยนสถานะ ไม่งั้น clickLike ถือว่าไม่สำเร็จ
  document.getElementById('like').addEventListener('click', function () {
    this.setAttribute('aria-label', 'เอาการถูกใจออก');
  });
  out.like_fresh = { ok: await clickLike(), clicked: clicked.slice() };

  // ไลค์ไว้แล้ว ห้ามกดซ้ำ
  stage(btn('เอาการถูกใจออก', 'ถูกใจ', 'already'));
  out.like_already = { ok: await clickLike(), clicked: clicked.slice() };

  // aria-pressed=true = ไลค์ไว้แล้วอีกแบบ
  stage(btn('ถูกใจ', 'ถูกใจ', 'pressed', {'aria-pressed': 'true'}));
  out.like_pressed = { ok: await clickLike(), clicked: clicked.slice() };

  // ไม่มีปุ่มไลค์เลย ต้องคืน false ไม่ค้าง (timeout 8 วิ)
  stage(btn('แสดงความคิดเห็น', 'แสดงความคิดเห็น', 'only_comment'));
  let t0 = performance.now();
  out.like_missing = { ok: await clickLike(), clicked: clicked.slice(),
                       ms: Math.round(performance.now() - t0) };

  // แชร์แบบ "แชร์ตอนนี้" จบใน 2 คลิก + ปุ่มหลอก "แชร์แล้ว 12 ครั้ง"
  stage(btn('แชร์แล้ว 12 ครั้ง', 'แชร์แล้ว 12 ครั้ง', 'decoy_share'),
        btn('แชร์', 'แชร์', 'share'));
  document.getElementById('share').addEventListener('click', () => {
    document.getElementById('stage').appendChild(btn('แชร์ตอนนี้', 'แชร์ตอนนี้', 'share_now'));
  });
  out.share_now = { ok: await clickShare(), clicked: clicked.slice() };

  // แชร์แบบเปิดกล่องเขียนโพสต์ ต้องกดปุ่มโพสต์ในกล่องอีกที
  stage(btn('แชร์', 'แชร์', 'share2'));
  document.getElementById('share2').addEventListener('click', () => {
    document.getElementById('stage').appendChild(btn('แชร์ไปยังฟีด', 'แชร์ไปยังฟีด', 'to_feed'));
  });
  const later = () => {
    const d = document.createElement('div');
    d.setAttribute('role', 'dialog');
    d.appendChild(btn('โพสต์', 'โพสต์', 'post_btn'));
    document.getElementById('stage').appendChild(d);
  };
  document.addEventListener('click', e => { if (e.target.id === 'to_feed') setTimeout(later, 200); }, true);
  out.share_dialog = { ok: await clickShare(), clicked: clicked.slice() };

  // ไม่มีปุ่มแชร์ ต้องคืน false ไม่ค้าง
  stage(btn('ถูกใจ', 'ถูกใจ', 'no_share'));
  t0 = performance.now();
  out.share_missing = { ok: await clickShare(), clicked: clicked.slice(),
                        ms: Math.round(performance.now() - t0) };

  // Facebook แทรก NBSP คั่นคำแทนช่องว่างธรรมดา (เจอมาแล้วกับปุ่ม "เริ่มต้นใช้งาน")
  // ภาษาอังกฤษเจอชัดสุดเพราะป้ายมีเว้นวรรค — "Remove Like" ที่พลาดจะกลายเป็นกดไลค์ออก
  stage(btn('Remove\\u00a0Like', 'Like', 'already_nbsp'));
  out.like_already_nbsp = { ok: await clickLike(), clicked: clicked.slice() };

  stage(btn('Share', 'Share', 'share_en'));
  document.getElementById('share_en').addEventListener('click', () => {
    document.getElementById('stage').appendChild(
      btn('Share\\u00a0now', 'Share\\u00a0now', 'now_nbsp'));
  });
  out.share_nbsp = { ok: await clickShare(), clicked: clicked.slice() };

  // หน้าจริง: มีปุ่มถูกใจของ "เพจ" อยู่นอกโพสต์ + ปุ่มถูกใจของ "คอมเมนต์" อยู่ในโพสต์
  // ต้องกดของโพสต์อย่างเดียว
  const art = document.createElement('div');
  art.setAttribute('role', 'article');
  art.style.cssText = 'width:400px;height:200px';
  art.appendChild(btn('ถูกใจ', 'ถูกใจ', 'post_like'));
  art.appendChild(btn('แชร์', 'แชร์', 'post_share'));
  const cmt = document.createElement('div');   // คอมเมนต์ = article ซ้อนอีกชั้น
  cmt.setAttribute('role', 'article');
  cmt.style.cssText = 'width:300px;height:50px';
  cmt.appendChild(btn('ถูกใจ', 'ถูกใจ', 'comment_like'));
  art.appendChild(cmt);
  stage(btn('ถูกใจ', 'ถูกใจ', 'page_like'), art);   // page_like อยู่นอก article
  document.getElementById('post_like').addEventListener('click', function () {
    this.setAttribute('aria-label', 'เอาการถูกใจออก');
  });
  out.like_scoped = { ok: await clickLike(), clicked: clicked.slice() };

  stage(btn('แชร์', 'แชร์', 'page_share'), art);
  document.getElementById('post_share').addEventListener('click', () => {
    art.appendChild(btn('แชร์ตอนนี้', 'แชร์ตอนนี้', 'scoped_now'));
  });
  out.share_scoped = { ok: await clickShare(), clicked: clicked.slice() };

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


EXPECT = {
    "like_fresh": (True, ["like"]),
    "like_already": (True, []),
    "like_pressed": (True, []),
    "like_missing": (False, []),
    "share_now": (True, ["share", "share_now"]),
    "share_dialog": (True, ["share2", "to_feed", "post_btn"]),
    "share_missing": (False, []),
    "like_already_nbsp": (True, []),           # NBSP ใน "Remove Like" ห้ามทำให้กดไลค์ออก
    "share_nbsp": (True, ["share_en", "now_nbsp"]),
    "like_scoped": (True, ["post_like"]),      # ไม่ใช่ page_like / comment_like
    "share_scoped": (True, ["post_share", "scoped_now"]),
}


def main():
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    p = subprocess.Popen([chrome_path(), "--user-data-dir=/tmp/likeshareprobe",
                          "--no-first-run", "--headless=new",
                          "http://127.0.0.1:%d/" % PORT],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 90
    while time.time() < deadline and not RESULTS:
        time.sleep(0.3)
    p.terminate()
    srv.shutdown()

    if not RESULTS:
        sys.exit("FAIL: หน้าเทสไม่ตอบกลับ")
    res = RESULTS[0]
    print(json.dumps(res, ensure_ascii=False, indent=1))

    for case, (want_ok, want_clicks) in EXPECT.items():
        got = res.get(case)
        if got is None:
            sys.exit("FAIL: ไม่มีผลของ %s" % case)
        if got["ok"] != want_ok:
            sys.exit("FAIL: %s ok=%s ควรเป็น %s" % (case, got["ok"], want_ok))
        if got["clicked"] != want_clicks:
            sys.exit("FAIL: %s กดปุ่ม %s ควรเป็น %s" % (case, got["clicked"], want_clicks))
    print("OK: ไลค์/แชร์กดถูกปุ่ม ไม่กดซ้ำโพสต์ที่ไลค์แล้ว และไม่ค้างเมื่อไม่มีปุ่ม")


if __name__ == "__main__":
    main()
