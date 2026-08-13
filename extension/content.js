function getCleanId(href) {
    if (!href) return Math.random().toString();
    try {
        let u = new URL(href, window.location.origin);
        if (u.searchParams.has('fbid')) return u.searchParams.get('fbid');
        if (u.searchParams.has('story_fbid')) return u.searchParams.get('story_fbid');
        return u.pathname; 
    } catch(e) {
        return href.split('?')[0];
    }
}

// ⚡ เข้าแท็บแบบไม่รอ!
if (window.location.href.includes('auto_photos_by=1')) {
    setTimeout(async () => {
        let tabClicked = await clickPhotosTab();
        if (tabClicked) {
            await new Promise(r => setTimeout(r, 20)); 
            await clickPhotosByTab(); 
        }
    }, 20); 
} else if (window.location.href.includes('auto_photos=1')) {
    setTimeout(() => { clickPhotosTab(); }, 20); 
}

function clickPhotosTab() {
    return new Promise(resolve => {
        let retry = 0;
        function tryClick() {
            let tabs = Array.from(document.querySelectorAll('a[role="tab"], a[href*="/photos"], div[role="tab"]'));
            let photoTab = tabs.find(el => {
                let href = (el.href || "").toLowerCase();
                let text = (el.innerText || "").toLowerCase().trim();
                return href.endsWith('/photos') || href.endsWith('/photos/') || href.includes('sk=photos') || text === 'รูปภาพ' || text === 'photos';
            });

            if (!photoTab) {
                let allLinks = Array.from(document.querySelectorAll('a'));
                photoTab = allLinks.find(a => {
                    let text = (a.innerText || "").trim().toLowerCase();
                    return text === 'รูปภาพ' || text === 'photos';
                });
            }

            if (photoTab && photoTab.offsetWidth > 0) {
                photoTab.click();
                resolve(true);
            } else {
                retry++;
                if (retry >= 50) resolve(false); 
                else setTimeout(tryClick, 20); 
            }
        }
        tryClick();
    });
}

function clickPhotosByTab() {
    return new Promise(resolve => {
        let retry = 0;
        function tryClick() {
            let links = Array.from(document.querySelectorAll('a[href*="/photos_by"], a[role="tab"]'));
            let targetTab = links.find(a => {
                let href = (a.href || "").toLowerCase();
                let text = (a.innerText || "").toLowerCase().trim();
                return href.includes('/photos_by') || text.includes('your photos') || text.includes('รูปภาพของคุณ') || text.includes("'s photos") || text.includes("ของ");
            });

            if (targetTab && targetTab.offsetWidth > 0) {
                targetTab.click();
                resolve(true);
            } else {
                retry++;
                if (retry >= 50) resolve(false);
                else setTimeout(tryClick, 20);
            }
        }
        tryClick();
    });
}

// ค้นหาและกดปุ่ม "ส่งข้อความ" บนหน้าโปรไฟล์เพจ
function clickPageMessageButton() {
    return new Promise(resolve => {
        let retry = 0;
        function tryClick() {
            let btns = Array.from(document.querySelectorAll('div[role="button"], a[role="button"], span[dir="auto"]'));
            let msgBtn = btns.find(b => {
                let text = (b.innerText || "").toLowerCase().trim();
                let aria = (b.getAttribute("aria-label") || "").toLowerCase().trim();
                return text === "message" || text === "ส่งข้อความ" || 
                       aria === "message" || aria.includes("ส่งข้อความ") || aria === "send message";
            });
            
            if (msgBtn && msgBtn.offsetWidth > 0) {
                msgBtn.click();
                resolve(true);
            } else {
                retry++;
                if (retry >= 100) resolve(false);
                else setTimeout(tryClick, 20);
            }
        }
        tryClick();
    });
}

