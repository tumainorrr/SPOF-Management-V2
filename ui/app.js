let mainChart = null, donutChart = null;
let fullScanData = [];
let filteredData = [];
let currentPage = 1;
const pageSize = 100;
let currentSort = { key: null, asc: true };
let compareChart = null; // เก็บตัวแปรเครื่องหมายกราฟไว้ข้างนอก
let afterChart = null;
let afterChartInstance = null; // เก็บตัวแปรไว้เพื่อเคลียร์กราฟเก่าก่อนวาดใหม่
let rawDeleteData = [];      // เก็บข้อมูลทั้งหมดจากไฟล์
let filteredDeleteData = []; // เก็บข้อมูลหลังจาก Search
let currentDelPage = 1;
const delPageSize = 100;    // กำหนด 100 แถวต่อหน้า
// เก็บสถานะการเรียงลำดับปัจจุบัน
let currentSortCol = '';
let isAsc = true
let myPolicyChart = null; // ตัวแปรเก็บ Instance ของกราฟ

// 1. เริ่มต้นโปรแกรม
const DEFAULT_SYNC_BUTTON_TEXT = "REFRESH & SYNC NEW DATA";
let syncQueuePollTimer = null;
let actionCenterSettings = null;
let actionCenterRawRows = [];
let actionCenterFilteredRows = [];
let actionCenterCurrentPage = 1;
const actionCenterPageSize = 100;
let actionCenterSort = { key: null, asc: true };
let actionCenterDuplicateDetectionAvailable = true;
let actionCenterResetConfirmResolver = null;

window.onload = function () {
    const check = () => {
        if (window.pywebview && window.pywebview.api) init();
        else setTimeout(check, 100);
    };
    check();
};

// รอให้ Pywebview พร้อมก่อนเริ่มทำงาน (สำคัญมากสำหรับ .exe)
window.addEventListener('pywebviewready', function () {
    console.log("Pywebview API is ready");
    init();
});

async function init() {
    switchTab('main');
    await loadMainData();
    await loadActionCenterSettings();
    await refreshSyncQueueStatus();
    setTimeout(() => refreshSyncQueueStatus(), 300);
    startSyncQueuePolling();

    try {
        const files = await pywebview.api.list_scan_files();
        window.scanFiles = files;
        updateFileList();

        // จุดที่ต้องเพิ่มตามโค้ดเดิมของคุณ
        if (typeof updateCompareList === 'function') {
            await updateCompareList();
        }

        const beforeSelect = document.getElementById('file-before');
        const afterSelect = document.getElementById('file-after');

        if (beforeSelect && afterSelect && files) {
            beforeSelect.innerHTML = files.Previous_Scan_Detail.map(f => `<option value="${f}">${f}</option>`).join('');
            afterSelect.innerHTML = files.ScanSizeAfterDelete.map(f => `<option value="${f}">${f}</option>`).join('');
        }
    } catch (err) {
        console.error("Init Error:", err);
    }
}

function updateSyncButtonState({
    has_pending = false,
    pending_count = 0,
    latest_file = null,
    watched_path = ""
} = {}) {
    const btn = document.getElementById('sync-btn');
    const btnText = document.getElementById('sync-btn-text');
    const badge = document.getElementById('sync-badge');
    const statusEl = document.getElementById('sync-status');
    const savedTime = localStorage.getItem('last_sync');

    if (!btn || !btnText || !badge || !statusEl) return;

    btn.classList.remove('bg-emerald-500', 'hover:bg-emerald-600', 'bg-amber-500', 'hover:bg-amber-600');

    if (has_pending) {
        btn.classList.add('bg-amber-500', 'hover:bg-amber-600');
        btnText.innerText = "SYNC NEW DATA READY";
        badge.innerText = pending_count;
        badge.classList.remove('hidden');
        badge.classList.add('inline-flex');
        statusEl.innerText = latest_file
            ? `Pending ${pending_count} file(s): ${latest_file}`
            : `Pending ${pending_count} file(s) waiting to sync`;
        return;
    }

    btn.classList.add('bg-emerald-500', 'hover:bg-emerald-600');
    btnText.innerText = DEFAULT_SYNC_BUTTON_TEXT;
    badge.classList.add('hidden');
    badge.classList.remove('inline-flex');
    statusEl.innerText = savedTime || `No new files waiting in Initial_Receive${watched_path ? ` | ${watched_path}` : ""}`;
}

async function refreshSyncQueueStatus() {
    try {
        const queueStatus = await window.pywebview.api.get_sync_queue_status();
        if (queueStatus && queueStatus.status === "success") {
            console.log("Sync queue status:", queueStatus);
            updateSyncButtonState(queueStatus);
        } else if (queueStatus && queueStatus.status === "error") {
            const statusEl = document.getElementById('sync-status');
            if (statusEl) {
                statusEl.innerText = `Queue check error: ${queueStatus.message}`;
            }
        }
    } catch (error) {
        console.error("Failed to refresh sync queue status:", error);
        const statusEl = document.getElementById('sync-status');
        if (statusEl) {
            statusEl.innerText = `Queue check error: ${error.message || error}`;
        }
    }
}

function startSyncQueuePolling() {
    if (syncQueuePollTimer) return;

    syncQueuePollTimer = setInterval(() => {
        refreshSyncQueueStatus();
    }, 2000);
}
// 2. ฟังก์ชันโหลดข้อมูลหน้า Dashboard หลัก
async function loadMainData() {
    console.log("Fetching Main Data...");
    try {
        const data = await window.pywebview.api.get_main_dashboard_data();

        if (!data || data.error) {
            console.error("Error:", data ? data.error : "No Data");
            // แจ้งเตือนบนหน้าตารางถ้าหาไฟล์ไม่เจอ
            const tableBody = document.getElementById('main-table');
            if (tableBody) tableBody.innerHTML = `<tr><td colspan="3" class="p-4 text-center text-red-500">⚠️ ${data ? data.error : 'ไม่สามารถโหลดข้อมูลได้'}</td></tr>`;
            return;
        }

        // --- คง Logic การคำนวณเดิม 100% ---
        const valid = data.filter(r => r['Library Name'] && !r['Library Name'].includes('TOTAL'))
            .map(r => ({
                name: r['Library Name'],
                size: parseFloat(r['Size (GB)']) || 0,
                items: parseInt(r['Total Items']) || 0
            }))
            .sort((a, b) => b.size - a.size);

        let totalS = 0;
        let totalI = 0;

        const tableBody = document.getElementById('main-table');
        tableBody.innerHTML = valid.map(r => {
            totalS += r.size;
            totalI += r.items;
            return `
                <tr class="hover:bg-indigo-50 transition-colors border-b border-slate-100">
                    <td class="p-4 font-bold text-slate-700">${r.name}</td>
                    <td class="p-4 text-center text-slate-500 font-medium">${r.items.toLocaleString()}</td>
                    <td class="p-4 text-right font-black text-indigo-600">${r.size.toFixed(2)}</td>
                </tr>
            `;
        }).join('');

        const quota = 900;
        const remaining = Math.max(0, quota - totalS);
        const usagePercent = ((totalS / quota) * 100).toFixed(1);

        if (document.getElementById('main-size')) document.getElementById('main-size').innerText = totalS.toFixed(2);
        if (document.getElementById('main-items')) document.getElementById('main-items').innerText = totalI.toLocaleString();
        if (document.getElementById('usage-percent')) document.getElementById('usage-percent').innerText = usagePercent + '%';
        if (document.getElementById('main-remaining')) document.getElementById('main-remaining').innerText = remaining.toFixed(2);

        renderDashboardCharts(valid, totalS);

    } catch (error) {
        console.error("Failed to load main data:", error);
    }
}

// 3. ฟังก์ชันวาดกราฟ (ใช้ Chart.js)
function renderDashboardCharts(data, totalUsed) {
    // 1. Bar Chart - ปรับให้ Label ไม่อัดกันเกินไป
    const ctxBar = document.getElementById('mainChart').getContext('2d');
    if (mainChart) mainChart.destroy();
    mainChart = new Chart(ctxBar, {
        type: 'bar',
        data: {
            labels: data.slice(0, 10).map(d => d.name),
            datasets: [{
                label: 'Usage (GB)',
                data: data.slice(0, 10).map(d => d.size),
                backgroundColor: '#6366f1',
                borderRadius: 6
            }]
        },
        options: {
            maintainAspectRatio: false, // บังคับให้เต็มความสูง Container
            responsive: true,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: '#f1f5f9' },
                    ticks: { font: { size: 11 } } // ปรับขนาดตัวเลขแกน Y
                },
                x: {
                    grid: { display: false },
                    ticks: {
                        font: { size: 10 },
                        maxRotation: 45, // ป้องกันชื่อ Library ซ้อนกันถ้าชื่อยาว
                        minRotation: 45
                    }
                }
            },
            layout: { padding: { top: 10, bottom: 10 } }
        }
    });

    // 2. Donut Chart - ปรับให้วงกลมอยู่กึ่งกลางและมีพื้นที่หายใจ
    const ctxDonut = document.getElementById('donutChart').getContext('2d');
    if (donutChart) donutChart.destroy();
    donutChart = new Chart(ctxDonut, {
        type: 'doughnut',
        data: {
            labels: ['Used', 'Free'],
            datasets: [{
                data: [totalUsed, Math.max(0, 900 - totalUsed)],
                backgroundColor: ['#6366f1', '#f1f5f9'],
                borderWidth: 0,
                cutout: '75%' // ปรับให้วงบางลงนิดหน่อย จะดูทันสมัยกว่า
            }]
        },
        options: {
            maintainAspectRatio: false, // บังคับให้กราฟขยายเต็มพื้นที่ที่ HTML กำหนด
            responsive: true,
            plugins: {
                legend: {
                    display: true,
                    position: 'bottom', // ย้ายมาไว้ข้างล่างเพื่อไม่ให้เบียดตัววงกลม
                    labels: {
                        boxWidth: 12,
                        padding: 15,
                        font: { size: 12 }
                    }
                }
            },
            layout: {
                padding: 20 // เพิ่ม Padding รอบตัวโดนัท ไม่ให้ขอบวงกลมกระแทกขอบกล่อง
            }
        }
    });
}

