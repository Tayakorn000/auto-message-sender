"""เช็คว่าสลับโหมดในหน้าต่างโปรแกรมแล้ว widget โผล่/หายถูก และคำสั่งที่ส่งออกถูกต้อง

import main.py ตรง ๆ (root = tk.Tk() ทำงานตอน import แต่ไม่เข้า mainloop เพราะอยู่ใต้ __main__)
โหมดไลค์/แชร์ต้อง: ซ่อนช่องข้อความ, โชว์ช่อง URL โพสต์, ส่ง mode ผ่าน API ถูก

รัน: python3 test_gui_modes.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("AUTOSENDER_NO_UPDATE_CHECK", "1")  # ห้ามยิง GitHub จริงตอนเทส
import main  # noqa: E402  (root = tk.Tk() ทำงานตอนนี้)

tab = main.tabs_list[0]
tab.frame.update_idletasks()


def shown(w):
    return bool(w.winfo_manager())


def check(cond, msg):
    if not cond:
        sys.exit("FAIL: " + msg)


# --- โหมด messenger: ต้องมีช่องข้อความ ---
tab.var_mode.set("messenger")
tab.frame.update_idletasks()
check(shown(tab.text_msg), "messenger: ช่องข้อความควรโชว์")
check(shown(tab.entry_url_msg), "messenger: ช่อง URL messenger ควรโชว์")
check(not shown(tab.entry_url_post), "messenger: ช่อง URL โพสต์ไม่ควรโชว์")

# --- โหมดไลค์ ---
tab.var_mode.set("like")
tab.frame.update_idletasks()
check(not shown(tab.text_msg), "like: ช่องข้อความไม่ควรโชว์")
check(not shown(tab.frame_preview), "like: พรีวิวไม่ควรโชว์")
check(not shown(tab.frame_limit), "like: จำนวนครั้งไม่ควรโชว์")
check(shown(tab.entry_url_post), "like: ช่อง URL โพสต์ควรโชว์")
check(not shown(tab.entry_url_msg), "like: ช่อง URL messenger ไม่ควรโชว์")
check(shown(tab.btn_send), "like: ปุ่มสั่งงานควรโชว์")
check("ไลค์" in tab.btn_send.cget("text"), "like: ปุ่มควรเขียนว่ากดไลค์")

# --- โหมดแชร์ ---
tab.var_mode.set("share")
tab.frame.update_idletasks()
check(not shown(tab.text_msg), "share: ช่องข้อความไม่ควรโชว์")
check(shown(tab.entry_url_post), "share: ช่อง URL โพสต์ควรโชว์")
check("แชร์" in tab.btn_send.cget("text"), "share: ปุ่มควรเขียนว่าแชร์")

# --- กลับมา messenger: ช่องข้อความต้องกลับมาครบ ตามลำดับเดิม ---
tab.var_mode.set("messenger")
tab.frame.update_idletasks()
for w, name in ((tab.lbl_msg_head, "หัวข้อ"), (tab.text_msg, "ช่องข้อความ"),
                (tab.frame_limit, "จำนวนครั้ง"), (tab.frame_preview, "พรีวิว")):
    check(shown(w), "กลับมา messenger: %s ควรกลับมาโชว์" % name)
kids = [str(w) for w in tab.frame_msg.pack_slaves()]
check(kids.index(str(tab.text_msg)) < kids.index(str(tab.btn_send)),
      "กลับมา messenger: ช่องข้อความควรอยู่เหนือปุ่มส่ง ได้ลำดับ %s" % kids)

# --- สั่งงานจริง: mode ที่ส่งออกทาง API ต้องเป็น like/share ---
tab.var_sys_on.set(True)
tab.var_mode.set("like")
tab.entry_url_post.delete(0, main.tk.END)
tab.entry_url_post.insert(0, "https://www.facebook.com/x/posts/123")
tab.action_send()
sent = main.presets_data[tab.preset_key]
check(sent["mode"] == "like", "action_send: mode ควรเป็น like ได้ %r" % sent["mode"])
check(sent["action_type"] == "send", "action_send: action_type ควรเป็น send")
check(sent["url_post"].endswith("/123"), "action_send: url_post ควรถูกส่งไปด้วย")

# --- API ต้องคืน mode ให้ extension ---
main.app.config.update(TESTING=True)
client = main.app.test_client()
res = client.get("/api/get-task/%s/uid_test" % tab.preset_key).get_json()
check(res["status"] == "has_task", "API: ควรมีงาน ได้ %r" % res)
check(res["mode"] == "like", "API: mode ควรเป็น like ได้ %r" % res.get("mode"))

print("OK: สลับโหมดไลค์/แชร์แล้ว UI ถูก และคำสั่งส่งออกถูก")