// ==========================================
// 👍 กดไลค์ / 🔁 แชร์โพสต์ (ทางเดินเดียวกับส่งข้อความ)
// ==========================================
const isVisible = el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
// ponytail: Facebook แทรก NBSP คั่นคำแทนช่องว่างธรรมดา ("Share now", "Remove Like")
// trim() ตัด NBSP หัวท้ายให้อยู่แล้ว แต่ตัวที่อยู่กลางคำต้องล้างเอง ไม่งั้น === / includes พลาด
const norm = s => (s || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").toLowerCase().trim();
const ariaOf = el => norm(el.getAttribute('aria-label'));
const textOf = el => norm(el.innerText);

// ponytail: รอแบบ poll ธรรมดา ไม่ใช้ MutationObserver เพราะ Facebook เปลี่ยน DOM รัวมาก
// observer จะยิงถี่กว่าที่ต้องใช้ คืนค่าที่ fn คืนมา หรือ null เมื่อหมดเวลา
function waitFor(fn, timeoutMs) {
    return new Promise(resolve => {
        const deadline = Date.now() + (timeoutMs || 5000);
        (function tick() {
            let r = null;
            try { r = fn(); } catch (e) { r = null; }
            if (r) return resolve(r);
            if (Date.now() >= deadline) return resolve(null);
            setTimeout(tick, 50);
        })();
    });
}

// ponytail: จำกัดขอบเขตไว้ที่ตัวโพสต์ ไม่งั้นไปโดนปุ่มถูกใจของเพจด้านบน (ไลค์เพจแทนโพสต์)
// หรือปุ่มถูกใจของคอมเมนต์ — Facebook ใช้ role="article" ซ้อนกันสำหรับคอมเมนต์
// เอา article ที่ไม่ได้ซ้อนอยู่ในอันอื่น = ตัวโพสต์
function postScope() {
    const arts = Array.from(document.querySelectorAll('div[role="article"]')).filter(isVisible);
    if (arts.length === 0) return null;
    return arts.find(a => !arts.some(b => b !== a && b.contains(a))) || arts[0];
}

function postButtons(selector) {
    const scope = postScope();
    return Array.from((scope || document).querySelectorAll(selector))
        .filter(isVisible)
        // ตัดปุ่มของคอมเมนต์ (อยู่ใน article ซ้อนอีกชั้น) ออก
        .filter(el => !scope || el.closest('div[role="article"]') === scope);
}

const LIKE_LABELS = ["ถูกใจ", "like"];
// ต้องเช็คคำพวกนี้ "ก่อน" ไม่งั้นกดซ้ำ = เอาไลค์ที่มีอยู่ออก
const UNLIKE_LABELS = ["เอาการถูกใจออก", "ยกเลิกการถูกใจ", "remove like", "unlike"];

function findLikeBtn() {
    const btns = postButtons('div[role="button"], span[role="button"]');
    for (const b of btns) {
        const a = ariaOf(b), t = textOf(b);
        if (UNLIKE_LABELS.some(x => a.includes(x) || t === x)) return { el: b, liked: true };
        if (b.getAttribute('aria-pressed') === "true" && LIKE_LABELS.some(x => a.includes(x))) {
            return { el: b, liked: true };
        }
        if (LIKE_LABELS.some(x => a === x || t === x)) return { el: b, liked: false };
    }
    return null;
}

async function clickLike() {
    const hit = await waitFor(findLikeBtn, 8000);
    if (!hit) return false;
    if (hit.liked) return true; // ไลค์ไว้แล้ว กดซ้ำจะกลายเป็นเอาไลค์ออก
    hit.el.click();
    // ยืนยันว่าปุ่มเปลี่ยนเป็นสถานะไลค์แล้วจริง ไม่ใช่แค่กดลงไป
    return !!(await waitFor(() => {
        const h = findLikeBtn();
        return h && h.liked ? h : null;
    }, 3000));
}

const SHARE_EXACT = ["แชร์", "share"];
const SHARE_ARIA_PART = ["ส่งโพสต์นี้ให้เพื่อน", "send this to friends", "แชร์โพสต์นี้"];
// แชร์ลงฟีดตัวเอง ไม่ใช่ส่งให้เพื่อนในแชท
const SHARE_NOW = ["แชร์ตอนนี้", "share now", "แชร์ไปยังฟีด", "แชร์ไปที่ฟีด", "share to feed"];
const POST_BTN = ["โพสต์", "post", "แชร์", "share"];

async function clickShare() {
    const shareBtn = await waitFor(() => {
        const btns = postButtons('div[role="button"], span[role="button"], a[role="button"]');
        // เทียบแบบตรงตัว ไม่งั้นไปโดน "แชร์แล้ว 12 ครั้ง"
        return btns.find(b => SHARE_EXACT.some(x => ariaOf(b) === x || textOf(b) === x) ||
                              SHARE_ARIA_PART.some(x => ariaOf(b).includes(x))) || null;
    }, 8000);
    if (!shareBtn) return false;
    shareBtn.click();

    const item = await waitFor(() => {
        const els = Array.from(document.querySelectorAll(
            'div[role="menuitem"], div[role="button"], span[role="button"]')).filter(isVisible);
        return els.find(e => SHARE_NOW.some(x => ariaOf(e).includes(x) || textOf(e).includes(x))) || null;
    }, 6000);
    if (!item) return false;
    item.click();

    // ทาง "แชร์ไปยังฟีด" จะเปิดกล่องเขียนโพสต์ ต้องกดปุ่มโพสต์ในกล่องอีกที
    // ทาง "แชร์ตอนนี้" จบตั้งแต่บรรทัดบน ไม่มีกล่องขึ้น waitFor คืน null แล้วผ่านไป
    const post = await waitFor(() => {
        const dlg = document.querySelector('div[role="dialog"]');
        if (!dlg) return null;
        const els = Array.from(dlg.querySelectorAll(
            'div[role="button"], span[role="button"]')).filter(isVisible);
        return els.find(e => POST_BTN.some(x => ariaOf(e) === x || textOf(e) === x)) || null;
    }, 2500);
    if (post) post.click();
    return true;
}

function reloadIfStillActive(url) {
    setTimeout(() => {
        chrome.storage.local.get(['monitoring_active'], function(res) {
            if (res.monitoring_active) window.location.href = url;
        });
    }, 800); 
}

function playSuccessSound() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        if (!ctx) return;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain); gain.connect(ctx.destination);
        osc.type = 'square'; 
        osc.frequency.setValueAtTime(1200, ctx.currentTime); 
        osc.frequency.setValueAtTime(2400, ctx.currentTime + 0.05); 
        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(0.2, ctx.currentTime + 0.02); 
        gain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.1); 
        osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.1);
    } catch (e) { }
}