// 4. ฟังก์ชันจัดการหน้า Analysis (Tab 2)
// ฟังก์ชันนี้จะทำงานทุกครั้งที่เปลี่ยน Category หรือสลับหน้ามาที่ Analysis
async function updateFileList() {
    const category = document.getElementById('cat-select').value;
    const fileSelect = document.getElementById('file-select');

    // 1. เก็บชื่อแผนกที่เลือกไว้ปัจจุบันก่อนจะล้างค่า
    const selectedDept = fileSelect.value;

    // แสดงสถานะว่ากำลังโหลด
    fileSelect.innerHTML = '<option value="">Loading Departments...</option>';

    try {
        const departments = await pywebview.api.get_available_departments(category);
        fileSelect.innerHTML = '';

        if (!departments || departments.length === 0) {
            fileSelect.innerHTML = '<option value="">No Departments Found</option>';
            return;
        }

        // 2. เพิ่ม Default Option เพื่อให้เกิด Event change ได้ง่ายขึ้น
        const defaultOpt = document.createElement('option');
        defaultOpt.value = "";
        defaultOpt.textContent = "-- Select Department --";
        fileSelect.appendChild(defaultOpt);

        // 3. สร้าง Option จากชื่อแผนก
        departments.forEach(dept => {
            const option = document.createElement('option');
            option.value = dept;
            option.textContent = `Department: ${dept}`;
            fileSelect.appendChild(option);
        });

        // 4. ตรวจสอบว่าแผนกเดิมที่เคยเลือกไว้ มีอยู่ใน Category ใหม่นี้หรือไม่
        const hasSameDept = departments.includes(selectedDept);

        if (selectedDept && hasSameDept) {
            // ถ้ามีแผนกเดิมอยู่ ให้เลือกอันเดิมคืนให้
            fileSelect.value = selectedDept;

            // สั่งโหลดข้อมูลของแผนกเดิมใน Category ใหม่ทันที
            loadScanDetail();
        } else {
            // ถ้าไม่มี (เช่น แผนกนี้ไม่มีไฟล์ใน Category อื่น) ให้เลือกตัวว่างไว้
            fileSelect.value = "";

            // ล้างข้อมูลหน้าจอเดิมทิ้ง (Optional: เพื่อไม่ให้ข้อมูลเก่าค้าง)
            fullScanData = [];
            filteredData = [];
            updateScanSummary([]);
            renderScanPage();
        }

    } catch (error) {
        console.error("Error updating departments:", error);
        fileSelect.innerHTML = '<option value="">Error connecting to Python</option>';
    }
}
function updateScanSummary(data) {
    let totalCurrentMB = 0;
    let totalVersions = 0;
    let totalSizeMB = 0;

    data.forEach(r => {
        totalCurrentMB += parseFloat(r['Current Size (MB)']) || 0;
        totalVersions += parseInt(r['Version Count']) || 0;
        totalSizeMB += parseFloat(r['Total Size (MB)']) || 0;
    });

    // คำนวณเป็น GB
    const currentGB = totalCurrentMB / 1024;
    const totalGB = totalSizeMB / 1024;

    // อัปเดตตัวเลขลงใน UI
    document.getElementById('sum-items').innerText = data.length.toLocaleString();

    // Current Size
    document.getElementById('sum-current-gb').innerText = currentGB.toFixed(2);
    document.getElementById('sum-current-mb').innerText = totalCurrentMB.toLocaleString(undefined, { minimumFractionDigits: 2 });

    // Versions
    document.getElementById('sum-versions').innerText = totalVersions.toLocaleString();

    // Total Size
    document.getElementById('sum-total-gb').innerText = totalGB.toFixed(2);
    document.getElementById('sum-total-mb').innerText = totalSizeMB.toLocaleString(undefined, { minimumFractionDigits: 2 });

    // แสดงแถบ Summary
    document.getElementById('scan-summary').classList.remove('hidden');
}

async function loadScanDetail() {
    const category = document.getElementById('cat-select').value;
    const deptName = document.getElementById('file-select').value;

    // ถ้ายังไม่ได้เลือกแผนก (ค่าว่าง) ให้หยุดทำงาน ไม่ต้องโชว์ Alert
    if (!deptName || deptName === "") return;

    try {
        // 1. ดึงข้อมูลจาก Python
        const data = await pywebview.api.get_latest_scan_data(category, deptName);

        if (!data || data.error) {
            console.error(data.error || "No data found");
            // อาจจะล้างตารางทิ้งถ้าหาข้อมูลไม่เจอ
            fullScanData = [];
            filteredData = [];
            renderScanPage();
            return;
        }

        // 2. อัปเดตตัวแปรส่วนกลาง
        fullScanData = data;
        filteredData = [...data];
        currentPage = 1;

        // 3. สั่งให้ฟังก์ชันเดิมๆ ทำงาน
        updateScanSummary(filteredData);
        renderScanPage();

    } catch (err) {
        console.error("Load Scan Detail Error:", err);
    }
}

function formatDisplayDateTime(value) {
    const raw = (value || '').toString().trim();
    if (!raw) return '-';

    const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/);
    if (match) {
        const [, yyyy, mm, dd, hh, mi, ss = '00'] = match;
        return `${dd}-${mm}-${yyyy} ${hh}:${mi}:${ss}`;
    }

    const parsed = new Date(raw);
    if (Number.isNaN(parsed.getTime())) return raw;

    const dd = String(parsed.getDate()).padStart(2, '0');
    const mm = String(parsed.getMonth() + 1).padStart(2, '0');
    const yyyy = parsed.getFullYear();
    const hh = String(parsed.getHours()).padStart(2, '0');
    const mi = String(parsed.getMinutes()).padStart(2, '0');
    const ss = String(parsed.getSeconds()).padStart(2, '0');
    return `${dd}-${mm}-${yyyy} ${hh}:${mi}:${ss}`;
}

