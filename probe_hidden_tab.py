"""พิสูจน์ว่าโค้ดพิมพ์ข้อความของบอททำงานได้จริงตอนหน้าต่าง Chrome ถูกบัง/ไม่มีโฟกัส

รันบนเครื่อง Windows:
    python probe_hidden_tab.py            # ใส่แฟล็กปิดการหน่วง (แบบที่โปรแกรมใช้จริง)
    python probe_hidden_tab.py --no-flags # ไม่ใส่แฟล็ก เอาไว้เทียบ

หน้าเว็บทดสอบทำเองในตัว ไม่ต้องใช้ส่วนขยาย (Chrome รุ่นใหม่บล็อก --load-extension)
DOM/execCommand/timer ที่ content script เห็น = อันเดียวกับที่หน้าเว็บเห็น

ลำดับ: เปิดหน้าต่างเป้าหมาย -> 3 วิ เปิดหน้าต่างอื่นทับเต็มจอ -> วินาทีที่ 8
หน้าเป้าหมาย (ตอนนี้ถูกบังและไม่มีโฟกัส) รันโค้ดพิมพ์แบบเดียวกับ executeSendSteps
แล้ว POST ผลกลับมา
"""
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time

PORT = 8777
RESULTS = []

PAGE = r"""<!doctype html><meta charset=utf-8><title>probe</title>
<body style="font-family:sans-serif">
<h3>probe target</h3>
<div id="box" role="textbox" contenteditable="true" aria-label="Message"
     style="border:1px solid #888;min-height:40px;width:400px"></div>
<script>
// รอให้หน้าต่างอื่นมาบังก่อน แล้วค่อยทดสอบ
setTimeout(() => {
  const el = document.getElementById('box');
  const out = { hidden: document.hidden, hasFocus: document.hasFocus(),
                visibility: document.visibilityState };
  el.focus(); el.click();

  // ทางที่ 1: synthetic paste (ทางหลักของ executeSendSteps)
  const dt = new DataTransfer();
  dt.setData('text/plain', 'PASTE_PATH');
  el.dispatchEvent(new ClipboardEvent('paste',
      {bubbles:true, cancelable:true, clipboardData:dt}));
  out.afterPaste = el.innerText;

  // ทางที่ 2: execCommand (ทาง fallback)
  if (el.innerText.trim() === '') {
    document.execCommand('insertText', false, 'EXEC_PATH');
    out.afterExec = el.innerText;
  } else {
    out.afterExec = '(skipped)';
  }

  // วัดการหน่วง timer: 20 รอบ ห่างละ 10ms ถ้าไม่โดนหน่วงควรจบราว 200-400ms
  // ถ้าโดนหน่วงเหลือ 1 ครั้ง/วินาที จะกินราว 20000ms
  let n = 0; const t0 = Date.now();
  (function tick(){
    if (++n >= 20) {
      out.timerMs = Date.now() - t0;
      out.text = el.innerText;
      fetch('http://127.0.0.1:PORT_/result',
            {method:'POST', body: JSON.stringify(out)});
      return;
    }
    setTimeout(tick, 10);
  })();
}, 8000);
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


def chrome_path():
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(p):
            return p
    sys.exit("ไม่พบ chrome.exe")


def main(use_flags, hide_tab=True):
    tmp = tempfile.mkdtemp(prefix="probe_")
    srv = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    srv.allow_reuse_address = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    flags = [
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling",
    ] if use_flags else []

    exe = chrome_path()
    prof = f"{tmp}\\prof"
    target = subprocess.Popen([exe, f"--user-data-dir={prof}", "--no-first-run",
                               "--window-size=900,700", "--window-position=0,0",
                               *flags, f"http://127.0.0.1:{PORT}/"])
    time.sleep(3)
    # เปิดแท็บใหม่ในโปรไฟล์เดิม = แท็บเป้าหมายถูกซ่อน (document.hidden = true)
    # ตรงกับสภาพจริงตอนโปรแกรมเปิดหลายแท็บแล้วแท็บที่ต้องส่งไม่ใช่แท็บที่เลือกอยู่
    # hide_tab=False = แท็บยังเป็นแท็บที่เลือกอยู่ แค่หน้าต่างไม่มีโฟกัส (สภาพหลังแก้ active:true)
    cover = (subprocess.Popen([exe, f"--user-data-dir={prof}", "--no-first-run",
                               "about:blank"]) if hide_tab else None)
    # เปิดโปรไฟล์อื่นทับเต็มจอด้วย เพื่อให้เสียโฟกัสระดับหน้าต่างพร้อมกัน
    cover2 = subprocess.Popen([exe, f"--user-data-dir={tmp}\\cover", "--no-first-run",
                               "--window-size=1920,1080", "--window-position=0,0",
                               "about:blank"])

    deadline = time.time() + 60
    while time.time() < deadline and not RESULTS:
        time.sleep(0.5)

    for p in (target, cover, cover2):
        if p:
            p.terminate()
    srv.shutdown()
    print(json.dumps({"flags": bool(flags), "hide_tab": hide_tab, "results": RESULTS},
                     ensure_ascii=False))
    time.sleep(1)
    shutil.rmtree(tmp, ignore_errors=True)
    return RESULTS


if __name__ == "__main__":
    main("--no-flags" not in sys.argv, hide_tab="--visible-tab" not in sys.argv)
