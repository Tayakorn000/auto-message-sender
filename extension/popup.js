document.addEventListener('DOMContentLoaded', () => {
    const select = document.getElementById('presetGroup');
    const saveBtn = document.getElementById('saveBtn');

    // โหลดค่าเดิมที่เคยตั้งไว้มาแสดงผล
    chrome.storage.local.get(['preset_group'], function(result) {
        if (result.preset_group) {
            select.value = result.preset_group;
        }
    });

    // บันทึกการตั้งค่าทั้งหมด
    saveBtn.addEventListener('click', () => {
        chrome.storage.local.set({ 
            'preset_group': select.value
        }, function() {
            alert(`บันทึกสำเร็จ!\n\nบอทจอนี้จะรับคำสั่งจาก: ${select.options[select.selectedIndex].text}`);
        });
    });
});