function buildSharePointFolderUrl(folderPath) {
    const raw = (folderPath || '').toString().trim();
    if (!raw || raw === '-') return '-';
    if (/^https?:\/\//i.test(raw)) return raw;
    if (raw.startsWith('/')) return `https://accor.sharepoint.com${raw}`;
    return `https://accor.sharepoint.com/${raw}`;
}

function renderScanPage() {
    const totalPages = Math.ceil(filteredData.length / pageSize) || 1;
    const start = (currentPage - 1) * pageSize;
    const pageData = filteredData.slice(start, start + pageSize);

    // --- ส่วนวาดตาราง (เหมือนเดิม) ---
    document.getElementById('scan-table').innerHTML = pageData.map((r, idx) => `
        <tr class="hover:bg-slate-50 border-b border-slate-100 table-fixed w-full">
            <td class="p-3 text-center text-slate-400 font-mono">${start + idx + 1}</td>
            <td class="p-3 overflow-hidden">
                <div class="text-[9px] text-slate-400 truncate w-full" title="${buildSharePointFolderUrl(r['Folder Path'])}">${buildSharePointFolderUrl(r['Folder Path'])}</div>
                <div class="font-bold text-slate-700 text-[11px] truncate w-full" title="${r['File Name']}">${r['File Name'] || '-'}</div>
            </td>
            <td class="p-3 text-center font-bold text-slate-500">${r['Extension'] || '-'}</td>
            <td class="p-3 text-right font-mono">${parseFloat(r['Current Size (MB)'] || 0).toFixed(2)}</td>
            <td class="p-3 text-center text-emerald-600 font-bold">${r['Version Count'] || 0}</td>
            <td class="p-3 text-right font-bold text-slate-900 font-mono">${parseFloat(r['Total Size (MB)'] || 0).toFixed(2)}</td>
            <td class="p-3 text-left text-[10px] text-slate-600 font-mono">${formatDisplayDateTime(r['Last Datetime of Original Version'])}</td>
            <td class="p-3 text-left text-[10px] text-slate-600 font-mono">${formatDisplayDateTime(r['First Datetime of History Version'])}</td>
        </tr>
    `).join('');

    // --- แก้ไขจุดนี้: ใส่เลขหน้าปัจจุบันเข้าไปด้วย ---
    document.getElementById('scan-info').innerText = `FOUND: ${filteredData.length.toLocaleString()} ITEMS`;

    // อัปเดตเลขในช่อง Input และตัวเลขรวม
    document.getElementById('pageInput').value = currentPage;
    document.getElementById('page-indicator').innerText = `of ${totalPages}`;

    document.getElementById('prevBtn').disabled = currentPage === 1;
    document.getElementById('nextBtn').disabled = currentPage >= totalPages;
}

// 1. ฟังก์ชันดึงรายชื่อแผนกมาโชว์ในหน้า Comparison
async function loadActionCenterSettings() {
    try {
        const response = await pywebview.api.get_action_center_settings();
        if (!response || !response.success) {
            throw new Error(response && response.error ? response.error : "Unable to load action center settings.");
        }

        actionCenterSettings = response.settings || {};
        fillActionCenterSettingsForm();
    } catch (error) {
        console.error("loadActionCenterSettings error:", error);
    }
}

function openActionCenterSettingsModal() {
    fillActionCenterSettingsForm();
    const modal = document.getElementById('actionCenterSettingsModal');
    if (modal) modal.classList.remove('hidden');
}

function closeActionCenterSettingsModal() {
    const modal = document.getElementById('actionCenterSettingsModal');
    if (modal) modal.classList.add('hidden');
}

function handleActionCenterSettingsBackdrop(event) {
    if (event.target?.id === 'actionCenterSettingsModal') {
        closeActionCenterSettingsModal();
    }
}

function openActionCenterResetConfirmModal() {
    const modal = document.getElementById('actionCenterResetConfirmModal');
    if (modal) modal.classList.remove('hidden');
}

function closeActionCenterResetConfirmModal() {
    const modal = document.getElementById('actionCenterResetConfirmModal');
    if (modal) modal.classList.add('hidden');
}

function handleActionCenterResetConfirmBackdrop(event) {
    if (event.target?.id === 'actionCenterResetConfirmModal') {
        resolveActionCenterResetConfirm(false);
    }
}

function resolveActionCenterResetConfirm(confirmed) {
    closeActionCenterResetConfirmModal();
    if (actionCenterResetConfirmResolver) {
        actionCenterResetConfirmResolver(confirmed);
        actionCenterResetConfirmResolver = null;
    }
}

function requestActionCenterResetConfirmation() {
    return new Promise((resolve) => {
        actionCenterResetConfirmResolver = resolve;
        openActionCenterResetConfirmModal();
    });
}

function fillActionCenterSettingsForm() {
    if (!actionCenterSettings) return;

    const fields = {
        'ac-high-versions-mb': actionCenterSettings.high_versions_mb,
        'ac-high-min-mb': actionCenterSettings.high_min_mb,
        'ac-high-max-mb': actionCenterSettings.high_max_mb,
        'ac-high-age-years': actionCenterSettings.high_age_years,
        'ac-high-total-mb': actionCenterSettings.high_total_mb,
        'ac-medium-versions-mb': actionCenterSettings.medium_versions_mb,
        'ac-medium-min-mb': actionCenterSettings.medium_min_mb,
        'ac-medium-max-mb': actionCenterSettings.medium_max_mb,
        'ac-medium-age-years': actionCenterSettings.medium_age_years,
        'ac-medium-total-mb': actionCenterSettings.medium_total_mb,
        'ac-low-versions-mb': actionCenterSettings.low_versions_mb,
        'ac-low-min-mb': actionCenterSettings.low_min_mb,
        'ac-low-max-mb': actionCenterSettings.low_max_mb,
        'ac-low-age-years': actionCenterSettings.low_age_years,
        'ac-low-total-mb': actionCenterSettings.low_total_mb,
        'ac-very-low-versions-mb': actionCenterSettings.very_low_versions_mb,
        'ac-very-low-min-mb': actionCenterSettings.very_low_min_mb,
        'ac-very-low-max-mb': actionCenterSettings.very_low_max_mb,
        'ac-very-low-age-years': actionCenterSettings.very_low_age_years,
        'ac-very-low-total-mb': actionCenterSettings.very_low_total_mb,
        'ac-pdf-focus-items-limit': actionCenterSettings.pdf_focus_items_limit,
    };

    Object.entries(fields).forEach(([id, value]) => {
        const element = document.getElementById(id);
        if (!element) return;
        if (element.type === 'checkbox') {
            element.checked = !!value;
            return;
        }
        element.value = value ?? '';
    });

    const duplicateToggle = document.getElementById('ac-pdf-group-duplicates');
    if (duplicateToggle) duplicateToggle.checked = !!actionCenterSettings.pdf_group_duplicate_topics;
}

function readActionCenterSettingsFromForm() {
    const getNullableValue = (id) => {
        const raw = document.getElementById(id)?.value;
        if (raw === undefined || raw === null) return null;
        const text = raw.toString().trim();
        if (!text) return null;
        const parsed = parseFloat(text);
        return Number.isFinite(parsed) ? parsed : null;
    };
    const getIntValue = (id, fallback) => {
        const parsed = parseInt(document.getElementById(id)?.value || fallback, 10);
        return Number.isFinite(parsed) ? parsed : fallback;
    };

    return {
        high_versions_mb: getNullableValue('ac-high-versions-mb'),
        high_min_mb: getNullableValue('ac-high-min-mb'),
        high_max_mb: getNullableValue('ac-high-max-mb'),
        high_age_years: getNullableValue('ac-high-age-years'),
        high_total_mb: getNullableValue('ac-high-total-mb'),
        medium_versions_mb: getNullableValue('ac-medium-versions-mb'),
        medium_min_mb: getNullableValue('ac-medium-min-mb'),
        medium_max_mb: getNullableValue('ac-medium-max-mb'),
        medium_age_years: getNullableValue('ac-medium-age-years'),
        medium_total_mb: getNullableValue('ac-medium-total-mb'),
        low_versions_mb: getNullableValue('ac-low-versions-mb'),
        low_min_mb: getNullableValue('ac-low-min-mb'),
        low_max_mb: getNullableValue('ac-low-max-mb'),
        low_age_years: getNullableValue('ac-low-age-years'),
        low_total_mb: getNullableValue('ac-low-total-mb'),
        very_low_versions_mb: getNullableValue('ac-very-low-versions-mb'),
        very_low_min_mb: getNullableValue('ac-very-low-min-mb'),
        very_low_max_mb: getNullableValue('ac-very-low-max-mb'),
        very_low_age_years: getNullableValue('ac-very-low-age-years'),
        very_low_total_mb: getNullableValue('ac-very-low-total-mb'),
        pdf_focus_items_limit: getIntValue('ac-pdf-focus-items-limit', 12),
        pdf_group_duplicate_topics: !!document.getElementById('ac-pdf-group-duplicates')?.checked,
    };
}

async function saveActionCenterSettings(closeAfterSave = false) {
    try {
        const response = await pywebview.api.save_action_center_settings(readActionCenterSettingsFromForm());
        if (!response || !response.success) {
            throw new Error(response && response.error ? response.error : "Unable to save settings.");
        }

        actionCenterSettings = response.settings || readActionCenterSettingsFromForm();
        fillActionCenterSettingsForm();
        if (actionCenterRawRows.length > 0) applyActionCenterFilters();
        if (closeAfterSave) {
            closeActionCenterSettingsModal();
        }
        alert("Action Center settings saved.");
    } catch (error) {
        console.error("saveActionCenterSettings error:", error);
        alert("Unable to save Action Center settings.");
    }
}

async function resetActionCenterSettings() {
    try {
        const confirmed = await requestActionCenterResetConfirmation();
        if (!confirmed) return;

        const response = await pywebview.api.reset_action_center_settings();
        if (!response || !response.success) {
            throw new Error(response && response.error ? response.error : "Unable to reset settings.");
        }

        actionCenterSettings = response.settings || {};
        fillActionCenterSettingsForm();
        if (actionCenterRawRows.length > 0) applyActionCenterFilters();
        alert("Action Center settings reset to default.");
    } catch (error) {
        console.error("resetActionCenterSettings error:", error);
        alert("Unable to reset Action Center settings.");
    }
}

async function updateActionCenterFileList() {
    const category = document.getElementById('action-cat-select')?.value || 'Current_Scan_Detail';
    const select = document.getElementById('action-file-select');
    if (!select) return;

    const previousValue = select.value;
    select.innerHTML = '<option value="">Loading Departments...</option>';

    try {
        const departments = await pywebview.api.get_available_departments(category);
        select.innerHTML = '<option value="">-- Select Department --</option>';

        (departments || []).forEach((dept) => {
            const option = document.createElement('option');
            option.value = dept;
            option.textContent = `Department: ${dept}`;
            select.appendChild(option);
        });

        if (previousValue && departments.includes(previousValue)) {
            select.value = previousValue;
            await loadActionCenterData();
        } else if (departments && departments.length > 0) {
            select.value = departments[0];
            await loadActionCenterData();
        } else {
            resetActionCenterData();
        }
    } catch (error) {
        console.error("updateActionCenterFileList error:", error);
        select.innerHTML = '<option value="">Error loading departments</option>';
    }
}

function resetActionCenterData() {
    actionCenterRawRows = [];
    actionCenterFilteredRows = [];
    actionCenterCurrentPage = 1;
    renderActionCenterSummary([]);
    renderActionCenterTable();
}

async function loadActionCenterData() {
    const category = document.getElementById('action-cat-select')?.value || 'Current_Scan_Detail';
    const deptName = document.getElementById('action-file-select')?.value || '';

    if (!deptName) {
        resetActionCenterData();
        return;
    }

    try {
        const data = await pywebview.api.get_latest_scan_data(category, deptName);
        if (!data || data.error) {
            throw new Error(data && data.error ? data.error : "Unable to load scan detail.");
        }

        actionCenterRawRows = data;
        actionCenterCurrentPage = 1;
        applyActionCenterFilters();
    } catch (error) {
        console.error("loadActionCenterData error:", error);
        resetActionCenterData();
        alert("Unable to load Action Center data.");
    }
}

function parseActionCenterNumber(value) {
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : 0;
}

function parseOptionalActionCenterNumber(value) {
    if (value === undefined || value === null) return null;
    const text = value.toString().trim();
    if (!text) return null;
    const parsed = parseFloat(text);
    return Number.isFinite(parsed) ? parsed : null;
}

function buildActionCenterPriorityConfig(settings, prefix) {
    return {
        versionsMB: parseOptionalActionCenterNumber(settings[`${prefix}_versions_mb`]),
        minMB: parseOptionalActionCenterNumber(settings[`${prefix}_min_mb`]),
        maxMB: parseOptionalActionCenterNumber(settings[`${prefix}_max_mb`]),
        ageYears: parseOptionalActionCenterNumber(settings[`${prefix}_age_years`]),
        totalMB: parseOptionalActionCenterNumber(settings[`${prefix}_total_mb`]),
    };
}

function buildActionCenterRangeReason(minMB, maxMB) {
    if (minMB !== null && maxMB !== null) {
        return `Total Size between ${minMB} MB and ${maxMB} MB`;
    }
    if (minMB !== null) {
        return `Total Size >= ${minMB} MB`;
    }
    if (maxMB !== null) {
        return `Total Size <= ${maxMB} MB`;
    }
    return '';
}

function evaluateActionCenterPriorityAny(totalMB, versionsMB, ageYears, config) {
    const reasons = [];
    const rangeEnabled = config.minMB !== null || config.maxMB !== null;
    const matchesRange = (!rangeEnabled)
        ? false
        : (config.minMB === null || totalMB >= config.minMB) && (config.maxMB === null || totalMB <= config.maxMB);

    if (config.totalMB !== null && totalMB > config.totalMB) {
        reasons.push(`Total Size > ${config.totalMB} MB`);
    }
    if (config.versionsMB !== null && versionsMB > config.versionsMB) {
        reasons.push(`Versions Size > ${config.versionsMB} MB`);
    }
    if (config.ageYears !== null && ageYears !== null && ageYears >= config.ageYears) {
        reasons.push(`Last Original older than ${config.ageYears} years`);
    }
    if (matchesRange) {
        reasons.push(buildActionCenterRangeReason(config.minMB, config.maxMB));
    }

    return reasons;
}

function evaluateActionCenterPriorityAll(totalMB, versionsMB, ageYears, config) {
    const checks = [];
    const rangeEnabled = config.minMB !== null || config.maxMB !== null;
    const rangeMatched = (!rangeEnabled)
        ? false
        : (config.minMB === null || totalMB >= config.minMB) && (config.maxMB === null || totalMB <= config.maxMB);

    if (config.totalMB !== null) {
        checks.push({
            matched: totalMB > config.totalMB,
            label: `Total Size > ${config.totalMB} MB`,
        });
    }
    if (config.versionsMB !== null) {
        checks.push({
            matched: versionsMB > config.versionsMB,
            label: `Versions Size > ${config.versionsMB} MB`,
        });
    }
    if (config.ageYears !== null) {
        checks.push({
            matched: ageYears !== null && ageYears >= config.ageYears,
            label: `Last Original older than ${config.ageYears} years`,
        });
    }
    if (rangeEnabled) {
        checks.push({
            matched: rangeMatched,
            label: buildActionCenterRangeReason(config.minMB, config.maxMB),
        });
    }

    if (!checks.length || !checks.every((check) => check.matched)) {
        return [];
    }
    return checks.map((check) => check.label);
}

function parseActionCenterDate(value) {
    const raw = (value || '').toString().trim();
    if (!raw || raw === '-') return null;

    let match = raw.match(/^(\d{2})-(\d{2})-(\d{4})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/);
    if (match) {
        const [, dd, mm, yyyy, hh, mi, ss = '00'] = match;
        return new Date(`${yyyy}-${mm}-${dd}T${hh}:${mi}:${ss}`);
    }

    match = raw.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/);
    if (match) {
        const [, yyyy, mm, dd, hh, mi, ss = '00'] = match;
        return new Date(`${yyyy}-${mm}-${dd}T${hh}:${mi}:${ss}`);
    }

    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function calculateActionCenterAgeYears(value) {
    const date = parseActionCenterDate(value);
    if (!date) return null;

    const diffMs = Date.now() - date.getTime();
    return diffMs > 0 ? diffMs / (365.25 * 24 * 60 * 60 * 1000) : 0;
}

function normalizeDuplicateText(value) {
    return (value || '').toString().trim().toLowerCase();
}

function hasHighConfidenceDuplicateMetadata(rows) {
    const sampleRow = (rows || []).find((row) => row && typeof row === 'object');
    if (!sampleRow) return false;

    return [
        'Last Datetime of Original Version',
        'First Datetime of History Version',
    ].every((key) => Object.prototype.hasOwnProperty.call(sampleRow, key));
}

function normalizeDuplicateDateKey(value) {
    const date = parseActionCenterDate(value);
    if (!date) return '-';
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    const dd = String(date.getDate()).padStart(2, '0');
    const hh = String(date.getHours()).padStart(2, '0');
    const mi = String(date.getMinutes()).padStart(2, '0');
    const ss = String(date.getSeconds()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
}

function buildHighConfidenceDuplicateSignature(row) {
    return [
        normalizeDuplicateText(row['File Name']),
        normalizeDuplicateText(row['Extension']),
        parseActionCenterNumber(row['Current Size (MB)']).toFixed(3),
        parseActionCenterNumber(row['Versions Size (MB)']).toFixed(3),
        parseActionCenterNumber(row['Total Size (MB)']).toFixed(3),
        String(parseInt(row['Version Count'] || 0, 10) || 0),
        normalizeDuplicateDateKey(row['Last Datetime of Original Version']),
        normalizeDuplicateDateKey(row['First Datetime of History Version']),
    ].join('|');
}

function buildDuplicateIdentityKey(row) {
    return [
        normalizeDuplicateText(row['Folder Path']),
        normalizeDuplicateText(row['File Name']),
    ].join('|');
}

function getActionCenterPriorityColor(priority) {
    const colorMap = {
        'High': 'bg-rose-100 text-rose-700',
        'Medium': 'bg-amber-100 text-amber-700',
        'Low': 'bg-sky-100 text-sky-700',
        'Very Low': 'bg-slate-200 text-slate-700',
        'Info': 'bg-emerald-100 text-emerald-700',
    };
    return colorMap[priority] || colorMap.Info;
}

function getActionCenterSortValue(row, key) {
    if (key === 'File Details') {
        return `${row['Folder Path'] || ''} ${row['File Name'] || ''}`.toLowerCase();
    }
    if (key === 'Ext') {
        return (row['Extension'] || '').toString().toLowerCase();
    }
    if (key === 'Versions MB') {
        return parseActionCenterNumber(row['Versions Size (MB)']);
    }
    if (key === 'Total MB') {
        return parseActionCenterNumber(row['Total Size (MB)']);
    }
    if (key === 'Age') {
        const age = parseFloat(row['Age (Years)']);
        return Number.isFinite(age) ? age : -1;
    }
    if (key === 'Duplicate') {
        return (row['Duplicate Candidate'] || '').toString().toLowerCase();
    }
    if (key === 'Count') {
        return parseInt(row['Duplicate Count'] || 0, 10) || 0;
    }
    if (key === 'Priority') {
        const priorityOrder = { High: 4, Medium: 3, Low: 2, 'Very Low': 1, Info: 0 };
        return priorityOrder[row['Priority']] ?? -1;
    }
    if (key === 'Recommended Action') {
        return (row['Recommended Action'] || '').toString().toLowerCase();
    }
    if (key === 'Last Original') {
        const date = parseActionCenterDate(row['Last Datetime of Original Version']);
        return date ? date.getTime() : 0;
    }
    if (key === 'Reason') {
        return (row['Reason'] || '').toString().toLowerCase();
    }
    return (row[key] || '').toString().toLowerCase();
}

function sortActionCenterBy(key) {
    if (actionCenterSort.key === key) {
        actionCenterSort.asc = !actionCenterSort.asc;
    } else {
        actionCenterSort.key = key;
        actionCenterSort.asc = true;
    }

    actionCenterCurrentPage = 1;
    applyActionCenterFilters();
}

function sortActionCenterRows(rows) {
    if (!actionCenterSort.key) return rows;

    rows.sort((a, b) => {
        const valueA = getActionCenterSortValue(a, actionCenterSort.key);
        const valueB = getActionCenterSortValue(b, actionCenterSort.key);

        if (typeof valueA === 'number' && typeof valueB === 'number') {
            return actionCenterSort.asc ? valueA - valueB : valueB - valueA;
        }

        const normalizedA = (valueA ?? '').toString();
        const normalizedB = (valueB ?? '').toString();
        return actionCenterSort.asc
            ? normalizedA.localeCompare(normalizedB)
            : normalizedB.localeCompare(normalizedA);
    });

    return rows;
}

function analyzeActionCenterRows(rows) {
    const settings = actionCenterSettings || readActionCenterSettingsFromForm();
    const highConfig = buildActionCenterPriorityConfig(settings, 'high');
    const mediumConfig = buildActionCenterPriorityConfig(settings, 'medium');
    const lowConfig = buildActionCenterPriorityConfig(settings, 'low');
    const veryLowConfig = buildActionCenterPriorityConfig(settings, 'very_low');
    const allRows = rows || [];
    const canDetectDuplicates = hasHighConfidenceDuplicateMetadata(allRows);
    actionCenterDuplicateDetectionAvailable = canDetectDuplicates;
    const signatureIdentitySets = {};
    const signatureGroupIds = {};
    let nextGroupIndex = 1;

    if (canDetectDuplicates) {
        allRows.forEach((row) => {
            const signature = buildHighConfidenceDuplicateSignature(row);
            if (!signatureIdentitySets[signature]) {
                signatureIdentitySets[signature] = new Set();
            }
            signatureIdentitySets[signature].add(buildDuplicateIdentityKey(row));
        });

        Object.entries(signatureIdentitySets).forEach(([signature, identitySet]) => {
            if (identitySet.size > 1) {
                signatureGroupIds[signature] = `DUP-${String(nextGroupIndex).padStart(4, '0')}`;
                nextGroupIndex += 1;
            }
        });
    }

    return allRows.map((row) => {
        const totalMB = parseActionCenterNumber(row['Total Size (MB)']);
        const versionsMB = parseActionCenterNumber(row['Versions Size (MB)']);
        const ageYears = calculateActionCenterAgeYears(row['Last Datetime of Original Version']);
        const reasons = [];
        let priority = 'Info';
        let recommendedAction = 'Monitor';
        const duplicateSignature = canDetectDuplicates ? buildHighConfidenceDuplicateSignature(row) : null;
        const duplicateCount = duplicateSignature ? (signatureIdentitySets[duplicateSignature]?.size || 1) : 1;
        const isDuplicate = canDetectDuplicates && duplicateCount > 1;
        const duplicateGroupId = duplicateSignature ? (signatureGroupIds[duplicateSignature] || '-') : '-';

        const highReasons = evaluateActionCenterPriorityAny(totalMB, versionsMB, ageYears, highConfig);
        const mediumReasons = evaluateActionCenterPriorityAny(totalMB, versionsMB, ageYears, mediumConfig);
        const veryLowReasons = evaluateActionCenterPriorityAll(totalMB, versionsMB, ageYears, veryLowConfig);
        const lowReasons = evaluateActionCenterPriorityAll(totalMB, versionsMB, ageYears, lowConfig);

        if (highReasons.length > 0) {
            priority = 'High';
            recommendedAction = 'Review for cleanup / move / compress';
            reasons.push(...highReasons);
        } else if (mediumReasons.length > 0) {
            priority = 'Medium';
            recommendedAction = 'Review version history / compress';
            reasons.push(...mediumReasons);
        } else if (veryLowReasons.length > 0) {
            priority = 'Very Low';
            recommendedAction = 'Archive or remove after owner confirmation';
            reasons.push(...veryLowReasons);
        } else if (lowReasons.length > 0) {
            priority = 'Low';
            recommendedAction = 'Archive / move to cold storage review';
            reasons.push(...lowReasons);
        } else {
            reasons.push('Within monitoring threshold');
        }

        if (isDuplicate) {
            reasons.unshift(`High-confidence duplicate metadata match (${duplicateCount} files in ${duplicateGroupId})`);
            if (priority === 'Info') {
                recommendedAction = recommendedAction === 'Monitor'
                    ? 'Review duplicate candidates'
                    : `${recommendedAction} + duplicate review`;
            } else if (!recommendedAction.includes('duplicate')) {
                recommendedAction = `${recommendedAction} + duplicate review`;
            }
        }

        return {
            ...row,
            'Age (Years)': ageYears === null ? '-' : ageYears.toFixed(1),
            'Duplicate Candidate': isDuplicate ? 'Yes' : 'No',
            'Duplicate Confidence': isDuplicate ? 'High' : '-',
            'Duplicate Count': duplicateCount,
            'Duplicate Group': duplicateGroupId,
            'Priority': priority,
            'Recommended Action': recommendedAction,
            'Reason': reasons.join(' | '),
        };
    });
}

function applyActionCenterFilters() {
    const searchTerm = (document.getElementById('actionSearch')?.value || '').toLowerCase().trim();
    const priorityFilter = document.getElementById('action-priority-filter')?.value || '';
    const actionFilter = document.getElementById('action-recommendation-filter')?.value || '';
    const duplicateFilter = document.getElementById('action-duplicate-filter')?.value || '';
    const analyzedRows = analyzeActionCenterRows(actionCenterRawRows);

    actionCenterFilteredRows = analyzedRows.filter((row) => {
        const matchesSearch = !searchTerm || [
            row['File Name'],
            row['Folder Path'],
            row['Reason'],
            row['Recommended Action'],
            row['Priority'],
            row['Duplicate Group'],
        ].some((value) => (value || '').toString().toLowerCase().includes(searchTerm));

        const matchesPriority = !priorityFilter || row['Priority'] === priorityFilter;
        const matchesAction = !actionFilter || (row['Recommended Action'] || '').includes(actionFilter);
        const matchesDuplicate = !duplicateFilter || row['Duplicate Candidate'] === duplicateFilter;
        return matchesSearch && matchesPriority && matchesAction && matchesDuplicate;
    });

    sortActionCenterRows(actionCenterFilteredRows);

    actionCenterCurrentPage = 1;
    renderActionCenterSummary(actionCenterFilteredRows);
    renderActionCenterTable();
}

function renderActionCenterSummary(rows) {
    const counters = {
        all: rows.length,
        high: rows.filter((row) => row['Priority'] === 'High').length,
        medium: rows.filter((row) => row['Priority'] === 'Medium').length,
        low: rows.filter((row) => row['Priority'] === 'Low').length,
        veryLow: rows.filter((row) => row['Priority'] === 'Very Low').length,
        duplicate: rows.filter((row) => row['Duplicate Candidate'] === 'Yes').length,
    };

    const mappings = {
        'ac-count-all': counters.all,
        'ac-count-high': counters.high,
        'ac-count-medium': counters.medium,
        'ac-count-low': counters.low,
        'ac-count-very-low': counters.veryLow,
        'ac-count-duplicate': counters.duplicate,
    };

    Object.entries(mappings).forEach(([id, value]) => {
        const element = document.getElementById(id);
        if (element) element.innerText = value.toLocaleString();
    });

    const info = document.getElementById('action-center-info');
    if (info) {
        let text = `FOUND: ${rows.length.toLocaleString()} ITEMS`;
        if (!actionCenterDuplicateDetectionAvailable && actionCenterRawRows.length > 0) {
            text += ' | DUPLICATE DETECTION UNAVAILABLE FOR THIS REPORT FORMAT';
        }
        info.innerText = text;
    }
}

function renderActionCenterTable() {
    const totalPages = Math.ceil(actionCenterFilteredRows.length / actionCenterPageSize) || 1;
    const start = (actionCenterCurrentPage - 1) * actionCenterPageSize;
    const pageRows = actionCenterFilteredRows.slice(start, start + actionCenterPageSize);
    const tbody = document.getElementById('action-center-table');
    if (!tbody) return;

    tbody.innerHTML = pageRows.map((row, index) => `
        <tr class="hover:bg-slate-50 border-b border-slate-100 align-top">
            <td class="p-3 text-center text-slate-400 font-mono">${start + index + 1}</td>
            <td class="p-3">
                <div class="text-[9px] text-slate-400 break-all" title="${buildSharePointFolderUrl(row['Folder Path'])}">${buildSharePointFolderUrl(row['Folder Path'])}</div>
                <div class="font-bold text-slate-700 text-[11px] break-all">${row['File Name'] || '-'}</div>
            </td>
            <td class="p-3 text-center font-bold text-slate-500">${row['Extension'] || '-'}</td>
            <td class="p-3 text-right font-mono">${parseActionCenterNumber(row['Versions Size (MB)']).toFixed(2)}</td>
            <td class="p-3 text-right font-bold text-slate-900 font-mono">${parseActionCenterNumber(row['Total Size (MB)']).toFixed(2)}</td>
            <td class="p-3 text-center font-mono">${row['Age (Years)'] || '-'}</td>
            <td class="p-3 text-center">
                <span class="inline-flex px-2.5 py-1 rounded-full text-[10px] font-black ${row['Duplicate Candidate'] === 'Yes' ? 'bg-fuchsia-100 text-fuchsia-700' : 'bg-slate-100 text-slate-500'}">
                    ${row['Duplicate Candidate'] || 'No'}
                </span>
            </td>
            <td class="p-3 text-center font-black ${row['Duplicate Candidate'] === 'Yes' ? 'text-fuchsia-600' : 'text-slate-500'}">${row['Duplicate Count'] || 1}</td>
            <td class="p-3 text-center">
                <span class="inline-flex px-2.5 py-1 rounded-full text-[10px] font-black ${getActionCenterPriorityColor(row['Priority'])}">
                    ${row['Priority'] || 'Info'}
                </span>
            </td>
            <td class="p-3 font-bold text-slate-700">${row['Recommended Action'] || '-'}</td>
            <td class="p-3 text-[10px] text-slate-600 font-mono">${formatDisplayDateTime(row['Last Datetime of Original Version'])}</td>
            <td class="p-3 text-[10px] text-slate-500">${row['Reason'] || '-'}</td>
        </tr>
    `).join('');

    if (pageRows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="12" class="p-6 text-center text-slate-400">No matching items</td></tr>';
    }

    document.getElementById('actionPageInput').value = actionCenterCurrentPage;
    document.getElementById('action-page-indicator').innerText = `of ${totalPages}`;
    document.getElementById('actionPrevBtn').disabled = actionCenterCurrentPage === 1;
    document.getElementById('actionNextBtn').disabled = actionCenterCurrentPage >= totalPages;
}

function changeActionCenterPage(step) {
    const totalPages = Math.ceil(actionCenterFilteredRows.length / actionCenterPageSize) || 1;
    const nextPage = actionCenterCurrentPage + step;
    if (nextPage >= 1 && nextPage <= totalPages) {
        actionCenterCurrentPage = nextPage;
        renderActionCenterTable();
    }
}

function goToActionCenterPage(value) {
    const totalPages = Math.ceil(actionCenterFilteredRows.length / actionCenterPageSize) || 1;
    let page = parseInt(value, 10);
    if (Number.isNaN(page) || page < 1) page = 1;
    if (page > totalPages) page = totalPages;
    actionCenterCurrentPage = page;
    renderActionCenterTable();
}

async function exportActionCenter(format) {
    if (!actionCenterFilteredRows.length) {
        alert("No filtered rows available for export.");
        return;
    }

    try {
        const category = document.getElementById('action-cat-select')?.value || 'Current_Scan_Detail';
        const deptName = document.getElementById('action-file-select')?.value || 'department';
        const now = new Date();
        const stamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`;
        const payload = {
            format,
            fileNameBase: `ActionCenter_${category}_${deptName}_${stamp}`,
            rows: actionCenterFilteredRows,
            summary: {
                matchedRows: actionCenterFilteredRows.length,
                highCount: actionCenterFilteredRows.filter((row) => row['Priority'] === 'High').length,
                mediumCount: actionCenterFilteredRows.filter((row) => row['Priority'] === 'Medium').length,
                lowCount: actionCenterFilteredRows.filter((row) => row['Priority'] === 'Low').length,
                veryLowCount: actionCenterFilteredRows.filter((row) => row['Priority'] === 'Very Low').length,
                duplicateCount: actionCenterFilteredRows.filter((row) => row['Duplicate Candidate'] === 'Yes').length,
                duplicateGroups: new Set(
                    actionCenterFilteredRows
                        .filter((row) => row['Duplicate Candidate'] === 'Yes')
                        .map((row) => row['Duplicate Group'])
                ).size,
            },
            meta: {
                category,
                deptName,
                exportedAt: now.toLocaleString(),
                searchTerm: document.getElementById('actionSearch')?.value || '',
                priorityFilter: document.getElementById('action-priority-filter')?.value || 'All',
                actionFilter: document.getElementById('action-recommendation-filter')?.value || 'All',
            },
            settings: readActionCenterSettingsFromForm(),
        };

        const result = await pywebview.api.export_action_center_report(payload);
        if (!result || !result.success) {
            if (result && result.cancelled) return;
            throw new Error(result && result.error ? result.error : "Unable to export report.");
        }

        let message = `Exported ${format.toUpperCase()} report:\n${result.path}`;
        if (result.note) message += `\n\nNote: ${result.note}`;
        alert(message);
    } catch (error) {
        console.error("exportActionCenter error:", error);
        alert("Unable to export Action Center report.");
    }
}

async function updateCompareList() {
    try {
        const select = document.getElementById('compare-dept-select');

        // 1. จำค่าที่เลือกไว้ปัจจุบันก่อน (ถ้ามี)
        const currentSelected = select.value;

        // ดึงรายชื่อจาก Python
        const departments = await pywebview.api.get_available_departments('Previous_Scan_Detail');

        if (!departments || departments.length === 0) {
            select.innerHTML = '<option value="">No Departments Found</option>';
            return;
        }

        // 2. สร้าง Option ใหม่ โดยคง "-- Select Department --" ไว้เป็นอันแรก
        let html = '<option value="">-- Select Department --</option>';
        html += departments.map(dept => `<option value="${dept}">${dept}</option>`).join('');
        select.innerHTML = html;

        // 3. ตรวจสอบว่าค่าเดิมยังอยู่ในลิสต์ใหม่ไหม ถ้าอยู่ให้เลือกคืนค่าเดิม
        if (currentSelected && departments.includes(currentSelected)) {
            select.value = currentSelected;
            // (Optional) ถ้าอยากให้กราฟอัปเดตทันทีที่สลับหน้ากลับมา ให้รันบรรทัดล่างนี้ด้วย
            // runAutoComparison(); 
        }

    } catch (err) {
        console.error("Error loading comparison list:", err);
    }
}
// 2. ฟังก์ชันรันการเปรียบเทียบแบบอัตโนมัติ
async function runAutoComparison() {
    const mode = document.querySelector('input[name="compare-mode"]:checked').value;
    const deptName = document.getElementById('compare-dept-select').value;

    if (!deptName) return alert("Please select department");

    try {
        const response = await pywebview.api.get_comparison_data(mode, deptName);
        if (response.error) {
            alert(response.error);
            return;
        }

        // ส่ง response พร้อมค่า mode เข้าไป
        renderComparisonUI(response, mode);

    } catch (err) {
        console.error(err);
    }
}

// 3. แยก Logic การวาด UI ออกมาเพื่อให้ใช้ซ้ำได้
// เพิ่ม parameter 'mode' เพื่อเอาไปใส่ในชื่อ Label
// เพิ่ม parameter 'mode' เพื่อใช้ในการแยกแยะธีมของ UI
function renderComparisonUI(response, mode = 'vs_current') {
    const data = response.chartData;
    const summary = response.summary;


    // --- ส่วนที่ 1: กำหนดธีมตาม Mode ---
    const isOriginal = mode === 'vs_original';
    const modeTitleElem = document.getElementById('compare-mode-title');
    const themeColor = isOriginal ? '#f06832' : '#94a3b8'; // เขียวเข้ม vs เทา
    const labelTitle = isOriginal ? 'Original (GB)' : 'Before (GB)';

    // --- ส่วนที่ 2: อัปเดตตัวเลขและสีใน Cards ---
    const beforeElement = document.getElementById('compare-previous-gb');
    beforeElement.innerText = summary.totalBefore.toFixed(2);

    if (modeTitleElem) {
        if (isOriginal) {
            modeTitleElem.innerText = "Comparison between Original Size and After Size";
            modeTitleElem.style.color = "#f06832"; // เปลี่ยนเป็นสีเขียวมรกต
        } else {
            modeTitleElem.innerText = "Comparison between Previous Size and After Size";
            modeTitleElem.style.color = "#6366f1"; // เปลี่ยนเป็นสีน้ำเงิน Indigo ให้ดูเด่น
        }
    }
    document.getElementById('compare-current-gb').innerText = summary.totalAfter.toFixed(2);

    // แสดงผล MB
    const beforeMB = (summary.totalBefore * 1024).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    const afterMB = (summary.totalAfter * 1024).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });

    document.getElementById('compare-before-mb').innerText = `(${beforeMB} MB)`;
    document.getElementById('compare-after-mb').innerText = `(${afterMB} MB)`;

    // คำนวณ Recovery
    const diff = summary.totalBefore - summary.totalAfter;
    document.getElementById('compare-recovered-gb').innerText = diff.toFixed(2);

    const percent = summary.totalBefore > 0 ? (diff / summary.totalBefore) * 100 : 0;
    document.getElementById('compare-savings-percent').innerText = `(${percent.toFixed(2)}% Saved)`;
    // --- Logic การวาดกราฟเดิมของคุณ (ที่รองรับการเปลี่ยนสีและชื่อโหมด) ---
    // --- ส่วนที่ 3: วาดกราฟ ---
    const modeLabel = isOriginal ? '(Original)' : '(Prev)';
    const ctx = document.getElementById('compareChart').getContext('2d');

    if (window.compareChart instanceof Chart) {
        window.compareChart.destroy();
    }



    // ตรวจสอบและทำลายกราฟเดิมก่อนวาดใหม่ (เพื่อป้องกันกราฟซ้อนกัน)
    if (window.compareChart instanceof Chart) {
        window.compareChart.destroy();
    }

    window.compareChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(item => `${item['Library Name']} ${modeLabel}`),
            datasets: [
                {
                    label: isOriginal ? 'Original Size (GB)' : 'Before Size (GB)',
                    data: data.map(item => item['Before']),
                    backgroundColor: themeColor,
                    borderRadius: 6
                },
                {
                    label: 'After Size (GB)',
                    data: data.map(item => item['After']),
                    backgroundColor: '#4f46e5',
                    borderRadius: 6
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: {
                        usePointStyle: true,
                        font: { weight: 'bold' }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: (ctx) => ` ${ctx.dataset.label}: ${ctx.raw.toFixed(2)} GB`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Storage Size (GB)' }
                }
            }
        }
    });
}

const TAB_GROUPS = {
    'main': 'overview',
    'compare': 'analysis',
    'after-detail': 'analysis',
    'delete-version': 'analysis',
    'scan': 'operations',
    'data-tools': 'operations',
    'action-center': 'operations'
};

const GROUP_DEFAULT_TABS = {
    'overview': 'main',
    'analysis': 'compare',
    'operations': 'scan'
};

function switchMainTab(groupName) {
    switchTab(GROUP_DEFAULT_TABS[groupName] || 'main');
}

function updateHeaderTabState(tabName) {
    const groupBtns = {
        'overview': 'btn-group-overview',
        'analysis': 'btn-group-analysis',
        'operations': 'btn-group-operations'
    };

    const subnavs = {
        'overview': 'subnav-overview',
        'analysis': 'subnav-analysis',
        'operations': 'subnav-operations'
    };

    const activeGroup = TAB_GROUPS[tabName] || 'overview';

    Object.entries(groupBtns).forEach(([groupName, id]) => {
        const btn = document.getElementById(id);
        if (!btn) return;
        btn.classList.remove('bg-indigo-600', 'text-white', 'shadow-sm');
        btn.classList.add('text-slate-500');
        if (groupName === activeGroup) {
            btn.classList.remove('text-slate-500');
            btn.classList.add('bg-indigo-600', 'text-white', 'shadow-sm');
        }
    });

    Object.entries(subnavs).forEach(([groupName, id]) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.toggle('hidden', groupName !== activeGroup);
    });
}

function switchTab(tabName) {
    // 1. รายชื่อ ID ของหน้าที่ต้องจัดการ
    const pages = {
        'main': 'page-main',
        'scan': 'page-scan',
        'action-center': 'page-action-center',
        'data-tools': 'page-data-tools',
        'compare': 'page-compare',
        'after-detail': 'page-after-detail',
        'delete-version': 'page-delete-version' // <--- เพิ่ม ID หน้าใหม่
    };

    const btns = {
        'main': 'btn-main',
        'scan': 'btn-scan',
        'action-center': 'btn-action-center',
        'data-tools': 'btn-data-tools',
        'compare': 'btn-compare',
        'after-detail': 'btn-after-detail',
        'delete-version': 'btn-delete-version' // <--- เพิ่ม ID ปุ่มใหม่
    };

    // 2. ซ่อนทุกหน้า และปรับสีปุ่มให้เป็นตัวจาง
    Object.values(pages).forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden');
    });

    Object.values(btns).forEach(id => {
        const btn = document.getElementById(id);
        if (btn) {
            btn.classList.remove('bg-white', 'shadow-sm', 'text-indigo-600');
            btn.classList.add('text-slate-500');
        }
    });

    // 3. แสดงหน้าที่เลือก และไฮไลท์ปุ่ม
    if (pages[tabName]) {
        document.getElementById(pages[tabName]).classList.remove('hidden');
    }

    const activeBtn = document.getElementById(btns[tabName]);
    if (activeBtn) {
        activeBtn.classList.remove('text-slate-500');
        activeBtn.classList.add('bg-white', 'shadow-sm', 'text-indigo-600');
    }

    // --- เงื่อนไขการโหลดข้อมูลในแต่ละหน้า ---
    updateHeaderTabState(tabName);

    if (tabName === 'scan') {
        updateFileList();
    }
    if (tabName === 'action-center') {
        fillActionCenterSettingsForm();
        updateActionCenterFileList();
    }
    if (tabName === 'compare') {
        updateCompareList();
    }
    if (tabName === 'after-detail') {
        refreshAfterDetail();
    }
    // เพิ่มเงื่อนไขสำหรับหน้าใหม่: โหลดรายชื่อแผนกจากโฟลเดอร์ DeleteVersion_Detail
    if (tabName === 'delete-version') {
        updateDeleteVersionList();
    }
}
// (เพิ่มฟังก์ชัน goToPage)
function goToPage(value) {
    const totalPages = Math.ceil(filteredData.length / pageSize) || 1;
    let targetPage = parseInt(value);

    // ตรวจสอบขอบเขตของเลขหน้า
    if (isNaN(targetPage) || targetPage < 1) targetPage = 1;
    if (targetPage > totalPages) targetPage = totalPages;

    currentPage = targetPage;
    renderScanPage();
}

// ฟังก์ชันเสริมสำหรับ Pagination และ Search
function changePage(dir) {
    const totalPages = Math.ceil(filteredData.length / pageSize) || 1;
    const nextStep = currentPage + dir;

    if (nextStep >= 1 && nextStep <= totalPages) {
        currentPage = nextStep;
        renderScanPage(); // วาดหน้าใหม่ พร้อมเลขหน้าใหม่
    }
}

function handleSort(key) {
    // ถ้ากดซ้ำที่เดิมให้สลับ Asc/Desc
    if (currentSort.key === key) {
        currentSort.asc = !currentSort.asc;
    } else {
        currentSort.key = key;
        currentSort.asc = true;
    }

    filteredData.sort((a, b) => {
        let valA = a[key] || "";
        let valB = b[key] || "";

        // ถ้าเป็นตัวเลข (ขนาดไฟล์ หรือ Version) ให้แปลงเป็น Float ก่อนเทียบ
        if (key.includes('MB') || key.includes('Count')) {
            valA = parseFloat(valA) || 0;
            valB = parseFloat(valB) || 0;
        } else {
            valA = valA.toString().toLowerCase();
            valB = valB.toString().toLowerCase();
        }

        if (valA < valB) return currentSort.asc ? -1 : 1;
        if (valA > valB) return currentSort.asc ? 1 : -1;
        return 0;
    });

    currentPage = 1; // สั่งเรียงแล้วให้กลับไปหน้า 1
    renderScanPage();
}
function handleSearch() {
    const term = document.getElementById('scanSearch').value.toLowerCase();
    filteredData = fullScanData.filter(r =>
        (r['File Name'] || '').toString().toLowerCase().includes(term) ||
        (r['Folder Path'] || '').toString().toLowerCase().includes(term) ||
        (r['Last Datetime of Original Version'] || '').toString().toLowerCase().includes(term) ||
        (r['First Datetime of History Version'] || '').toString().toLowerCase().includes(term)
    );

    updateScanSummary(filteredData); // อัปเดตสรุปตามข้อมูลที่กรอง
    currentPage = 1;
    renderScanPage();
}

function renderComparisonChart(data) {
    const ctx = document.getElementById('compareChart').getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => d['Library Name']),
            datasets: [
                { label: 'Before (MB)', data: data.map(d => d['Total Size (MB)_Before']), backgroundColor: '#cbd5e1' },
                { label: 'After (MB)', data: data.map(d => d['Total Size (MB)_After']), backgroundColor: '#6366f1' }
            ]
        },
        options: { responsive: true, maintainAspectRatio: false }
    });
}


async function runComparison() {
    const fileBefore = document.getElementById('file-before').value;
    const fileAfter = document.getElementById('file-after').value;

    if (!fileBefore || !fileAfter) {
        alert("กรุณาเลือกไฟล์ทั้งสองฝั่งครับ");
        return;
    }

    try {
        const response = await pywebview.api.get_comparison_data(fileBefore, fileAfter);

        if (!response || !response.chartData || response.chartData.length === 0) {
            alert("ไม่พบข้อมูลที่สามารถเปรียบเทียบได้");
            return;
        }

        const data = response.chartData;
        const summary = response.summary;

        // 1. อัปเดตตัวเลขใน Summary Cards
        const totalB_GB = summary.totalBefore || 0;
        const totalA_GB = summary.totalAfter || 0;
        const diff_GB = totalB_GB - totalA_GB;
        const savingPercent = totalB_GB > 0 ? (diff_GB / totalB_GB) * 100 : 0;

        // แสดง GB ตัวใหญ่
        document.getElementById('compare-previous-gb').innerText = totalB_GB.toFixed(2);
        document.getElementById('compare-current-gb').innerText = totalA_GB.toFixed(2);
        document.getElementById('compare-recovered-gb').innerText = diff_GB.toFixed(2);

        // แสดง MB ในวงเล็บ (แปลง GB กลับเป็น MB)
        if (document.getElementById('compare-before-mb')) {
            const mb = (totalB_GB * 1024).toLocaleString(undefined, { maximumFractionDigits: 0 });
            document.getElementById('compare-before-mb').innerText = `(${mb} MB)`;
        }
        if (document.getElementById('compare-after-mb')) {
            const mb = (totalA_GB * 1024).toLocaleString(undefined, { maximumFractionDigits: 0 });
            document.getElementById('compare-after-mb').innerText = `(${mb} MB)`;
        }

        // อัปเดต % Saved
        const savingsEl = document.getElementById('compare-savings-percent');
        if (savingsEl) {
            savingsEl.innerText = `(${savingPercent.toFixed(2)}% Saved)`;
        }

        // 2. จัดการกราฟ (ใช้หน่วย GB)
        const ctx = document.getElementById('compareChart').getContext('2d');
        if (compareChart) { compareChart.destroy(); }

        compareChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.map(item => item['Library Name']),
                datasets: [
                    {
                        label: 'Before (GB)',
                        data: data.map(item => item['Before']),
                        backgroundColor: '#94a3b8',
                        borderRadius: 6
                    },
                    {
                        label: 'After (GB)',
                        data: data.map(item => item['After']),
                        backgroundColor: '#4f46e5',
                        borderRadius: 6
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top' },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => ` ${ctx.dataset.label}: ${ctx.raw.toFixed(2)} GB`
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: { display: true, text: 'Size in Gigabytes (GB)', font: { weight: 'bold' } }
                    }
                }
            }
        });

    } catch (error) {
        console.error("JS Error:", error);
        alert("เกิดข้อผิดพลาด: " + error.message);
    }
}

function showPage(pageId) {
    // 1. รายชื่อ ID ของ section ทั้งหมดที่คุณมีในหน้าเว็บ
    const pages = ['page-dashboard', 'page-analysis', 'page-compare'];

    // 2. วนลูปเพื่อซ่อนทุกหน้า (ใส่ class 'hidden')
    pages.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.classList.add('hidden');
        }
    });

    // 3. แสดงเฉพาะหน้าจอที่ต้องการ (เอา class 'hidden' ออก)
    const activePage = document.getElementById(pageId);
    if (activePage) {
        activePage.classList.remove('hidden');
    }
}

async function loadReport() {
    const category = document.getElementById('cat-select').value;
    const deptName = document.getElementById('file-select').value;

    if (!deptName) return;

    // 1. ดึงข้อมูลจาก Python
    const data = await pywebview.api.get_latest_scan_data(category, deptName);

    if (data.error) {
        alert(data.error);
        return;
    }

    // 2. อัปเดตตัวเลข Dashboard (คำนวณจาก Data ที่ได้มา)
    updateDashboardStats(data);

    // 3. วาดตารางข้อมูล
    renderTable(data);
}

function renderTable(items) {
    const tbody = document.querySelector('#data-table tbody'); // เปลี่ยน ID ให้ตรงกับ HTML ของคุณ
    tbody.innerHTML = '';

    document.getElementById('found-count').textContent = `FOUND: ${items.length} ITEMS`;

    items.forEach((item, index) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${index + 1}</td>
            <td>${item['File Details'] || item['File_Name'] || '-'}</td>
            <td>${item['Ext'] || '-'}</td>
            <td>${item['Current (MB)'] || 0}</td>
            <td>${item['Vers'] || 0}</td>
            <td>${item['Total (MB)'] || 0}</td>
        `;
        tbody.appendChild(tr);
    });
}

async function syncData() {
    // แจ้งเตือนว่ากำลังเริ่มทำงาน
    alert("System is syncing new data...");

    // เรียกใช้ฟังก์ชัน Python (ตัวอย่างนี้ใช้ผ่าน Python Bridge เช่น Eel หรือ pywebview)
    await window.pywebview.api.sync_new_data();

    // รีโหลดหน้าจอเพื่อแสดงผลข้อมูลล่าสุด
    location.reload();
}

async function handleSync() {
    const btn = document.getElementById('sync-btn');
    const btnText = document.getElementById('sync-btn-text');
    const badge = document.getElementById('sync-badge');

    // 1. เปลี่ยนสถานะปุ่มให้กำลังโหลด
    btn.disabled = true;
    btn.classList.add('opacity-50', 'cursor-not-allowed');
    btnText.innerText = "SYNCING FILES...";
    if (badge) {
        badge.classList.add('hidden');
        badge.classList.remove('inline-flex');
    }

    try {
        // 2. เรียก Python ย้ายไฟล์ (ยึดตาม API ใน main.py)
        const result = await window.pywebview.api.sync_new_data();

        if (result.status === "success") {
            // 3. บันทึกเวลาปัจจุบันไว้ในเครื่อง
            const now = new Date();
            const timeStr = `LAST SYNC: ${now.toLocaleDateString()} ${now.toLocaleTimeString()}`;
            localStorage.setItem('last_sync', timeStr);

            // 4. รีโหลดหน้าจอทันที ไม่ต้องรอ OK
            location.reload();
        } else if (result.status === "info") {
            alert(result.message);
            resetBtn();
            await refreshSyncQueueStatus();
        } else {
            alert("Error: " + result.message);
            resetBtn();
            await refreshSyncQueueStatus();
        }
    } catch (err) {
        console.error(err);
        resetBtn();
        await refreshSyncQueueStatus();
    }

    function resetBtn() {
        btn.disabled = false;
        btn.classList.remove('opacity-50', 'cursor-not-allowed');
        btnText.innerText = DEFAULT_SYNC_BUTTON_TEXT;
    }
}

async function openSharePointScanner() {
    try {
        const result = await window.pywebview.api.open_sharepoint_inventory_window();

        if (!result || result.status !== "success") {
            alert("ไม่สามารถเปิด SharePoint scanner ได้" + (result && result.message ? `: ${result.message}` : ""));
            return;
        }

        alert(
            "เปิดหน้าต่าง SharePoint แล้ว\n\n" +
            "1. ลงชื่อเข้าใช้ให้เรียบร้อยถ้าระบบถาม\n" +
            "2. เมื่อเข้าไซต์ H6323_SPOF แล้ว จะมีปุ่มลอย 'Run Inventory'\n" +
            "3. กดปุ่มนั้นเพื่อรันรายงานและดาวน์โหลด CSV ได้ทันที"
        );
    } catch (error) {
        console.error("openSharePointScanner error:", error);
        alert("ไม่สามารถติดต่อระบบเพื่อเปิด SharePoint scanner ได้");
    }
}

// ส่วนแสดงเวลาเมื่อเปิดหน้าเว็บขึ้นมาใหม่

// 5. ส่วนแสดงเวลาหลังโหลดหน้าจอเสร็จ (ใส่ไว้ในจุดที่เหมาะสมในไฟล์ app.js)
window.addEventListener('DOMContentLoaded', () => {
    const lastTime = localStorage.getItem('lastSyncTime');
    if (lastTime) {
        // หา Element ที่ต้องการแสดงเวลา (สมมติว่าสร้าง id="sync-status" ไว้)
        const statusEl = document.getElementById('sync-status');
        if (statusEl) {
            statusEl.innerText = `Last updated: ${lastTime}`;
        }
    }
});
// ตรวจสอบว่าปุ่มใน HTML มีการเรียก onclick="handleSync()"


async function syncNewData() {
    // 1. เปลี่ยน UI ปุ่มให้ดูเหมือนกำลังทำงาน (Optional)
    console.log("Syncing...");

    // 2. เรียก Python
    const result = await window.pywebview.api.sync_new_data();

    // 3. จัดการผลลัพธ์
    if (result.status === "success") {
        alert("✅ " + result.message);
        location.reload(); // รีโหลดหน้าจอเพื่อดึง List ไฟล์ใหม่
    } else if (result.status === "info") {
        alert("ℹ️ " + result.message);
    } else {
        alert("❌ Error: " + result.message);
    }
}


function renderAfterStackedChart(data) {
    const ctx = document.getElementById('afterStackedChart').getContext('2d');

    // ลบกราฟเก่าทิ้งก่อนถ้ามี
    if (afterChart) afterChart.destroy();

    // ตัวอย่าง data: [{ dept: 'FO', current: 100, versions: 50 }, { dept: 'FB', current: 80, versions: 30 }]
    const labels = data.map(item => item.dept);
    const currentSizes = data.map(item => item.current); // สีฟ้า
    const versionSizes = data.map(item => item.versions); // สีส้ม

    afterChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Current Size (GB)',
                    data: currentSizes,
                    backgroundColor: '#6366f1', // Indigo (ฟ้า/ม่วง)
                    borderRadius: 5,
                },
                {
                    label: 'Versions Size (GB)',
                    data: versionSizes,
                    backgroundColor: '#f97316', // Orange (ส้ม)
                    borderRadius: 5,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { stacked: true }, // เปิดโหมดแท่งซ้อน
                y: {
                    stacked: true,
                    beginAtZero: true,
                    title: { display: true, text: 'Storage Size (GB)', font: { weight: 'bold' } }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        footer: (tooltipItems) => {
                            let sum = 0;
                            tooltipItems.forEach(i => sum += i.parsed.y);
                            return `Total Size: ${sum.toFixed(2)} GB`;
                        }
                    }
                }
            }
        }
    });
}

