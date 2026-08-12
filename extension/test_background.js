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
function runOnce(task, tabs, opts = {}) {
    const log = [];
    const reports = [];
    let served = false;
    let sends = 0;
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
                sendMessage: async (id, msg) => {
                    log.push(`sendMessage:${id}:${msg.task.mode}`);
                    sends++;
                    if (opts.sendMessage) return opts.sendMessage(sends, id);
                    return { status: 'success' };
                },
            },
            scripting: {
                executeScript: async (o) => {
                    log.push(`inject:${o.target.tabId}:${o.files.join(',')}`);
                    if (opts.injectFails) throw new Error('ยัดไม่ได้');
                    return [{}];
                },
            },
            windows: {
                update: async (id, props) => { log.push(`windows.update:${id}`); },
            },
            runtime: {
                onMessage: { addListener: () => {} },
                getManifest: () => ({ version: '1.6.3' }),
            },
        },
        fetch: async (url, init) => {
            if (url.includes('/api/report/')) {
                reports.push(JSON.parse(init.body));
                return { json: async () => ({}) };
            }
            if (url.includes('/api/get-task/')) {
                assert.ok(url.includes('v=1.6.3'), 'ต้องบอกเวอร์ชันส่วนขยายไปด้วย: ' + url);
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
    log.reports = reports;
    return log;
}

const BASE = { action_type: 'send', message: 'ทักครับ', limit: 1,
               url_messenger: '', url_live: '', url_post: '' };
const POST_TAB = { id: 7, windowId: 3, url: 'https://www.facebook.com/somepage/posts/123' };
const CHAT_TAB = { id: 9, windowId: 3, url: 'https://www.messenger.com/t/abc' };

const NO_SCRIPT = new Error('Could not establish connection. Receiving end does not exist.');

const results = {};
results.messenger = runOnce(Object.assign({ mode: 'messenger' }, BASE), [CHAT_TAB]);
results.like = runOnce(Object.assign({ mode: 'like' }, BASE), [POST_TAB, CHAT_TAB]);
results.share = runOnce(Object.assign({ mode: 'share' }, BASE), [POST_TAB, CHAT_TAB]);

// แท็บที่เปิดค้างไว้ก่อนติดตั้งส่วนขยาย = ไม่มี content.js อยู่ ต้องยิงใส่แล้วลองใหม่
results.orphan = runOnce(Object.assign({ mode: 'messenger' }, BASE), [CHAT_TAB],
    { sendMessage: n => { if (n === 1) throw NO_SCRIPT; return { status: 'success' }; } });

// ยิงแล้วยังคุยไม่ได้ ต้องรายงานกลับ ไม่ใช่เงียบ
results.dead = runOnce(Object.assign({ mode: 'messenger' }, BASE), [CHAT_TAB],
    { sendMessage: () => { throw NO_SCRIPT; } });

// content.js บอกว่าพัง (เช่น ยังไม่ได้พิมพ์ข้อความ) ต้องส่งข้อความนั้นกลับโปรแกรม
results.errored = runOnce(Object.assign({ mode: 'messenger' }, BASE), [CHAT_TAB],
    { sendMessage: () => ({ status: 'error', error: 'ยังไม่ได้พิมพ์ข้อความที่จะส่ง' }) });

// ไม่มีแท็บ Facebook เปิดเลย เดิมเงียบสนิท
results.notab = runOnce(Object.assign({ mode: 'messenger' }, BASE), []);

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

    // ใหม่: ทุกครั้งที่สั่งงานต้องรายงานผลจริงกลับโปรแกรม
    const statusOf = r => (r.reports[0] || { results: [] }).results.map(x => x.status).join(' | ');

    assert.strictEqual(statusOf(results.messenger), '✅ สั่งงานแล้ว',
        'สำเร็จต้องรายงานว่าสำเร็จ: ' + statusOf(results.messenger));

    assert.ok(results.orphan.includes('inject:9:content.js'),
        'แท็บที่ไม่มี content.js ต้องยิงสคริปต์ใส่: ' + results.orphan.join(' | '));
    assert.strictEqual(statusOf(results.orphan), '✅ สั่งงานแล้ว',
        'ยิงสคริปต์แล้วต้องส่งงานต่อได้: ' + statusOf(results.orphan));

    assert.ok(/ส่วนขยายเข้าไม่ถึงหน้านี้/.test(statusOf(results.dead)),
        'ยิงแล้วยังคุยไม่ได้ ต้องบอกให้รีเฟรชหน้า: ' + statusOf(results.dead));

    assert.strictEqual(statusOf(results.errored), '❌ ยังไม่ได้พิมพ์ข้อความที่จะส่ง',
        'error จาก content.js ต้องถึงโปรแกรม: ' + statusOf(results.errored));

    assert.strictEqual(statusOf(results.notab), 'ไม่มีแท็บ Facebook เปิดอยู่',
        'ไม่มีแท็บต้องบอก ไม่ใช่เงียบ: ' + statusOf(results.notab));

    console.log('OK', JSON.stringify(results, null, 1));
    process.exit(0); // ตัด timer เผื่อเวลาที่ยังค้างอยู่ ไม่งั้น node ไม่ยอมจบ
}, 1500);