function showSuccessNotificationAndTurnOff() {
    playSuccessSound(); 
    let div = document.createElement('div');
    div.style.position = 'fixed'; div.style.top = '80px'; div.style.right = '20px';
    div.style.backgroundColor = '#dc3545'; div.style.color = 'white'; div.style.padding = '20px 25px';
    div.style.fontSize = '18px'; div.style.fontFamily = 'Tahoma, sans-serif'; div.style.fontWeight = 'bold';
    div.style.zIndex = '9999999'; div.style.borderRadius = '8px'; div.style.boxShadow = '0 4px 12px rgba(0,0,0,0.6)';
    div.innerHTML = '⚡ ทำงานจบในเสี้ยววินาที!<br><span style="font-size:14px; font-weight:normal;">ระบบหยุดทำงานอัตโนมัติ</span>';
    let closeBtn = document.createElement('span'); closeBtn.innerHTML = ' &times;'; closeBtn.style.cursor = 'pointer'; closeBtn.style.float = 'right'; closeBtn.style.marginLeft = '20px'; closeBtn.style.fontSize = '24px';
    closeBtn.onclick = () => div.remove(); div.appendChild(closeBtn);
    document.body.appendChild(div);
    fetch('http://localhost:5000/api/turn-off-auto').catch(e => e);
}