// // ตัวแปรเก็บ Instance ของ Chart เพื่อลบตัวเก่าทิ้งเวลา Refresh

async function refreshAfterDetail() {
    try {
        const data = await pywebview.api.get_after_delete_summary();
        if (!data || data.length === 0) return;

        let globalCurrent = 0;
        let globalVersions = 0;
        let tableHtml = '';

        data.forEach(item => {
            const current = parseFloat(item.current);
            const versions = parseFloat(item.versions);
            const total = current + versions;

            // คำนวณ % ของแผนกนั้นๆ
            const currentPercent = total > 0 ? ((current / total) * 100).toFixed(1) : 0;
            const versionPercent = total > 0 ? ((versions / total) * 100).toFixed(1) : 0;

            globalCurrent += current;
            globalVersions += versions;

            tableHtml += `
                <tr class="hover:bg-slate-50 transition-colors">
                    <td class="px-4 py-3 text-sm font-bold text-slate-700">${item.dept}</td>
                    <td class="px-4 py-3 text-sm text-right text-indigo-600 font-medium">${current.toFixed(2)} GB (${currentPercent}%)</td>
                    <td class="px-4 py-3 text-sm text-right text-orange-500 font-medium">${versions.toFixed(2)} GB (${versionPercent}%)</td>
                    <td class="px-4 py-3 text-sm text-right font-bold text-slate-800">${total.toFixed(2)} GB</td>
                </tr>
            `;
        });

        // แสดงผลรวม (Summary) ด้านบนตาราง
        const globalTotal = globalCurrent + globalVersions;
        const globalCurrentP = ((globalCurrent / globalTotal) * 100).toFixed(1);
        const globalVersionP = ((globalVersions / globalTotal) * 100).toFixed(1);

        document.getElementById('after-detail-summary').innerHTML = `
            <div class="flex gap-4 mb-4">
                <div class="flex-1 bg-indigo-50 p-3 rounded-lg border border-indigo-100">
                    <p class="text-xs text-indigo-600 font-bold uppercase">Total Current</p>
                    <p class="text-xl font-bold text-indigo-700">${globalCurrent.toFixed(2)} GB <span class="text-sm font-normal">(${globalCurrentP}%)</span></p>
                </div>
                <div class="flex-1 bg-orange-50 p-3 rounded-lg border border-orange-100">
                    <p class="text-xs text-orange-600 font-bold uppercase">Total Versions</p>
                    <p class="text-xl font-bold text-orange-700">${globalVersions.toFixed(2)} GB <span class="text-sm font-normal">(${globalVersionP}%)</span></p>
                </div>
            </div>
        `;

        document.getElementById('after-detail-table-body').innerHTML = tableHtml;

        // วาดกราฟ (ใช้ Logic เดิม)
        renderAfterStackedChart(data.map(i => i.dept), data.map(i => i.current), data.map(i => i.versions));

    } catch (error) {
        console.error("Error calculating percentages:", error);
    }
}

