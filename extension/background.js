let lastProcessedTaskId = 0; 

function getExtensionIdentity(callback) {
    chrome.storage.local.get(['preset_group', 'unique_id'], function(result) {
        let presetGroup = result.preset_group || 'profile_1'; 
        let uniqueId = result.unique_id;
        
        if (!uniqueId) {
            uniqueId = 'uid_' + Math.random().toString(36).substr(2, 9);
            chrome.storage.local.set({ 'unique_id': uniqueId });
        }
        callback(presetGroup, uniqueId);
    });
}

// บอกเวอร์ชันส่วนขยายให้โปรแกรมหลักรู้ ไปโผล่ในหน้า "อัปเดตโปรแกรม"
// (Chrome อัปเดตส่วนขยายที่โหลดแบบ unpacked ให้เองไม่ได้ ต้องบอกให้คนกด Reload)
const EXT_VERSION = chrome.runtime.getManifest().version;

function fetchTaskFromServer() {
    getExtensionIdentity(function(presetGroup, uniqueId) {
        fetch(`http://localhost:5000/api/get-task/${presetGroup}/${uniqueId}?v=${EXT_VERSION}`)
            .then(response => response.json())
            .then(data => {
                if (data.status === "has_task" && data.task_id) {
                    if (data.task_id <= lastProcessedTaskId) return;
                    lastProcessedTaskId = data.task_id;
                    console.log(`[${presetGroup}] ได้รับคำสั่ง: ${data.action_type}`);

                    // 🟢 โหมด Auto Monitor
                    if (data.action_type === "start_auto_monitor") {
                        let finalMonitorUrl = data.url_post;
                        let secretCommand = "";

                        if (finalMonitorUrl) {
                            if (finalMonitorUrl.includes('/photos_by') || finalMonitorUrl.includes('sk=photos_by')) {
                                secretCommand = "auto_photos_by=1";
                            } else if (finalMonitorUrl.includes('/photos') || finalMonitorUrl.includes('sk=photos')) {
                                secretCommand = "auto_photos=1";
                            }
                        }
                        
                        if (secretCommand !== "") {
                            let rootUrl = finalMonitorUrl.split('/photos_by')[0].split('/photos')[0].split(/[\?&]sk=photos/)[0];
                            if (rootUrl.endsWith('/')) rootUrl = rootUrl.slice(0, -1);
                            finalMonitorUrl = rootUrl + (rootUrl.includes('?') ? '&' : '?') + secretCommand;
                        }

                        chrome.storage.local.set({
                            monitoring_active: true,
                            monitor_message: data.message,
                            monitor_limit: data.limit,
                            monitor_mode: data.mode,
                            monitor_url: finalMonitorUrl,
                            last_seen_items: [] 
                        }, () => {
                            chrome.tabs.query({ url: ["*://*.facebook.com/*"] }, function(tabs) {
                                let targetTab = tabs.find(t => !t.url.includes("messenger.com") && !t.url.includes("messages"));
                                if (targetTab) {
                                    // active:true = แท็บเฝ้าดูต้องไม่ถูกซ่อน ไม่งั้น timer โดนหน่วงเหมือนกัน
                                    chrome.tabs.update(targetTab.id, { url: finalMonitorUrl, active: true });
                                } else {
                                    chrome.tabs.create({ url: finalMonitorUrl, active: true });
                                }
                                markTaskAsDone(uniqueId, data.task_id);
                            });
                        });
                    } 
                    // 🛑 ปิดระบบ Monitor (สวิตช์ปิด)
                    else if (data.action_type === "stop_auto_monitor") {
                        console.log("🛑 ได้รับคำสั่งหยุด Auto Monitor");
                        chrome.storage.local.set({ monitoring_active: false }, () => {
                            markTaskAsDone(uniqueId, data.task_id);
                        });
                    }

                    if (data.action_type === "setup") {
                        // ปิด Monitor เผื่อค้างไว้
                        chrome.storage.local.set({ monitoring_active: false });

                        let urlsToOpen = [];
                        if ((data.mode === "messenger" || data.mode === "all") && data.url_messenger) urlsToOpen.push(data.url_messenger);
                        if ((data.mode === "live" || data.mode === "all") && data.url_live) urlsToOpen.push(data.url_live);
                        // ไลค์/แชร์ ใช้ช่อง URL โพสต์ช่องเดียวกับคอมเมนต์โพสต์
                        if ((data.mode === "like" || data.mode === "share") && data.url_post) urlsToOpen.push(data.url_post);

                        if ((data.mode === "post" || data.mode === "all") && data.url_post) {
                            let postUrl = data.url_post;
                            let secretCommand = "";

                            if (postUrl.includes('/photos_by') || postUrl.includes('sk=photos_by')) {
                                secretCommand = "auto_photos_by=1";
                            } else if (postUrl.includes('/photos') || postUrl.includes('sk=photos')) {
                                secretCommand = "auto_photos=1";
                            }

                            if (secretCommand !== "") {
                                let rootUrl = postUrl.split('/photos_by')[0].split('/photos')[0].split(/[\?&]sk=photos/)[0];
                                if (rootUrl.endsWith('/')) rootUrl = rootUrl.slice(0, -1);
                                postUrl = rootUrl + (rootUrl.includes('?') ? '&' : '?') + secretCommand;
                            }
                            urlsToOpen.push(postUrl);
                        }

                        if (urlsToOpen.length === 0) return;

                        chrome.tabs.query({ url: ["*://*.facebook.com/*", "*://*.messenger.com/*"] }, function(tabs) {
                            urlsToOpen.forEach((url, index) => {
                                if (tabs[index]) {
                                    chrome.tabs.update(tabs[index].id, { url: url, active: true });
                                } else {
                                    chrome.tabs.create({ url: url, active: true });
                                }
                            });
                            markTaskAsDone(uniqueId, data.task_id);
                        });
                    }

                    else if (data.action_type === "send") {
                        chrome.storage.local.set({ monitoring_active: false }); // ปิด Monitor เมื่อกดส่งเอง

                        chrome.tabs.query({ url: ["*://*.facebook.com/*", "*://*.messenger.com/*"] }, async function(tabs) {
                            if (tabs.length === 0) return;
                            markTaskAsDone(uniqueId, data.task_id);

                            for (const tab of tabs) {
                                let tabMode = "messenger";
                                const isChatTab = tab.url.includes("messenger.com") || tab.url.includes("messages");
                                if (data.mode === "like" || data.mode === "share") {
                                    // ไลค์/แชร์ ทำบนหน้าโพสต์เท่านั้น ข้ามแท็บแชท
                                    if (isChatTab) continue;
                                    tabMode = data.mode;
                                } else if (tab.url.includes("videos") || tab.url.includes("watch") || tab.url.includes("live")) {
                                    tabMode = "live";
                                } else if (data.mode === "post" || data.mode === "all") {
                                    if (!isChatTab) tabMode = "post";
                                }

                                if (data.mode !== "all" && data.mode !== tabMode) continue;

                                // ponytail: แท็บที่ถูกซ่อน (ไม่ใช่แท็บที่เลือกอยู่ในหน้าต่างนั้น) โดน Chrome
                                // หน่วง timer เหลือ 1 ครั้ง/วินาที ลูป retry ในหน้าเว็บเลยค้างจนคนไปคลิกแท็บเอง
                                // สั่งเลือกแท็บให้เองก่อนส่ง = แทนการคลิกจอ (ทีละแท็บ ไม่แย่งกัน)
                                // ไม่สั่ง windows.update({focused}) เพราะเปิดพร้อมกันหลายโปรไฟล์
                                // โฟกัสได้หน้าต่างเดียว ที่เหลือจะพัง + แย่งจอคนใช้
                                await chrome.tabs.update(tab.id, { active: true }).catch(() => {});
                                await new Promise(r => setTimeout(r, 150));
                                // ponytail: กันแท็บเดียวค้างแล้วบล็อกแท็บที่เหลือ เผื่อเวลาตามจำนวนครั้งที่ส่ง
                                // ไลค์/แชร์ ทำครั้งเดียวจบ ไม่ใช้ limit (ค่าค้างจากโหมดก่อนหน้าอาจเป็น 1000)
                                const budgetMs = (tabMode === "like" || tabMode === "share")
                                    ? 30000
                                    : (Number(data.limit) || 1) * 1500 + 30000;
                                await Promise.race([
                                    chrome.tabs.sendMessage(tab.id, {
                                        action: "runBot",
                                        task: { ...data, mode: tabMode },
                                        profileId: uniqueId
                                    }).catch(() => {}),
                                    new Promise(r => setTimeout(r, budgetMs))
                                ]);
                            }
                        });
                    }
                }
            })
            .catch(err => {});
    });
}

function markTaskAsDone(uniqueId, taskId) {
    fetch(`http://localhost:5000/api/mark-done/${uniqueId}/${taskId}`).catch(err => {});
}

fetchTaskFromServer();
setInterval(fetchTaskFromServer, 1000);