// 🟢 ระบบ Auto Monitor 
function runAutoMonitor() {
    chrome.storage.local.get([
        'monitoring_active', 'monitor_message', 'monitor_limit', 
        'monitor_mode', 'monitor_url', 'last_seen_items'
    ], async function(config) {
        
        if (!config.monitoring_active) return; 

        const isPhotoByMonitor = window.location.href.includes('auto_photos_by=1');
        const isPhotoMonitor = window.location.href.includes('auto_photos=1');
        const isPhotoTarget = config.monitor_url.includes('auto_photos') || config.monitor_url.includes('/photos');

        if (isPhotoByMonitor) {
            await new Promise(r => setTimeout(r, 50)); 
            let tabClicked = await clickPhotosTab();
            if (tabClicked) {
                await new Promise(r => setTimeout(r, 50)); 
                await clickPhotosByTab(); 
                await new Promise(r => setTimeout(r, 100)); 
            } else return reloadIfStillActive(config.monitor_url);
        } 
        else if (isPhotoMonitor) {
            await new Promise(r => setTimeout(r, 50)); 
            let tabClicked = await clickPhotosTab();
            if (tabClicked) await new Promise(r => setTimeout(r, 100)); 
            else return reloadIfStillActive(config.monitor_url);
        } else await new Promise(r => setTimeout(r, 100)); 

        let foundItems = [];

        if (isPhotoTarget) {
            const links = Array.from(document.querySelectorAll('a[href*="/photo"], a[href*="fbid="]'))
                .filter(a => a.offsetWidth > 40 && a.offsetHeight > 40 && !a.closest('header') && !a.closest('nav'));
            for (let a of links) {
                let id = getCleanId(a.href);
                if (id && !foundItems.some(item => item.id === id)) foundItems.push({ id: id, el: a, href: a.href }); 
                if (foundItems.length >= 10) break; 
            }
        } else {
            const posts = Array.from(document.querySelectorAll('div[role="article"], div[data-pagelet^="FeedUnit_"]'));
            for (let p of posts) {
                let timeLink = p.querySelector('a[href*="/posts/"], a[href*="/permalink/"], a[href*="fbid="]');
                let commentBtn = p.querySelector('div[aria-label="แสดงความคิดเห็น"], div[aria-label="Leave a comment"], div[aria-label="Comment"]');
                let id = null;
                if (timeLink) id = getCleanId(timeLink.href);
                else if (commentBtn) id = "post_" + p.innerText.replace(/\s+/g, '').substring(0, 30);
                if (id && !foundItems.some(item => item.id === id)) foundItems.push({ id: id, el: commentBtn || timeLink, href: (timeLink ? timeLink.href : "No Link") });
                if (foundItems.length >= 10) break; 
            }
        }

        if (foundItems.length === 0) return reloadIfStillActive(config.monitor_url);

        let currentIds = foundItems.map(i => i.id);
        let previousIds = Array.isArray(config.last_seen_items) ? config.last_seen_items : [];

        if (previousIds.length === 0) {
            chrome.storage.local.set({ last_seen_items: currentIds }, () => { reloadIfStillActive(config.monitor_url); });
        } 
        else {
            let newItem = foundItems.find(item => !previousIds.includes(item.id));
            if (!newItem) reloadIfStillActive(config.monitor_url);
            else {
                chrome.storage.local.get(['monitoring_active'], function(res) {
                    if (res.monitoring_active) {
                        chrome.storage.local.set({ last_seen_items: currentIds }, () => {
                            if (newItem.el) {
                                newItem.el.click(); 
                                setTimeout(async () => {
                                    let successCount = 0;
                                    for(let i=0; i<config.monitor_limit; i++) {
                                        try {
                                            await forceSend(config.monitor_message, config.monitor_mode, true);
                                            successCount++;
                                            if (i < config.monitor_limit - 1) await new Promise(r => setTimeout(r, 100)); 
                                        } catch(e) { break; }
                                    }
                                    chrome.storage.local.set({ monitoring_active: false }, () => {
                                        if (successCount > 0) showSuccessNotificationAndTurnOff();
                                    });
                                }, 1); 
                            }
                        });
                    }
                });
            }
        }
    });
}