function renderAfterStackedChart(labels, currentData, versionData) {
    const ctx = document.getElementById('afterStackedChart').getContext('2d');

    if (afterChartInstance) {
        afterChartInstance.destroy();
    }

    afterChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Current Size (GB)',
                    data: currentData,
                    backgroundColor: '#6366f1', // สีฟ้า Indigo
                    borderRadius: 4
                },
                {
                    label: 'Versions Size (GB)',
                    data: versionData,
                    backgroundColor: '#f97316', // สีส้ม Orange
                    borderRadius: 4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { stacked: true },
                y: {
                    stacked: true,
                    beginAtZero: true,
                    title: { display: true, text: 'Storage Size (GB)' }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        footer: (items) => {
                            let total = items.reduce((sum, item) => sum + item.parsed.y, 0);
                            return `Total: ${total.toFixed(2)} GB`;
                        }
                    }
                }
            }
        }
    });
}


// --- Import Modal Logic ---
function openImportModal() {
    document.getElementById('importModal').classList.remove('hidden');
}

function closeImportModal() {
    document.getElementById('importModal').classList.add('hidden');
}

async function handleImport(type) {
    try {
        const result = await pywebview.api.import_csv_file(type);

        if (result.success) {
            let message = `Import success: ${result.count} file(s)`;
            if (result.details) {
                message += `\n\n${result.details}`;
            }
            alert(message);
            closeImportModal();
            if (typeof handleSync === "function") handleSync();
            return;
        }

        if (result.error && result.error !== "No file selected") {
            alert("Import blocked:\n\n" + result.error);
            return;
        }

        if (result.success) {
            // แจ้งเตือนจำนวนไฟล์ที่ Import สำเร็จ
            alert(`✅ Import สำเร็จทั้งหมด ${result.count} ไฟล์`);
            if (result.details) {
                alert(`âœ… Import à¸ªà¸³à¹€à¸£à¹‡à¸ˆà¸—à¸±à¹‰à¸‡à¸«à¸¡à¸” ${result.count} à¹„à¸Ÿà¸¥à¹Œ\n\n${result.details}`);
            }
            closeImportModal();
            if (typeof handleSync === "function") handleSync();
        } else if (result.error) {
            if (result.error !== "No file selected") {
                alert("❌ เกิดข้อผิดพลาด: " + result.error);
            }
        }
    } catch (err) {
        console.error("Import Error:", err);
    }
}

