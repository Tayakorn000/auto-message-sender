// เช็คว่า background.js สั่งโฟกัสหน้าต่าง + เลือกแท็บ ก่อนสั่ง runBot เสมอ
// (ถ้าไม่สั่ง แท็บที่ถูกบังจะโดน Chrome หน่วง timer แล้วบอทค้างรอคนคลิกจอ)
// และเช็คว่าโหมดไลค์/แชร์ ยิงเฉพาะแท็บโพสต์ ไม่ยิงแท็บแชท
// รัน: node test_background.js
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const SRC = fs.readFileSync(__dirname + '/background.js', 'utf8')
    .replace(/setInterval\([^)]*\);?/, ''); // ห้าม poll ค้างตอนเทส

// รันหนึ่งรอบด้วย task ที่กำหนด แล้วคืน log ที่เกิดขึ้น
function runOnce(task, tabs) {
    const log = [];
    let served = false;
    const ctx = {
        console,
        setTimeout, clearTimeout, setInterval, Promise, Number, Math, JSON,
        chrome: {
            storage: { local: {
                get: (keys, cb) => cb({ preset_group: 'profile_1', unique_id: 'uid_test' }),
                set: (obj, cb) => cb && cb(),
            }},
            tabs: {
                query: (q, cb) => cb(tabs),
                update: async (id, props) => { log.push(`tabs.update:${id}:${JSON.stringify(props)}`); },
                create: async () => {},
                sendMessage: async (id, msg) => { log.push(`sendMessage:${id}:${msg.task.mode}`); },
            },
            windows: {
                update: async (id, props) => { log.push(`windows.update:${id}`); },
            },
            runtime: {
                onMessage: { addListener: () => {} },
                getManifest: () => ({ version: '1.6.0' }),
            },
        },
        fetch: async (url) => {
            if (url.includes('/api/get-task/')) {
                assert.ok(url.includes('v=1.6.0'), 'ต้องบอกเวอร์ชันส่วนขยายไปด้วย: ' + url);
                const body = served ? { status: 'no_task' }
                                    : Object.assign({ status: 'has_task', task_id: 1 }, task);
                served = true;
                return { json: async () => body };
            }
            log.push('markDone');
            return { json: async () => ({}) };
        },
    };
    vm.createContext(ctx);
    vm.runInContext(SRC, ctx);
    return log;
}

const BASE = { action_type: 'send', message: 'ทักครับ', limit: 1,
               url_messenger: '', url_live: '', url_post: '' };
const POST_TAB = { id: 7, windowId: 3, url: 'https://www.facebook.com/somepage/posts/123' };
const CHAT_TAB = { id: 9, windowId: 3, url: 'https://www.messenger.com/t/abc' };

const results = {};
results.messenger = runOnce(Object.assign({ mode: 'messenger' }, BASE), [CHAT_TAB]);
results.like = runOnce(Object.assign({ mode: 'like' }, BASE), [POST_TAB, CHAT_TAB]);
results.share = runOnce(Object.assign({ mode: 'share' }, BASE), [POST_TAB, CHAT_TAB]);

setTimeout(() => {
    // เดิม: ต้องเลือกแท็บก่อนสั่ง runBot และห้ามโฟกัสหน้าต่าง
    const log = results.messenger;
    const iActive = log.findIndex(l => l.includes('"active":true'));
    const iSend = log.findIndex(l => l.startsWith('sendMessage:'));
    assert.ok(iActive >= 0, 'ต้องสั่งเลือกแท็บ (active:true) ก่อนส่ง: ' + log.join(' | '));
    assert.ok(iSend >= 0, 'ต้องส่ง runBot: ' + log.join(' | '));
    assert.ok(iActive < iSend, 'ลำดับผิด ต้องเลือกแท็บก่อน runBot: ' + log.join(' | '));
    assert.ok(!log.some(l => l.startsWith('windows.update')),
        'ห้ามสั่งโฟกัสหน้าต่าง จะแย่งจอคนใช้ + หลายโปรไฟล์โฟกัสพร้อมกันไม่ได้: ' + log.join(' | '));

    // ใหม่: ไลค์/แชร์ ยิงเฉพาะแท็บโพสต์ ไม่ยิงแท็บแชท
    for (const mode of ['like', 'share']) {
        const sends = results[mode].filter(l => l.startsWith('sendMessage:'));
        assert.deepStrictEqual(sends, [`sendMessage:7:${mode}`],
            `โหมด ${mode} ควรยิงแท็บโพสต์อย่างเดียว ได้ ${JSON.stringify(results[mode])}`);
    }

    console.log('OK', JSON.stringify(results, null, 1));
    process.exit(0); // ตัด timer เผื่อเวลาที่ยังค้างอยู่ ไม่งั้น node ไม่ยอมจบ
}, 1500);
