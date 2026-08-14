"""เทสว่าเปิดพอร์ต 5000 ไม่ได้แล้วโปรแกรมรู้ตัว (เดิมเธรด API ตายเงียบ ๆ)

อาการจริงที่เจอ: ส่วนขยายยิงไปโดนโปรแกรมอื่นที่ยึดพอร์ตอยู่ (Mac = AirPlay Receiver)
ได้ error ที่ chrome://extensions ว่า "No 'Access-Control-Allow-Origin' header"
ส่วนหน้าโปรแกรมดูปกติทุกอย่าง ไม่มีอะไรบอกว่าพัง

รัน: python3 test_api_port.py
"""
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("AUTOSENDER_NO_UPDATE_CHECK", "1")
import main  # noqa: E402

hog = socket.socket()
hog.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    hog.bind(("127.0.0.1", 5000))
    hog.listen(1)
except OSError:
    pass  # มีตัวอื่นยึด 5000 อยู่แล้ว (เช่น AirPlay) ก็ใช้ทดสอบได้เหมือนกัน

main.run_api_server()   # ต้องไม่โยน exception และต้องคืนค่ากลับมา ไม่ค้าง

assert main.api_error, "พอร์ตถูกยึดแล้วต้องตั้ง api_error ไม่ใช่ตายเงียบ"
assert "5000" in main.api_error, main.api_error
print("PASS: พอร์ตถูกยึด -> ขึ้นเตือนในโปรแกรม")