// 1. เพิ่มฟังก์ชันช่วยแปลงหน่วย (Helper Function)
function formatStorageSize(sizeMB) {
    const val = parseFloat(sizeMB || 0);
    if (val >= 1024) {
        return (val / 1024).toFixed(2) + " GB";
    }
    return val.toFixed(2) + " MB";
}

// ฟังก์ชันโหลดรายชื่อแผนกเมื่อเปิดหน้า
async function initDeleteVersionPage() {
    const depts = await pywebview.api.get_delete_version_departments();
    const select = document.getElementById('select-dept-delete');
    select.innerHTML = '<option value="">-- เลือกแผนก --</option>';
    depts.forEach(d => {
        select.innerHTML += `<option value="${d}">${d}</option>`;
    });
}

// ฟังก์ชันดึงข้อมูลจาก CSV มาแสดง
async function loadDeleteVersionData() {
    const dept = document.getElementById('select-dept-delete').value;
    if (!dept) return;

    // เพิ่มบรรทัดนี้เพื่อล้างช่อง Search เมื่อเปลี่ยนแผนก
    document.getElementById('input-search-delete').value = '';
    document.getElementById('select-policy-filter').value = '';
    try {
        const data = await pywebview.api.get_delete_version_data(dept);
        if (data.error) { alert(data.error); return; }

        rawDeleteData = data;
        filteredDeleteData = [...rawDeleteData]; // เริ่มต้นให้ข้อมูลเท่ากัน
        currentDelPage = 1;

        // อัปเดตตัวเลข Summary (ใช้ข้อมูลทั้งหมดในการคำนวณ)
        updateDeleteSummary();
        // แสดงผลตารางหน้าแรก
        renderDeleteTable(1);
        // --- เพิ่มบรรทัดนี้เพื่อวาดกราฟเมื่อโหลดแผนกใหม่ ---
        updatePolicyChart(filteredDeleteData);

    } catch (err) { console.error(err); }
}