runAutoMonitor();

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "runBot") {
        const mode = request.task.mode || "messenger";
        const limit = request.task.limit || 1;
        const text = request.task.message;
        // ponytail: ข้อความว่าง = พิมพ์ไม่มีอะไร กด Enter เปล่า Facebook ไม่ส่งอะไรเลย
        // แต่เดิมตอบว่าสำเร็จ = "กดแล้วไม่มีอะไรเกิด" ที่หาสาเหตุไม่เจอ (ไลค์/แชร์ไม่ต้องมีข้อความ)
        if (mode !== "like" && mode !== "share" && !(text || "").trim()) {
            sendResponse({ status: "error", error: "ยังไม่ได้พิมพ์ข้อความที่จะส่ง" });
            return true;
        }
        const targetUrl = request.task.url_post || "";
        const isPageLink = request.task.is_page_link || false; 
        
        async function executeSendLoop() {
            const isPhotoTarget = targetUrl.includes('auto_photos') || targetUrl.includes('/photos');

            // 👍/🔁 โหมดไลค์+แชร์ ไม่ต้องพิมพ์อะไร จบตรงนี้
            if (mode === "like" || mode === "share") {
                const ok = mode === "like" ? await clickLike() : await clickShare();
                sendResponse(ok ? { status: "success" }
                                : { status: "error", error: `หาปุ่ม${mode === "like" ? "ถูกใจ" : "แชร์"}ไม่เจอ` });
                return;
            }

            if ((mode === "messenger" || mode === "all") && isPageLink) {
                let btnClicked = await clickPageMessageButton();
                if (btnClicked) {
                    await new Promise(resolve => setTimeout(resolve, 800)); 
                }
            }
            else if (mode === "post" && isPhotoTarget) {
                const links = Array.from(document.querySelectorAll('a[href*="/photo"], a[href*="fbid="]'))
                    .filter(a => a.offsetWidth > 40 && a.offsetHeight > 40 && !a.closest('header') && !a.closest('nav')); 
                if (links.length > 0) {
                    links[0].click(); 
                    await new Promise(resolve => setTimeout(resolve, 2000)); 
                }
            }

            for (let i = 0; i < limit; i++) {
                try {
                    await forceSend(text, mode, isPhotoTarget, isPageLink);
                    if (i < limit - 1) await new Promise(resolve => setTimeout(resolve, 1500)); 
                } catch (err) {
                    sendResponse({ status: "error", error: err.message });
                    return; 
                }
            }
            sendResponse({ status: "success" });
        }
        executeSendLoop();
        return true; 
    }
});

// 🟢 หากล่องพิมพ์ ต้องเจอเองโดยไม่ต้องรอให้คนเอาเมาส์ไปคลิกก่อน
// เดิมพึ่ง aria-label ที่ hardcode ไว้ ("message"/"ข้อความ"/...) พอ Facebook ใช้คำอื่น
// ก็หาไม่เจอ แล้วไปติดที่ document.activeElement ซึ่งจะมีค่าก็ต่อเมื่อคนคลิกในกล่องเอง
// = อาการ "ต้องกดที่จอก่อนถึงจะส่งได้"
function findInputEl(mode, isPhotoTarget) {
    const activeEl = document.activeElement;
    if (activeEl && activeEl.getAttribute && activeEl.getAttribute("contenteditable") === "true") {
        return activeEl;
    }

    // ponytail: รับทุก tag ที่ contenteditable ไม่ใช่แค่ div[role="textbox"]
    // เผื่อ Facebook เปลี่ยนโครงสร้าง
    const els = Array.from(document.querySelectorAll('[contenteditable="true"]'))
        .filter(el => el.offsetWidth > 0 && el.offsetHeight > 0);

    const labelOf = el => ((el.getAttribute('aria-label') || "") + " " +
                           (el.getAttribute('aria-placeholder') || "") + " " +
                           (el.getAttribute('placeholder') || "") + " " +
                           (el.getAttribute('data-text') || "")).toLowerCase();

    // ตัดกล่องที่ไม่ใช่ที่พิมพ์ข้อความแน่ ๆ ออก (ช่องค้นหา / กล่องตั้งสเตตัส)
    const BAD = ["คิดอะไรอยู่", "mind", "search", "ค้นหา"];
    // โหมดแชท ห้ามไปโดนกล่องคอมเมนต์เด็ดขาด
    const BAD_CHAT = ["comment", "ความคิดเห็น", "คอมเมนต์"];
    const validEls = els.filter(el => {
        const l = labelOf(el);
        if (BAD.some(b => l.includes(b))) return false;
        if (mode === "messenger" && BAD_CHAT.some(b => l.includes(b))) return false;
        return true;
    });
    if (validEls.length === 0) return null;

    if (mode !== "messenger") {
        if (mode === "post" && !isPhotoTarget) return validEls[0];
        return validEls[validEls.length - 1];
    }

    // โหมด Messenger: เลือกกล่องแชท ห้ามไปโดนกล่องคอมเมนต์
    // ponytail: "write to <ชื่อ>" / "เขียนถึง <ชื่อ>" คือป้ายจริงของกล่องแชทหน้าเพจ
    // (ดู DOM จริงบน facebook.com/<เพจ> แล้ว) ไม่มีคำว่า message/ข้อความ เลยสักคำ
    // เดิมตกมาถึงทางสุดท้าย (เดาจากตำแหน่งบนจอ) ซึ่งบังเอิญถูกตอนมีกล่องเดียว
    const GOOD = ["message", "ข้อความ", "ส่งข้อความ", "สนทนา", "chat", "write to", "เขียนถึง",
                  "เขียนข้อความ", "พิมพ์ข้อความ", "aa", "reply", "ตอบกลับ"];
    const named = validEls.filter(el => {
        const l = labelOf(el).trim();
        return GOOD.some(g => l.includes(g));
    });
    if (named.length > 0) return named[named.length - 1];

    // ไม่มีชื่อให้จับ: เอากล่องที่อยู่ในหน้าต่างแชท popup ก่อน
    const popup = validEls.filter(el => el.closest('div[role="dialog"]') ||
                                        el.closest('div[data-pagelet="ChatTab"]') ||
                                        el.closest('.fb_dialog'));
    if (popup.length > 0) return popup[popup.length - 1];

    // ponytail: ทางสุดท้าย เอากล่องที่อยู่ล่างสุดของจอ = ช่องพิมพ์ของหน้าแชท
    // เดิมตรงนี้คืน null แล้ววนรอจนคนไปคลิกเอง ซึ่งคือบั๊กที่ผู้ใช้เจอ
    return validEls.reduce((lowest, el) =>
        (!lowest || el.getBoundingClientRect().top > lowest.getBoundingClientRect().top)
            ? el : lowest, null);
}

