"""พิสูจน์ว่า document.execCommand('insertText') ต้องมี "การคลิกจริงของคน" ก่อนหรือไม่

จากวิดีโอ: แท็บ Messenger เป็นแท็บที่เลือกอยู่ หน้าต่างเห็นเต็ม ๆ แต่ยังไม่ส่ง
จนกระทั่งเอาเมาส์ไปคลิกในกล่องพิมพ์ = ไม่ใช่เรื่อง throttling

สมมติฐานที่ทดสอบ: `el.focus()` จากสคริปต์ ไม่พอสำหรับ execCommand ถ้าเอกสารนั้น
ยังไม่เคยได้รับ user gesture / หน้าต่างไม่ใช่หน้าต่างที่ระบบโฟกัสอยู่

รันบน Mac: python3 probe_focus.py
"""
import http.server
import json
import socketserver
import subprocess
import sys
import threading
import time

PORT = 8781
RESULTS = []

PAGE = r"""<!doctype html><meta charset=utf-8><title>focus probe</title>
<body style="font-family:sans-serif">
<h3>focus probe</h3>
<div id="box" role="textbox" contenteditable="true" aria-label="Message"
     style="border:1px solid #888;min-height:40px;width:400px"></div>
<script>
function attempt(tag) {
  const el = document.getElementById('box');
  el.innerHTML = '';
  const r = { tag, hasFocus: document.hasFocus(), hidden: document.hidden };

  el.focus(); el.click();
  r.activeIsBox = (document.activeElement === el);

  // ทางที่ 1: synthetic paste
  const dt = new DataTransfer();
  dt.setData('text/plain', 'PASTE');
  el.dispatchEvent(new ClipboardEvent('paste',
      {bubbles:true, cancelable:true, clipboardData:dt}));
  r.afterPaste = el.innerText;

  // ทางที่ 2: execCommand
  if (el.innerText.trim() === '') {
    r.execReturn = document.execCommand('insertText', false, 'EXEC');
    r.afterExec = el.innerText;
  } else { r.afterExec = '(skipped)'; r.execReturn = null; }

  // ทางที่ 3: เขียน textContent ตรง ๆ (ไม่พึ่ง gesture เลย)
  if (el.innerText.trim() === '') {
    el.textContent = 'DIRECT';
    el.dispatchEvent(new InputEvent('input', {bubbles:true, data:'DIRECT',
                                              inputType:'insertText'}));
    r.afterDirect = el.innerText;
  } else { r.afterDirect = '(skipped)'; }

  return r;
}

// รอบที่ 1: ยังไม่มีใครคลิกอะไรเลย (สภาพเดียวกับตอนบอทสั่งเอง)
const out = [attempt('no_user_gesture')];

// รอบที่ 2: หลังคนคลิกจริง 1 ครั้ง
document.addEventListener('click', function once(e) {
  if (e.isTrusted !== true) return;
  document.removeEventListener('click', once);
  out.push(attempt('after_real_click'));
  fetch('http://127.0.0.1:PORT_/result', {method:'POST', body: JSON.stringify(out)});
}, true);

// ถ้าไม่มีใครคลิกใน 12 วิ ส่งเฉพาะรอบแรก
setTimeout(() => {
  fetch('http://127.0.0.1:PORT_/result', {method:'POST', body: JSON.stringify(out)});
}, 12000);
</script>
</body>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE.replace("PORT_", str(PORT)).encode())

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        RESULTS.append(json.loads(self.rfile.read(n) or b"{}"))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def main():
    srv = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    srv.allow_reuse_address = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    p = subprocess.Popen([CHROME, "--user-data-dir=/tmp/focusprobe", "--no-first-run",
                          "--new-window", f"http://127.0.0.1:{PORT}/"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 25
    while time.time() < deadline and not RESULTS:
        time.sleep(0.5)
    p.terminate()
    srv.shutdown()
    print(json.dumps(RESULTS, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