// ฟังก์ชันสำหรับดึงรายชื่อแผนกในโฟลเดอร์ DeleteVersion_Detail
// 1. ฟังก์ชันดึงรายชื่อแผนก Cleanup (เรียกตอนโหลดหน้าหรือหลัง Sync)
async function updateDeleteVersionList() {
    try {
        const select = document.getElementById('select-dept-delete');
        if (!select) return;

        // --- 1. เพิ่มบรรทัดนี้: จำค่าแผนกที่เลือกไว้ปัจจุบันก่อน ---
        const currentSelected = select.value;

        // ใช้ API ตามชื่อที่คุณตั้งไว้ (ตรวจสอบให้ตรงกับ Python ของคุณ)
        const depts = await pywebview.api.get_delete_version_departments();

        // 2. ล้างและสร้าง Options ใหม่
        select.innerHTML = '<option value="">-- Select Department --</option>';
        depts.forEach(dept => {
            const option = document.createElement('option');
            option.value = dept;
            option.textContent = dept;
            select.appendChild(option);
        });

        // --- 3. เพิ่มบรรทัดนี้: ถ้าแผนกเดิมยังอยู่ในลิสต์ใหม่ ให้เลือกคืนค่าเดิม ---
        if (currentSelected && depts.includes(currentSelected)) {
            select.value = currentSelected;
        }

    } catch (err) {
        console.error("Failed to update dept list:", err);
    }
}