// ponytail: จำว่ารู้ผลเรื่องปุ่ม "เริ่มต้นใช้งาน" แล้ว (กดไปแล้ว หรือรอจนครบแล้วไม่มี)
// ครั้งต่อไปในหน้าเดิมจะได้ไม่ต้องรออีก ไม่งั้นส่ง 1000 ครั้ง = รอเปล่ารอบละ 500 ms
let gsSettled = false;

// 🟢 แยกระหว่าง "กล่องคอมเมนต์" กับ "กล่องแชท" อย่างเด็ดขาด!
const GS_LABELS = ["เริ่มต้นใช้งาน", "get started", "เริ่มต้นการสนทนา", "เริ่มการสนทนา",
                   "เริ่มแชท", "start chat", "เริ่มต้น", "เริ่มสนทนา"];

// ponytail: เดิมเทียบชื่อปุ่มแบบ "ตรงเป๊ะ" ทำให้ป้ายที่มีคำอื่นพ่วง ("เริ่มต้นใช้งาน 👋") หลุดหมด
// และ Facebook ห่อ span ที่มีข้อความไว้ใต้ตัวที่คลิกได้จริงบ้าง สลับกันบ้าง แล้วแต่หน้า
// ใช้ includes + จำกัดความยาวป้าย (กันไปโดนย่อหน้ายาว ๆ ที่บังเอิญมีคำนี้)
function findGsBtns() {
    const hit = t => t && t.length <= 40 && GS_LABELS.some(g => t.includes(g));
    const cands = Array.from(document.querySelectorAll(
            'div[role="button"], span[role="button"], a[role="button"], button, ' +
            'div[role="link"], a[role="link"]'))
        .filter(isVisible)
        .filter(b => hit(norm(b.innerText)) || hit(norm(b.getAttribute("aria-label"))));
    // ปุ่มซ้อนกัน เอาตัวในสุด ไม่งั้นกดโดนกรอบนอกที่ไม่ใช่ปุ่มจริง
    return cands.filter(b => !cands.some(o => o !== b && b.contains(o)));
}

// ponytail: Messenger กั้นห้องแชทเก่าด้วยหน้าประกาศเข้ารหัส ต้องกด "ดำเนินการต่อ"/"Continue" ก่อน
// ไม่กด = ไม่มีกล่องพิมพ์บนหน้าเลย (เจอกับตัวตอนทดสอบส่งจริง ได้ข้อความเดียวกับที่ลูกค้าเจอเป๊ะ:
// "กล่องพิมพ์ 0/0 | ปุ่มเริ่มต้นใช้งาน 0")
// กดเฉพาะตอนไม่มีกล่องพิมพ์เลย และห้ามโดนปุ่มล็อกอิน "ดำเนินการต่อในชื่อ ..." ของ messenger.com
const GATE_LABELS = ["ดำเนินการต่อ", "continue"];
const GATE_SKIP = ["ในชื่อ", "as ", "log in", "เข้าสู่ระบบ"];

function findGateBtns() {
    const hit = t => t && t.length <= 30 && GATE_LABELS.some(g => t.includes(g)) &&
                     !GATE_SKIP.some(s => t.includes(s));
    const cands = Array.from(document.querySelectorAll(
            'div[role="button"], span[role="button"], a[role="button"], button'))
        .filter(isVisible)
        .filter(b => hit(norm(b.innerText)) || hit(norm(b.getAttribute("aria-label"))));
    return cands.filter(b => !cands.some(o => o !== b && b.contains(o)));
}

// ponytail: "หาช่องพิมพ์ไม่เจอ" เฉย ๆ บอกอะไรไม่ได้เลย ต้องเดาต่อว่าหน้ายังโหลด/ต้องล็อกอิน/
// หรือมีกล่องแต่คัดออกหมด — แนบสภาพหน้าจริงตอนยอมแพ้ไปด้วย จะได้จบในรอบเดียว
function whyNoInput() {
    const vis = el => el.offsetWidth > 0 && el.offsetHeight > 0;
    const boxes = Array.from(document.querySelectorAll('[contenteditable="true"]'));
    const gs = Array.from(document.querySelectorAll('[role="button"], button'))
        .filter(b => GS_LABELS.includes(norm(b.innerText)) ||
                     GS_LABELS.includes(norm(b.getAttribute("aria-label"))));
    return "หาช่องพิมพ์ไม่เจอ (รอ 20 วิ" +
           " | กล่องพิมพ์ " + boxes.filter(vis).length + "/" + boxes.length +
           " | ปุ่มเริ่มต้นใช้งาน " + gs.length +
           " | ปุ่มดำเนินการต่อ " + findGateBtns().length +
           " | หน้า " + document.readyState +
           (document.querySelector('input[name="pass"], form[action*="login"]') ? " | ยังไม่ได้ล็อกอิน" : "") +
           ")";
}

function forceSend(text, mode, isPhotoTarget = false, isPageLink = false) {
    return new Promise((resolve, reject) => {
        let retryCount = 0;
        // ponytail: 300 รอบ × 10 ms = รอแค่ 3 วิ ซึ่งสั้นกว่าเวลาที่หน้า Facebook โหลดเสร็จ
        // เปิดหลายโปรไฟล์พร้อมกันยิ่งช้า = ยอมแพ้ก่อนกล่องพิมพ์จะโผล่ (background ให้เวลา 30 วิ+ อยู่แล้ว)
        const maxRetries = 2000;
        const gsClicked = new Set();   // กดปุ่มไหนไปแล้วบ้าง
        let gsWaits = 0; // ponytail: นับแยกจาก retryCount ไม่งั้นหน้าโหลดช้าจะข้ามการรอไปเลย

        function tryFindInput() {
            // สแกนหาปุ่ม "เริ่มต้นใช้งาน" — แชทที่ยังไม่เคยคุยกับเพจจะ "ไม่มีกล่องพิมพ์เลย"
            // จนกว่าจะกดปุ่มนี้ ถ้ากดไม่โดน = หากล่องพิมพ์ยังไงก็ไม่เจอ
            if (mode === "messenger" || mode === "all") {
                // ponytail: เดิมกดได้ครั้งเดียวจบ กดพลาดปุ่มเดียว = จบเห่ทั้งงาน
                // ตอนนี้ไล่กดตัวที่ยังไม่ได้กด ทีละอันจนกล่องพิมพ์โผล่ (กดซ้ำอันเดิมไม่มีประโยชน์)
                const fresh = findGsBtns().filter(b => !gsClicked.has(b));
                if (fresh.length > 0) {
                    gsClicked.add(fresh[0]);
                    fresh[0].click();
                    gsSettled = true;
                    setTimeout(tryFindInput, 300);
                    return;
                }
            }

            let inputEl = findInputEl(mode, isPhotoTarget);

            // ponytail: เฉพาะลิงก์เพจ รอปุ่ม "เริ่มต้นใช้งาน" ได้อีกไม่เกิน 500 ms หลังเจอกล่องพิมพ์
            // โค้ดหากล่องตัวใหม่เจอกล่องเร็วกว่าที่ Facebook จะ render ปุ่มเสร็จ
            // ไม่รอ = ปุ่มไม่ถูกกด แล้วพิมพ์ลงกล่องที่ยังใช้งานไม่ได้ ส่งไม่ออก
            // เคยเอาการรอออกมาใช้กับทุกแชท = กดส่งแล้วหน่วงทุกครั้ง ทั้งที่แชทธรรมดาไม่มีปุ่มนี้
            // ลืมติ๊กช่องลิงก์เพจก็ยังใช้ได้ เพราะแชทที่ยังไม่เริ่มจะ "ไม่มีกล่องพิมพ์เลย"
            // ลูปข้างบนจึงเจอปุ่มแล้วกดให้เองอยู่ดี การรอนี้กันแค่จังหวะปุ่มมาช้ากว่ากล่อง
            if (inputEl && isPageLink && !gsSettled && gsClicked.size === 0 &&
                (mode === "messenger" || mode === "all")) {
                if (gsWaits < 50) {
                    gsWaits++;
                    setTimeout(tryFindInput, 10);
                    return;
                }
                gsSettled = true; // รอครบแล้วไม่มีปุ่ม = แชทธรรมดา ครั้งต่อไปไม่ต้องรอ
            }

            if (inputEl) {
                executeSendSteps(inputEl, text, resolve, mode); // ส่ง mode ไปด้วย
            } else {
                // ไม่มีกล่องพิมพ์เลย = อาจโดนหน้าประกาศเข้ารหัสกั้นอยู่ กดผ่านให้ทีละปุ่ม
                const gate = findGateBtns().filter(b => !gsClicked.has(b));
                if (gate.length > 0) {
                    gsClicked.add(gate[0]);
                    gate[0].click();
                    setTimeout(tryFindInput, 300);
                    return;
                }
                if (mode === "post" && !isPhotoTarget && retryCount === 0) {
                    const commentBtns = Array.from(document.querySelectorAll('div[aria-label="แสดงความคิดเห็น"], div[aria-label="Leave a comment"], div[aria-label="Comment"]')).filter(btn => btn.offsetWidth > 0);
                    if (commentBtns.length > 0) commentBtns[0].click(); 
                }
                retryCount++;
                if (retryCount >= maxRetries) reject(new Error(whyNoInput()));
                else setTimeout(tryFindInput, 10); 
            }
        }
        tryFindInput();
    });
}