// ฟังก์ชันกรองข้อมูล (Filter)
function filterDeleteData() {
    // ดึงค่าจากตัวกรองต่างๆ
    const searchTerm = document.getElementById('input-search-delete').value.toLowerCase();
    const policyFilter = document.getElementById('select-policy-filter').value;
    const sortType = document.getElementById('select-sort-delete') ? document.getElementById('select-sort-delete').value : 'size-desc';

    // 1. เริ่มการกรองข้อมูล (Filtering)
    let result = rawDeleteData.filter(row => {
        // กรองด้วย Search Term (File หรือ Folder)
        const matchSearch = (row.File || "").toLowerCase().includes(searchTerm) ||
            (row.Folder || "").toLowerCase().includes(searchTerm);

        // กรองด้วย Policy Dropdown (จัดการกรณี None)
        let matchPolicy = false;
        const currentPolicy = (row.PolicyApplied || "").trim();

        if (policyFilter === "") {
            // ถ้าเลือก -- All Policies -- ให้ผ่านหมด
            matchPolicy = true;
        } else if (policyFilter === "None") {
            // ปรับปรุง: เช็คทั้งค่าว่าง, ค่าที่เป็น "-", หรือคำว่า "None" โดยไม่สนตัวพิมพ์เล็กพิมพ์ใหญ่
            matchPolicy = (currentPolicy === "" || currentPolicy === "-" || currentPolicy.toLowerCase() === "none");
        } else {
            // ถ้าเลือก Policy เฉพาะเจาะจง ให้เช็คว่าตรงกันเป๊ะๆ
            matchPolicy = (currentPolicy === policyFilter);
        }

        return matchSearch && matchPolicy;
    });

    // 2. การเรียงลำดับ (Sorting)
    result.sort((a, b) => {
        if (sortType === 'size-desc') {
            return parseFloat(b.SpaceSavedMB || 0) - parseFloat(a.SpaceSavedMB || 0);
        } else if (sortType === 'size-asc') {
            return parseFloat(a.SpaceSavedMB || 0) - parseFloat(b.SpaceSavedMB || 0);
        } else if (sortType === 'name-asc') {
            return (a.File || "").localeCompare(b.File || "");
        } else if (sortType === 'name-desc') {
            return (b.File || "").localeCompare(a.File || "");
        }
        return 0;
    });

    // อัปเดตข้อมูลและ Render ใหม่
    filteredDeleteData = result;
    currentDelPage = 1; // กลับไปหน้า 1 เสมอเมื่อมีการกรองใหม่
    updateDeleteSummary();
    renderDeleteTable();

    // อัปเดตกราฟตามผลการ Filter
    if (typeof updatePolicyChart === 'function') {
        updatePolicyChart(filteredDeleteData);
    }
}
// ฟังก์ชัน Render ตารางตามหน้าปัจจุบัน
// 3. แก้ไขฟังก์ชัน Render ตารางเพื่อให้คอลัมน์ Saved และ Final Size แสดงหน่วยด้วย
function renderDeleteTable() {
    const tbody = document.getElementById('body-delete-version');
    const start = (currentDelPage - 1) * delPageSize;
    const end = start + delPageSize;
    const pageData = filteredDeleteData.slice(start, end);

    tbody.innerHTML = '';

    if (pageData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center py-8 text-slate-400">ไม่พบข้อมูล</td></tr>';
    }

    pageData.forEach(row => {
        tbody.innerHTML += `
            <tr class="hover:bg-slate-50 transition-all border-b border-slate-100">
                <td class="px-4 py-2 font-medium text-slate-700 text-[11px]">${row.File || '-'}</td>
                <td class="px-4 py-2 text-slate-500 truncate max-w-[250px] text-[10px]" title="${row.Folder}">${row.Folder || '-'}</td>
                <td class="px-4 py-2"><span class="bg-slate-100 px-2 py-0.5 rounded text-[9px]">${row.PolicyApplied || '-'}</span></td>
                <td class="px-4 py-2 text-right">${parseInt(row.VersionsDeleted || 0).toLocaleString()}</td>
                <td class="px-4 py-2 text-right text-emerald-600 font-bold">${formatStorageSize(row.SpaceSavedMB)}</td>
                <td class="px-4 py-2 text-right text-slate-600">${formatStorageSize(row.FinalSizeMB)}</td>
            </tr>
        `;
    });
    const totalPages = Math.ceil(filteredDeleteData.length / delPageSize) || 1;

    // อัปเดตเลขหน้าในช่องพิมพ์
    document.getElementById('input-current-page').value = currentDelPage;
    // อัปเดตเลขหน้าทั้งหมด
    document.getElementById('txt-total-pages').innerText = `of ${totalPages}`;

    // ปุ่มกด Prev/Next ใช้ ID เดิมที่คุณมีได้เลย
    document.getElementById('btn-prev-del').disabled = currentDelPage === 1;
    document.getElementById('btn-next-del').disabled = currentDelPage === totalPages;
}
//     const totalPages = Math.ceil(filteredDeleteData.length / delPageSize) || 1;
//     document.getElementById('txt-page-info').innerText = `Page ${currentDelPage} of ${totalPages}`;
//     document.getElementById('btn-prev-del').disabled = currentDelPage === 1;
//     document.getElementById('btn-next-del').disabled = currentDelPage === totalPages;       
// }

// ฟังก์ชันเปลี่ยนหน้า
function changeDeletePage(step) {
    const totalPages = Math.ceil(filteredDeleteData.length / delPageSize);
    const newPage = currentDelPage + step;

    if (newPage >= 1 && newPage <= totalPages) {
        currentDelPage = newPage;
        renderDeleteTable();
        updatePolicyChart(data);
    }
}


function updateDeleteSummary() {
    let totalSavedMB = 0;
    let totalVers = 0;
    const policySummary = {};

    filteredDeleteData.forEach(row => {
        const savedMB = parseFloat(row.SpaceSavedMB || 0);
        const policy = (row.PolicyApplied || 'None / No Policy').trim();

        totalSavedMB += savedMB;
        totalVers += parseInt(row.VersionsDeleted || 0);

        policySummary[policy] = (policySummary[policy] || 0) + savedMB;
    });

    // อัปเดตตัวเลขภาพรวม
    const totalSavedGB = totalSavedMB / 1024;
    document.getElementById('txt-total-saved').innerText = totalSavedGB.toFixed(2) + " GB";
    document.getElementById('txt-total-versions').innerText = totalVers.toLocaleString();

    // สร้าง Policy Cards
    const cardsContainer = document.getElementById('policy-cards-container');
    cardsContainer.innerHTML = '';

    const colorMap = {
        'Retention 365 Days': { bg: 'bg-violet-50', border: 'border-violet-100', text: 'text-violet-700', label: 'text-violet-600' },
        'Retention 90 Days': { bg: 'bg-blue-50', border: 'border-blue-100', text: 'text-blue-700', label: 'text-blue-600' },
        'Large File Policy': { bg: 'bg-amber-50', border: 'border-amber-100', text: 'text-amber-700', label: 'text-amber-600' },
        'default': { bg: 'bg-slate-50', border: 'border-slate-100', text: 'text-slate-700', label: 'text-slate-600' }
    };

    Object.entries(policySummary).forEach(([policy, sizeMB]) => {
        const sizeGB = sizeMB / 1024;

        // 🔥 เงื่อนไขการซ่อน: ถ้าชื่อเป็น "-" หรือค่าเป็น 0 ให้ข้ามไปเลย
        if (policy === "-" || policy === "" || sizeGB <= 0) {
            return;
        }

        const colors = colorMap[policy] || colorMap['default'];

        const cardHTML = `
            <div class="flex-1 min-w-[280px] ${colors.bg} p-6 rounded-3xl border ${colors.border} shadow-sm transition-all hover:shadow-md">
                <div class="flex justify-between items-start">
                    <div>
                        <h3 class="${colors.label} text-[11px] font-black uppercase mb-1 tracking-wider">${policy}</h3>
                        <p class="text-3xl font-black ${colors.text}">${sizeGB.toFixed(2)} GB</p>
                    </div>
                </div>
                <div class="mt-4 pt-4 border-t ${colors.border.replace('100', '200')} border-dashed">
                    <p class="text-[10px] text-slate-400 font-bold uppercase">Contribution to Total Savings</p>
                </div>
            </div>
        `;
        cardsContainer.innerHTML += cardHTML;
    });
}

function sortTable(columnName) {
    // ถ้าคลิกคอลัมน์เดิม ให้สลับสถานะ Asc/Desc
    if (currentSortCol === columnName) {
        isAsc = !isAsc;
    } else {
        currentSortCol = columnName;
        isAsc = true;
    }

    filteredDeleteData.sort((a, b) => {
        let valA = a[columnName] || 0;
        let valB = b[columnName] || 0;

        // ถ้าเป็นคอลัมน์ตัวเลข ให้แปลงเป็น Float ก่อนคำนวณ
        if (columnName === 'SpaceSavedMB' || columnName === 'FinalSizeMB' || columnName === 'VersionsDeleted') {
            valA = parseFloat(valA);
            valB = parseFloat(valB);
            return isAsc ? valA - valB : valB - valA;
        }

        // ถ้าเป็นข้อความ (String)
        valA = valA.toString().toLowerCase();
        valB = valB.toString().toLowerCase();
        return isAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
    });

    currentDelPage = 1; // กลับไปหน้าแรกเสมอเมื่อเรียงใหม่
    renderDeleteTable();
}

function jumpToPage() {
    const input = document.getElementById('input-current-page');
    const totalPages = Math.ceil(filteredDeleteData.length / delPageSize) || 1;
    let targetPage = parseInt(input.value);

    // ดักจับกรณีพิมพ์เลขมั่ว
    if (isNaN(targetPage) || targetPage < 1) targetPage = 1;
    if (targetPage > totalPages) targetPage = totalPages;

    currentDelPage = targetPage;
    renderDeleteTable();
}


function updatePolicyChart(data) {
    const ctx = document.getElementById('policyChart');
    if (!ctx || !data) return;

    // 1. กำหนดคู่สีให้ตรงกับ Policy Cards
    const policyColors = {
        'Retention 365 Days': '#a855f7', // Purple
        'Retention 90 Days': '#3b82f6',  // Blue
        'Large File Policy': '#f59e0b',  // Amber
        'default': '#94a3b8'             // Slate
    };

    const summary = {};
    data.forEach(item => {
        const policy = (item.PolicyApplied || 'No Policy').trim();
        const savedMB = parseFloat(item.SpaceSavedMB || 0);
        summary[policy] = (summary[policy] || 0) + (savedMB / 1024);
    });

    const filteredEntries = Object.entries(summary).filter(([policy, value]) => {
        return policy !== "-" && policy !== "" && value > 0;
    });

    const sortedEntries = filteredEntries.sort((a, b) => b[1] - a[1]);
    const labels = sortedEntries.map(e => e[0]);
    const values = sortedEntries.map(e => e[1].toFixed(2));

    // 🔥 2. สร้าง Array ของสีตามลำดับของ Labels ที่กรองแล้ว
    const backgroundColors = labels.map(policy => policyColors[policy] || policyColors['default']);

    if (myPolicyChart) {
        myPolicyChart.destroy();
    }

    myPolicyChart = new Chart(ctx.getContext('2d'), {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Space Saved (GB)',
                data: values,
                // 🔥 3. เปลี่ยนจาก gradient เดิม เป็น Array ของสีที่เราเตรียมไว้
                backgroundColor: backgroundColors,
                borderRadius: 20,
                borderSkipped: false,
                barThickness: 24,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1e293b',
                    padding: 10,
                    callbacks: {
                        label: function (context) {
                            return ` ✨ Saved: ${context.raw} GB`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    grid: { display: false },
                    ticks: {
                        font: { size: 10 },
                        callback: v => v + ' GB'
                    }
                },
                y: {
                    grid: { display: false },
                    border: { display: false },
                    ticks: {
                        font: { size: 11, weight: 'bold' },
                        color: '#475569'
                    }
                }
            },
            animation: {
                duration: 1500,
                easing: 'easeOutQuart'
            }
        }
    });
}

async function handleOriginalBackupImport() {
    try {
        const result = await pywebview.api.import_original_and_backup();

        if (result.success) {
            let message = `✅ นำเข้าสำเร็จ ${result.count} ไฟล์`;
            if (result.details) {
                message += `\n${result.details}`;
            }
            alert(message);

            if (typeof handleSync === "function") handleSync();
        } else if (result.error) {
            if (result.error !== "No file selected") {
                alert("❌ เกิดข้อผิดพลาด: " + result.error);
            }
        }
    } catch (err) {
        alert("❌ ไม่สามารถติดต่อระบบได้");
    }
}