function executeSendSteps(inputEl, text, resolve, mode) {
    inputEl.focus();
    inputEl.click();

    setTimeout(() => {
        const dataTransfer = new DataTransfer();
        dataTransfer.setData('text/plain', text);
        inputEl.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dataTransfer }));

        setTimeout(() => {
            if (inputEl.innerText.trim() === "") document.execCommand('insertText', false, text);
            inputEl.dispatchEvent(new Event('input', { bubbles: true }));
            inputEl.dispatchEvent(new Event('change', { bubbles: true }));

            setTimeout(() => {
                ['keydown', 'keypress', 'keyup'].forEach(evtType => {
                    inputEl.dispatchEvent(new KeyboardEvent(evtType, { bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13 }));
                });

                setTimeout(() => {
                    if (inputEl.innerText.trim() !== "") {
                        // 🎯 ป้องกันการกดปุ่มคอมเมนต์พลาด ในโหมด Messenger
                        let safeSendSelectors = ['div[aria-label="ส่ง"]', 'div[aria-label="Send"]'];
                        if (mode !== "messenger") {
                            safeSendSelectors.unshift('div[aria-label="แสดงความคิดเห็น"]', 'div[aria-label="Comment"]');
                        }
                        safeSendSelectors.push('div[role="button"] i'); // ปุ่มจรวดแบบ fallback

                        for (let sel of safeSendSelectors) {
                            const btns = Array.from(document.querySelectorAll(sel)).filter(btn => {
                                if (btn.offsetWidth === 0) return false;
                                let aria = (btn.getAttribute('aria-label') || "").toLowerCase();
                                // ถ้าอยู่ในโหมดแชท ห้ามกดปุ่มที่มีคำว่า "คอมเมนต์"
                                if (mode === "messenger" && (aria.includes("comment") || aria.includes("ความคิดเห็น"))) return false;
                                return true;
                            });
                            
                            if (btns.length > 0) {
                                let targetBtn = btns[btns.length - 1];
                                targetBtn.click();
                                if(targetBtn.parentElement && targetBtn.tagName.toLowerCase() === 'i') targetBtn.parentElement.click();
                                break; 
                            }
                        }
                    }
                    resolve(); 
                }, 1); 
            }, 1); 
        }, 1); 
    }, 1); 
}