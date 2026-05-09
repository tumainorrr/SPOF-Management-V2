import webview
import os
import sys
import shutil
import glob
import json
from bridge import SharePointApi 
import time
import re
import os
import glob
import shutil
import tkinter as tk
from tkinter import filedialog
from datetime import datetime
import time
import shutil
class EnhancedApi(SharePointApi):
    SHAREPOINT_SITE_URL = "https://accor.sharepoint.com/sites/H6323_SPOF"

    def __init__(self):
        super().__init__()
        self._sharepoint_window = None
        self._sharepoint_launcher_js = self._build_sharepoint_launcher_js()

    def get_data_root(self):
        # หาตำแหน่ง Folder หลักของโปรแกรม (ที่อยู่ข้างๆ .exe หรือข้างๆโฟลเดอร์ src)
        if getattr(sys, 'frozen', False):
            # ถ้าเป็น EXE โฟลเดอร์ Data จะอยู่ระดับเดียวกับ .exe
            return os.path.dirname(sys.executable)
        else:
            # ถ้าเป็น Dev (รันจาก src/main.py) โฟลเดอร์ Data จะอยู่ที่ Root ของโปรเจกต์
            return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    def _is_supported_sync_filename(self, filename):
        if not filename or not filename.lower().endswith(".csv"):
            return False

        supported_patterns = [
            r"^SharePoint_Report_\d{8}_\d{4}\.csv$",
            r"^ScanSize_[A-Za-z0-9-]+_Report_\d{8}_\d{4}\.csv$",
            r"^Cleanup_Report_[A-Za-z0-9_-]+_\d{8}_\d{4}\.csv$",
        ]

        return any(re.fullmatch(pattern, filename) for pattern in supported_patterns)

    def get_sync_queue_status(self):
        try:
            root_path = self.get_data_root()
            queue_dir = os.path.join(root_path, "Data", "Initial_Receive")
            os.makedirs(queue_dir, exist_ok=True)

            pending_files = sorted(
                [
                    filename for filename in os.listdir(queue_dir)
                    if self._is_supported_sync_filename(filename)
                    and os.path.isfile(os.path.join(queue_dir, filename))
                ],
                key=lambda name: os.path.getmtime(os.path.join(queue_dir, name)),
                reverse=True
            )

            latest_file = pending_files[0] if pending_files else None

            return {
                "status": "success",
                "has_pending": len(pending_files) > 0,
                "pending_count": len(pending_files),
                "latest_file": latest_file,
                "watched_path": queue_dir,
                "pending_files": pending_files[:10],
            }
        except Exception as e:
            return {"status": "error", "message": f"เกิดข้อผิดพลาด: {str(e)}"}

    def sync_new_data(self):
        try:
            root_path = self.get_data_root()
            base_data = os.path.join(root_path, "Data")
            
            # --- โฟลเดอร์หลัก ---
            new_dir = os.path.join(base_data, "Initial_Receive")
            after_dir = os.path.join(base_data, "Current_Scan_Detail")
            before_dir = os.path.join(base_data, "Previous_Scan_Detail")
            delete_ver_dir = os.path.join(base_data, "DeleteVersion_Detail")
            
            # --- โฟลเดอร์ Backup หลัก ---
            backup_root = os.path.join(base_data, "Backup")

            # ฟังก์ชันช่วยดึง วันที่จากชื่อไฟล์ และสร้าง Path Backup (ปี/เดือน)
            def get_dynamic_backup_path(sub_folder, filename):
                # ค้นหาตัวเลข 8 หลัก เช่น 20260402
                date_match = re.search(r"(\d{4})(\d{2})\d{2}", filename)
                if date_match:
                    year = date_match.group(1)  # 2026
                    month = date_match.group(2) # 04
                else:
                    # ถ้าหาไม่เจอให้ใช้ ปี/เดือน ปัจจุบันกันเหนียว
                    from datetime import datetime
                    year = datetime.now().strftime("%Y")
                    month = datetime.now().strftime("%m")
                
                target_dir = os.path.join(backup_root, sub_folder, year, month)
                os.makedirs(target_dir, exist_ok=True)
                return target_dir

            # สร้างโฟลเดอร์หลักที่จำเป็น (ส่วน Backup ย่อยจะสร้างตอนย้ายไฟล์)
            for d in [new_dir, after_dir, before_dir, delete_ver_dir]:
                os.makedirs(d, exist_ok=True)

            sync_status = False
            executed_tasks = []

            # ==========================================
            # ส่วนที่ 1: ระบบใหม่ (SharePoint_Report -> ย้ายเข้า Data)
            # ==========================================
            sp_new_reports = [
                os.path.join(new_dir, filename)
                for filename in os.listdir(new_dir)
                if filename.startswith("SharePoint_Report_")
                and self._is_supported_sync_filename(filename)
            ]
            if sp_new_reports:
                for sp_file_path in sp_new_reports:
                    filename = os.path.basename(sp_file_path)
                    target_path = os.path.join(base_data, filename) 

                    old_reports_in_data = glob.glob(os.path.join(base_data, "SharePoint_Report_*.csv"))
                    for old_file in old_reports_in_data:
                        try:
                            old_name = os.path.basename(old_file)
                            # สร้าง Path ตามวันที่ในชื่อไฟล์เก่า: Backup\ScanSizeOverall\YYYY\MM
                            bak_path = get_dynamic_backup_path("ScanSizeOverall", old_name)
                            shutil.move(old_file, os.path.join(bak_path, old_name))
                        except: pass

                    shutil.move(sp_file_path, target_path)
                    sync_status = True
                    executed_tasks.append(f"Summary Synced")

            # ==========================================
            # ส่วนที่ 2: ระบบเดิม (ScanSize_* ขั้นบันได)
            # ==========================================
            new_dept_files = [
                os.path.join(new_dir, filename)
                for filename in os.listdir(new_dir)
                if filename.startswith("ScanSize_")
                and self._is_supported_sync_filename(filename)
            ]
            if new_dept_files:
                for new_file_path in new_dept_files:
                    filename = os.path.basename(new_file_path)
                    if "SharePoint_Report" in filename: continue

                    parts = filename.split("_")
                    if len(parts) < 2: continue
                    
                    dept_name = parts[1]
                    dept_prefix = f"ScanSize_{dept_name}_Report"

                    # 1. ย้าย Before -> Backup (ไปยัง ScanVersionDetail\YYYY\MM)
                    for f in glob.glob(os.path.join(before_dir, f"{dept_prefix}*.csv")):
                        ts = int(time.time())
                        old_name = os.path.basename(f)
                        # สร้าง Path ตามวันที่ในชื่อไฟล์ที่จะ backup
                        bak_path = get_dynamic_backup_path("ScanVersionDetail", old_name)
                        shutil.move(f, os.path.join(bak_path, f"{old_name}"))

                    # 2. ย้าย After -> Before
                    for f in glob.glob(os.path.join(after_dir, f"{dept_prefix}*.csv")):
                        shutil.move(f, os.path.join(before_dir, os.path.basename(f)))

                    # 3. ย้าย New -> After
                    shutil.move(new_file_path, os.path.join(after_dir, filename))
                    sync_status = True
                
                executed_tasks.append("Department Data Synced")

            # ==========================================
            # ส่วนที่ 3: ระบบย้ายไฟล์ Cleanup_Report
            # ==========================================
            cleanup_new_files = [
                os.path.join(new_dir, filename)
                for filename in os.listdir(new_dir)
                if filename.startswith("Cleanup_Report_")
                and self._is_supported_sync_filename(filename)
            ]
            if cleanup_new_files:
                for cl_file_path in cleanup_new_files:
                    filename = os.path.basename(cl_file_path)
                    match = re.search(r"Cleanup_Report_(.*?)_\d{8}", filename)
                    if match:
                        dept_tag = match.group(1)
                        
                        # 1. ย้ายไฟล์เก่าใน DeleteVersion_Detail ไปยัง DeleteVersion_Backup_Detail\YYYY\MM
                        for old_cl in os.listdir(delete_ver_dir):
                            if old_cl.startswith(f"Cleanup_Report_{dept_tag}_"):
                                ts = int(time.time())
                                old_path = os.path.join(delete_ver_dir, old_cl)
                                # สร้าง Path ตามวันที่ในชื่อไฟล์เก่า
                                bak_path = get_dynamic_backup_path("DeleteVersion_Backup_Detail", old_cl)
                                shutil.move(old_path, os.path.join(bak_path, f"{old_cl}"))

                        # 2. ย้ายไฟล์ใหม่เข้าสู่ DeleteVersion_Detail
                        shutil.move(cl_file_path, os.path.join(delete_ver_dir, filename))
                        sync_status = True
                
                executed_tasks.append("Cleanup Reports Updated")

            # ==========================================
            # Response
            # ==========================================
            if not sync_status:
                return {"status": "info", "message": "ไม่พบไฟล์ใหม่สำหรับซิงค์"}

            return {
                "status": "success", 
                "message": "ดำเนินการสำเร็จ: " + " & ".join(executed_tasks)
            }

        except Exception as e:
            return {"status": "error", "message": f"เกิดข้อผิดพลาด: {str(e)}"}

    # เพิ่มในคลาส EnhancedApi
    def import_original_and_backup(self):
            try:
                # 1. Select Files
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                file_paths = filedialog.askopenfilenames(
                    title="Select Original Files to Import",
                    filetypes=[("CSV Files", "*.csv")]
                )
                root.destroy()

                if not file_paths:
                    return {"error": "No file selected"}

                root_path = self.get_data_root()
                target_dir = os.path.join(root_path, "Data", "ScanSizeOriginalFirstTime")
                backup_root = os.path.join(root_path, "Data", "Backup")

                def get_dynamic_backup_path(sub_folder, filename):
                    date_match = re.search(r"(\d{4})(\d{2})\d{2}", filename)
                    year, month = (date_match.group(1), date_match.group(2)) if date_match else (datetime.now().strftime("%Y"), datetime.now().strftime("%m"))
                    target_path = os.path.join(backup_root, sub_folder, year, month)
                    os.makedirs(target_path, exist_ok=True)
                    return target_path

                os.makedirs(target_dir, exist_ok=True)

                imported_count = 0
                backup_tasks = []
                skipped_files = []

                for path in file_paths:
                    filename = os.path.basename(path)
                    
                    # Validation: Must start with ScanSize_ and not be a Summary report
                    if not filename.startswith("ScanSize_") or "SharePoint_Report" in filename:
                        continue

                    # 🔥 Logic: Extract Prefix (e.g., ScanSize_DPT-FB_Report)
                    parts = filename.split("_")
                    if len(parts) < 2: continue
                    dept_name = parts[1] # Extracts "DPT-FB" or "Forum"
                    dept_prefix = f"ScanSize_{dept_name}_Report"

                    # Check if this exact file already exists
                    dest_file_path = os.path.join(target_dir, filename)
                    if os.path.exists(dest_file_path):
                        skipped_files.append(filename) # Skip if identical file exists
                        continue

                    # 🔥 Logic: Find any existing file for this Department to Backup
                    existing_dept_files = glob.glob(os.path.join(target_dir, f"{dept_prefix}*.csv"))
                    
                    for old_file in existing_dept_files:
                        old_filename = os.path.basename(old_file)
                        # Move old department file to Dynamic Backup Path
                        bak_path = get_dynamic_backup_path("ScanOriginalVersionDetail", old_filename)
                        shutil.move(old_file, os.path.join(bak_path, old_filename))
                        backup_tasks.append(f"{old_filename} -> Backup")

                    # Import the new file
                    shutil.copy2(path, dest_file_path)
                    imported_count += 1

                # Summary
                report = f"✅ Imported: {imported_count} files."
                if backup_tasks: report += f"\n📦 Backed up {len(backup_tasks)} previous department versions."
                if skipped_files: report += f"\nℹ️ Skipped (Exact Match): {len(skipped_files)} files."

                return {"success": True, "details": report}

            except Exception as e:
                return {"error": str(e)}

    def _build_sharepoint_launcher_js(self):
        scan_logic = r"""
(async () => {
  const siteUrl = "https://accor.sharepoint.com/sites/H6323_SPOF";
  const DELAY_MS = 500;
  const results = [];
  let totalItems = 0;
  let totalBytes = 0;

  const sleep = (ms) => new Promise(res => setTimeout(res, ms));

  const getThaiFileNameDate = () => {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    const hh = String(now.getHours()).padStart(2, '0');
    const mm = String(now.getMinutes()).padStart(2, '0');
    return `${y}${m}${d}_${hh}${mm}`;
  };

  const oldOverlay = document.getElementById("sp-estimate-overlay");
  if (oldOverlay) oldOverlay.remove();

  const overlay = document.createElement("div");
  overlay.id = "sp-estimate-overlay";
  overlay.style = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(15,23,42,0.7);display:flex;justify-content:center;align-items:center;z-index:10000;backdrop-filter:blur(4px);";

  const modal = document.createElement("div");
  modal.style = "background:white;padding:25px;border-radius:12px;width:min(900px,92vw);max-height:85vh;display:flex;flex-direction:column;font-family:Segoe UI,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,0.35);";
  modal.innerHTML = `
    <h2 style="margin:0 0 10px 0;color:#0078d4;">Library Inventory Report</h2>
    <p id="st" style="font-size:13px;color:#666;margin:0 0 14px 0;">Initializing scan...</p>
    <div style="flex-grow:1;overflow-y:auto;border:1px solid #eee;border-radius:8px;background:#fafafa;">
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead style="background:#f9f9f9;position:sticky;top:0;z-index:1;">
          <tr>
            <th style="padding:10px;text-align:left;border-bottom:2px solid #ddd;">Library Name</th>
            <th style="padding:10px;text-align:right;border-bottom:2px solid #ddd;">Items</th>
            <th style="padding:10px;text-align:right;border-bottom:2px solid #ddd;">Size (MB)</th>
            <th style="padding:10px;text-align:right;border-bottom:2px solid #ddd;">Size (GB)</th>
            <th style="padding:10px;text-align:center;border-bottom:2px solid #ddd;">Last Update</th>
          </tr>
        </thead>
        <tbody id="tb"></tbody>
        <tfoot id="tf" style="background:#f0f7ff;font-weight:bold;position:sticky;bottom:0;"></tfoot>
      </table>
    </div>
    <div style="margin-top:15px;text-align:right;display:flex;justify-content:flex-end;gap:10px;">
      <button id="dl-csv" style="padding:8px 15px;border:none;background:#0078d4;color:white;cursor:pointer;border-radius:4px;display:none;font-weight:bold;">Save to Initial_Receive</button>
      <button id="cx" style="padding:8px 15px;border:none;background:#eee;cursor:pointer;border-radius:4px;">Close</button>
    </div>
  `;

  document.body.appendChild(overlay);
  overlay.appendChild(modal);
  document.getElementById("cx").onclick = () => overlay.remove();

  try {
    const res = await fetch(`${siteUrl}/_api/web/lists?$filter=BaseTemplate eq 101 and Hidden eq false&$select=Title,ItemCount,RootFolder/ServerRelativeUrl&$expand=RootFolder`, {
      headers: { "Accept": "application/json;odata=verbose" }
    });

    if (!res.ok) {
      throw new Error(`List API returned ${res.status}`);
    }

    const data = await res.json();
    const libs = (data.d.results || []).filter(l => !["Form Templates", "Site Assets", "Style Library"].includes(l.Title));

    for (let i = 0; i < libs.length; i++) {
      const lib = libs[i];
      document.getElementById("st").innerHTML = `Scanning: <b>${lib.Title}</b> (${i + 1}/${libs.length})`;

      let displayGB = "0.000";
      let displayMB = "0.00";
      let lastUpdate = "-";
      let bytes = 0;

      const encodedPath = lib.RootFolder.ServerRelativeUrl.replace(/'/g, "''");
      const folderRes = await fetch(`${siteUrl}/_api/web/getfolderbyserverrelativeurl('${encodedPath}')?$select=StorageMetrics&$expand=StorageMetrics`, {
        headers: { "Accept": "application/json;odata=verbose" }
      });

      if (folderRes.ok) {
        const fData = await folderRes.json();
        const metrics = fData.d.StorageMetrics || {};

        bytes = Number(metrics.TotalSize) || 0;
        const itemCount = Number(lib.ItemCount) || 0;

        displayGB = (bytes / (1024 ** 3)).toFixed(3);
        displayMB = (bytes / (1024 ** 2)).toFixed(2);

        if (metrics.LastModified) {
          lastUpdate = new Date(metrics.LastModified).toLocaleString('th-TH');
        }

        totalItems += itemCount;
        totalBytes += bytes;
      }

      results.push({
        title: lib.Title,
        items: Number(lib.ItemCount) || 0,
        mb: displayMB,
        gb: displayGB,
        updated: lastUpdate
      });

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td style="padding:10px;border-bottom:1px solid #eee;">${lib.Title}</td>
        <td style="padding:10px;text-align:right;border-bottom:1px solid #eee;">${(Number(lib.ItemCount) || 0).toLocaleString()}</td>
        <td style="padding:10px;text-align:right;border-bottom:1px solid #eee;color:#0078d4;">${displayMB} MB</td>
        <td style="padding:10px;text-align:right;border-bottom:1px solid #eee;font-weight:bold;color:#d83b01;">${displayGB} GB</td>
        <td style="padding:10px;text-align:center;border-bottom:1px solid #eee;color:#666;">${lastUpdate}</td>
      `;
      document.getElementById("tb").appendChild(tr);
      tr.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

      if (i < libs.length - 1) await sleep(DELAY_MS);
    }

    const totalMBVal = (totalBytes / (1024 ** 2)).toFixed(2);
    const totalGBVal = (totalBytes / (1024 ** 3)).toFixed(3);

    document.getElementById("tf").innerHTML = `
      <tr>
        <td style="padding:10px;border-top:2px solid #0078d4;">GRAND TOTAL</td>
        <td style="padding:10px;text-align:right;border-top:2px solid #0078d4;">${totalItems.toLocaleString()}</td>
        <td style="padding:10px;text-align:right;border-top:2px solid #0078d4;color:#0078d4;">${Number(totalMBVal).toLocaleString()} MB</td>
        <td style="padding:10px;text-align:right;border-top:2px solid #0078d4;color:#d83b01;">${Number(totalGBVal).toLocaleString()} GB</td>
        <td style="padding:10px;border-top:2px solid #0078d4;"></td>
      </tr>
    `;

    document.getElementById("st").textContent = "Scan completed successfully.";

    const dlBtn = document.getElementById("dl-csv");
    dlBtn.style.display = "block";
    dlBtn.onclick = async () => {
      dlBtn.disabled = true;
      const originalText = dlBtn.textContent;
      dlBtn.textContent = "Saving...";

      let csvContent = "\uFEFF";
      csvContent += "Library Name,Total Items,Size (MB),Size (GB),Last Modified\n";
      results.forEach(r => {
        csvContent += `"${String(r.title).replace(/"/g, '""')}",${r.items},${r.mb},${r.gb},"${String(r.updated).replace(/"/g, '""')}"\n`;
      });
      csvContent += `"\nGRAND TOTAL",${totalItems},${totalMBVal},${totalGBVal},""\n`;

      const fileName = `SharePoint_Report_${getThaiFileNameDate()}.csv`;

      try {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.save_sharepoint_inventory_csv_auto) {
          const saveResult = await window.pywebview.api.save_sharepoint_inventory_csv_auto(csvContent, fileName);
          if (!saveResult || !saveResult.success) {
            throw new Error(saveResult && saveResult.error ? saveResult.error : "Unable to auto-save CSV.");
          }
          document.getElementById("st").textContent = `Saved to Initial_Receive: ${saveResult.path}`;
        } else {
          throw new Error("Desktop save bridge is not available.");
        }
      } catch (saveError) {
        document.getElementById("st").textContent = "Save error: " + saveError.message;
      } finally {
        dlBtn.disabled = false;
        dlBtn.textContent = originalText;
      }
    };
  } catch (e) {
    document.getElementById("st").textContent = "Error: " + e.message;
  }
})();
"""

        version_scan_logic = r"""
(async () => {
  const siteUrl = "https://accor.sharepoint.com/sites/H6323_SPOF";
  const BATCH_SIZE = 5000;
  const CONCURRENCY_LIMIT = 3;
  const MAX_RETRIES = 5;

  function escapeOData(str) {
    return str ? str.replace(/'/g, "''") : "";
  }

  function getThaiTime() {
    const now = new Date();
    const tzOffset = 7 * 60 * 60 * 1000;
    const thaiDate = new Date(now.getTime() + tzOffset);
    return thaiDate.toISOString().replace('Z', '').replace('T', ' ').split('.')[0];
  }

  function formatThaiDateTime(value) {
    if (!value) return "";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "";
    const tzOffset = 7 * 60 * 60 * 1000;
    const thaiDate = new Date(parsed.getTime() + tzOffset);
    return thaiDate.toISOString().replace('Z', '').replace('T', ' ').split('.')[0];
  }

  function getFileSuffix() {
    const now = new Date();
    const tzOffset = 7 * 60 * 60 * 1000;
    const d = new Date(now.getTime() + tzOffset);
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, '0');
    const day = String(d.getUTCDate()).padStart(2, '0');
    const hh = String(d.getUTCHours()).padStart(2, '0');
    const mm = String(d.getUTCMinutes()).padStart(2, '0');
    return `${y}${m}${day}_${hh}${mm}`;
  }

  const sleep = (ms) => new Promise(res => setTimeout(res, ms));

  async function fetchWithRetry(url, options, retries = MAX_RETRIES) {
    try {
      const res = await fetch(url, options);
      if ((res.status === 429 || res.status === 406 || !res.ok) && retries > 0) {
        const waitTime = (MAX_RETRIES - retries + 1) * 2000 + (Math.random() * 1000);
        await sleep(waitTime);
        return await fetchWithRetry(url, options, retries - 1);
      }
      return res;
    } catch (e) {
      if (retries > 0) {
        await sleep(2000);
        return await fetchWithRetry(url, options, retries - 1);
      }
      throw e;
    }
  }

  async function saveCsvToInitialReceive(csvContent, fileName) {
    if (!(window.pywebview && window.pywebview.api && window.pywebview.api.save_sharepoint_inventory_csv_auto)) {
      throw new Error("Desktop save bridge is not available.");
    }

    const saveResult = await window.pywebview.api.save_sharepoint_inventory_csv_auto(csvContent, fileName);
    if (!saveResult || !saveResult.success) {
      throw new Error(saveResult && saveResult.error ? saveResult.error : "Unable to auto-save CSV.");
    }
    return saveResult;
  }

  async function getLibraries() {
    const res = await fetchWithRetry(`${siteUrl}/_api/web/lists?$filter=BaseTemplate eq 101 and Hidden eq false&$expand=RootFolder`, {
      headers: { "Accept": "application/json;odata=verbose" }
    });
    const data = await res.json();
    return data.d.results.map(l => ({
      title: l.Title,
      url: l.RootFolder.ServerRelativeUrl
    }))
    .filter(lib => !["Form Templates", "Site Assets", "Style Library"].includes(lib.title))
    .sort((a, b) => a.title.localeCompare(b.title, undefined, { sensitivity: 'accent' }));
  }

  async function getSubFolders(folderUrl) {
    try {
      const safePath = escapeOData(folderUrl);
      const endpoint = `${siteUrl}/_api/web/GetFolderByServerRelativeUrl(@target)/folders?@target='${encodeURIComponent(safePath)}'`;
      const res = await fetchWithRetry(endpoint, { headers: { "Accept": "application/json;odata=verbose" } });
      if (!res.ok) return [];
      const data = await res.json();
      return data.d.results
        .filter(f => f.Name !== "Forms")
        .map(f => ({ name: f.Name, url: f.ServerRelativeUrl }))
        .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }));
    } catch (e) {
      return [];
    }
  }

  function createModal(titleText) {
    const existing = document.getElementById("sp-modal-overlay");
    if (existing) existing.remove();

    const overlay = document.createElement("div");
    overlay.id = "sp-modal-overlay";
    overlay.style = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);display:flex;justify-content:center;align-items:center;z-index:10000;backdrop-filter:blur(2px);";

    const modal = document.createElement("div");
    modal.style = "background:white;padding:25px;border-radius:12px;box-shadow:0 15px 35px rgba(0,0,0,0.4);width:850px;max-height:85vh;overflow-y:auto;font-family:'Segoe UI',Tahoma,sans-serif;display:flex;flex-direction:column;";

    const title = document.createElement("div");
    title.textContent = titleText;
    title.style = "font-weight:bold;margin-bottom:15px;font-size:18px;color:#0078d4;border-bottom:2px solid #0078d4;padding-bottom:8px;";

    const container = document.createElement("div");
    container.style = "flex-grow:1; overflow-y:auto;";

    modal.appendChild(title);
    modal.appendChild(container);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    return { overlay, container };
  }

  function createBtn(text, color, bgColor) {
    const btn = document.createElement("button");
    btn.textContent = text;
    btn.style = `padding:8px 16px;border:none;border-radius:4px;cursor:pointer;font-weight:bold;color:${color};background:${bgColor};transition:0.2s;margin-left:8px;font-size:13px;`;
    btn.onmouseover = () => btn.style.opacity = "0.8";
    btn.onmouseout = () => btn.style.opacity = "1";
    return btn;
  }

  async function showStep1() {
    const libraries = await getLibraries();
    const { overlay, container } = createModal("Step 1: Select Libraries to Scan");

    const utilBox = document.createElement("div");
    utilBox.style = "margin-bottom:12px;display:flex;align-items:center;gap:10px;";
    const selAll = createBtn("Select All", "#0078d4", "#f0f7ff");
    const deSelAll = createBtn("Deselect All", "#666", "#eee");

    const counter = document.createElement("span");
    counter.id = "sel-count";
    counter.textContent = "Selected: 0";
    counter.style = "font-size:14px;color:#444;margin-left:auto;font-weight:bold;";

    utilBox.appendChild(selAll);
    utilBox.appendChild(deSelAll);
    utilBox.appendChild(counter);
    container.appendChild(utilBox);

    const listDiv = document.createElement("div");
    listDiv.style = "display:grid;grid-template-columns:repeat(3,1fr);gap:8px 15px;border:1px solid #ddd;padding:15px;border-radius:8px;max-height:450px;overflow-y:auto;margin-bottom:20px;background:#fafafa;";

    libraries.forEach(lib => {
      const lbl = document.createElement("label");
      lbl.style = "display:flex;align-items:center;cursor:pointer;font-size:15px;padding:6px;border-radius:4px;transition:0.2s;font-weight:500;color:#333;";
      lbl.onmouseover = () => lbl.style.background = "#eef4fb";
      lbl.onmouseout = () => lbl.style.background = "transparent";

      const chk = document.createElement("input");
      chk.type = "checkbox";
      chk.className = "lib-chk";
      chk.value = lib.url;
      chk.dataset.title = lib.title;
      chk.style = "margin-right:12px;cursor:pointer;width:18px;height:18px;accent-color:#0078d4;";
      chk.onchange = () => {
        const count = container.querySelectorAll('.lib-chk:checked').length;
        counter.textContent = `Selected: ${count}`;
      };

      lbl.appendChild(chk);
      lbl.appendChild(document.createTextNode(lib.title));
      listDiv.appendChild(lbl);
    });

    container.appendChild(listDiv);

    selAll.onclick = () => {
      container.querySelectorAll('.lib-chk').forEach(c => c.checked = true);
      counter.textContent = `Selected: ${libraries.length}`;
    };

    deSelAll.onclick = () => {
      container.querySelectorAll('.lib-chk').forEach(c => c.checked = false);
      counter.textContent = "Selected: 0";
    };

    const btnBox = document.createElement("div");
    btnBox.style = "display:flex;justify-content:flex-end;border-top:1px solid #eee;padding-top:15px;";
    const closeBtn = createBtn("Close", "#666", "#eee");
    closeBtn.onclick = () => document.body.removeChild(overlay);
    const nextBtn = createBtn("Next Step", "white", "#0078d4");
    nextBtn.style.padding = "10px 20px";
    nextBtn.style.fontSize = "14px";

    nextBtn.onclick = () => {
      const selected = Array.from(container.querySelectorAll('.lib-chk:checked')).map(c => ({
        title: c.dataset.title,
        url: c.value
      }));

      if (selected.length === 0) {
        alert("Please select at least one library.");
        return;
      }

      document.body.removeChild(overlay);
      showStep2Multi(selected);
    };

    btnBox.appendChild(closeBtn);
    btnBox.appendChild(nextBtn);
    container.appendChild(btnBox);
  }

  async function showStep2Multi(selectedLibs) {
    const { overlay, container } = createModal("Step 2: Scope Scan");
    container.parentElement.style.width = "550px";

    const libNamesHtml = selectedLibs.map(l => `<div style="padding:4px 8px;margin:2px;background:#e1f5fe;border-radius:4px;font-size:12px;display:inline-block;border:1px solid #b3e5fc;">${l.title}</div>`).join("");

    container.innerHTML = `
      <div style="margin-bottom:15px;background:#f8f9fa;padding:12px;border:1px solid #ddd;border-radius:8px;">
        <div style="font-weight:bold;color:#333;margin-bottom:8px;display:flex;justify-content:space-between;">
          <span>Selected Libraries:</span>
          <span style="background:#0078d4;color:white;padding:0 8px;border-radius:10px;">${selectedLibs.length}</span>
        </div>
        <div style="max-height:100px;overflow-y:auto;border:1px inset #eee;padding:5px;background:white;border-radius:4px;">
          ${libNamesHtml}
        </div>
      </div>
      <div style="margin-bottom:15px;background:#fff9e6;padding:10px;border-left:4px solid #ffc107;font-size:13px;color:#856404;">
        <strong>Note:</strong> Libraries will be processed sequentially. Each result CSV will auto-save to Initial_Receive.
      </div>
      <div style="margin-bottom:15px;padding:0 5px;">
        <p style="font-weight:bold;margin-bottom:8px;font-size:14px;">Scanning Depth:</p>
        <label style="display:block;margin-bottom:8px;cursor:pointer;font-size:14px;"><input type="radio" name="scope" value="allfolders" checked> All Folders (Recursive)</label>
        <label style="display:block;margin-bottom:8px;cursor:pointer;font-size:14px;"><input type="radio" name="scope" value="allfiles"> Files in Root Folders Only</label>
      </div>
    `;

    const btnBox = document.createElement("div");
    btnBox.style = "display:flex;justify-content:space-between;margin-top:15px;";
    const backBtn = createBtn("Back", "#333", "#eee");
    backBtn.onclick = () => {
      document.body.removeChild(overlay);
      showStep1();
    };
    const startBtn = createBtn("Start Batch Scan", "white", "#28a745");

    startBtn.onclick = async () => {
      const scope = container.querySelector('input[name="scope"]:checked').value;
      document.body.removeChild(overlay);

      for (let i = 0; i < selectedLibs.length; i++) {
        const lib = selectedLibs[i];
        const isLast = i === selectedLibs.length - 1;
        const result = await runSizeReportParallel(lib.title, lib.url, scope, i + 1, selectedLibs.length);
        if (result === "CANCELLED") break;
        if (!isLast) await sleep(1500);
      }
    };

    btnBox.appendChild(backBtn);
    btnBox.appendChild(startBtn);
    container.appendChild(btnBox);
  }

  async function runSizeReportParallel(libraryName, finalPath, scope, currentIdx, totalIdx) {
    let isStopping = false;
    let isCancelled = false;

    const { overlay: prgOverlay, container: prgContainer } = createModal(`Scanning Progress [${currentIdx}/${totalIdx}]`);
    prgContainer.parentElement.style.width = "550px";
    prgContainer.innerHTML = `
      <div id="stTxt" style="font-weight:bold;color:#0078d4;margin-bottom:5px;">Current: ${libraryName}</div>
      <div id="fTxt" style="font-size:11px;margin-bottom:10px;height:1.5em;overflow:hidden;text-overflow:ellipsis;color:#666;">Initializing...</div>
      <div style="width:100%;background:#eee;height:14px;border-radius:7px;overflow:hidden;margin-bottom:10px;border:1px solid #ddd;">
        <div id="pBar" style="width:0%;height:100%;background:linear-gradient(90deg,#28a745,#5cd65c);transition:width 0.3s;"></div>
      </div>
      <div id="stat" style="font-size:12px;color:#444;margin-bottom:15px;background:#f9f9f9;padding:8px;border-radius:4px;">Files Found: 0 | Folders: 0/0</div>
      <div style="display:flex;justify-content:center;gap:10px;">
        <button id="stopBtn" style="padding:8px 16px;cursor:pointer;border-radius:4px;border:1px solid #ffc107;background:#fff;color:#856404;font-weight:bold;">Stop & Save This Lib</button>
        <button id="cancelBtn" style="padding:8px 16px;cursor:pointer;border-radius:4px;border:1px solid #dc3545;background:#dc3545;color:white;font-weight:bold;">Stop All Tasks</button>
      </div>
    `;

    const stTxt = prgContainer.querySelector("#stTxt");
    const fTxt = prgContainer.querySelector("#fTxt");
    const pBar = prgContainer.querySelector("#pBar");
    const stat = prgContainer.querySelector("#stat");

    prgContainer.querySelector("#stopBtn").onclick = (e) => {
      isStopping = true;
      e.target.disabled = true;
      stTxt.textContent = "Finalizing Current Library...";
    };

    prgContainer.querySelector("#cancelBtn").onclick = () => {
      if (confirm("Stop all tasks and return to main menu? Data for current library will be lost.")) {
        isCancelled = true;
        document.body.removeChild(prgOverlay);
      }
    };

    let logs = [];
    let foldersToProcess = [finalPath];
    let processedFoldersCount = 0;
    let activeWorkers = 0;

    const updateUI = () => {
      if (isCancelled) return;
      const total = foldersToProcess.length;
      const percent = total > 0 ? Math.floor((processedFoldersCount / total) * 100) : 0;
      pBar.style.width = percent + "%";
      stat.textContent = `Files Found: ${logs.length} | Folders: ${processedFoldersCount}/${total}`;
    };

    async function processFolder(currentPath) {
      if (isStopping || isCancelled) return;
      activeWorkers++;
      fTxt.textContent = `Scanning: ${currentPath}`;

      try {
        const safePath = escapeOData(currentPath);
        let fileUrl = `${siteUrl}/_api/web/GetFolderByServerRelativeUrl(@target)/Files?@target='${encodeURIComponent(safePath)}'&$select=Name,Length,ServerRelativeUrl,TimeLastModified,Versions/Size,Versions/Created&$expand=Versions&$top=${BATCH_SIZE}`;

        while (fileUrl && !isStopping && !isCancelled) {
          const res = await fetchWithRetry(fileUrl, { headers: { "Accept": "application/json;odata=verbose" } });
          if (!res || !res.ok) break;
          const data = await res.json();

          data.d.results.forEach(file => {
            const currentSize = parseInt(file.Length || 0, 10);
            const versions = (file.Versions && file.Versions.results) ? file.Versions.results : [];
            const versionsSize = versions.reduce((sum, v) => sum + parseInt(v.Size || 0, 10), 0);
            const sortedVersions = versions.slice().sort((a, b) => new Date(a.Created) - new Date(b.Created));
            const firstHistoryVersionDate = sortedVersions.length > 0 ? formatThaiDateTime(sortedVersions[0].Created) : "";
            const lastOriginalVersionDate = formatThaiDateTime(file.TimeLastModified);

            logs.push({
              "Scanned At": getThaiTime(),
              "Library": libraryName,
              "File Name": file.Name,
              "Extension": file.Name.includes('.') ? file.Name.split('.').pop().toLowerCase() : '',
              "Folder Path": currentPath,
              "Current Size (MB)": (currentSize / 1048576).toFixed(3),
              "Version Count": versions.length,
              "Versions Size (MB)": (versionsSize / 1048576).toFixed(3),
              "Total Size (MB)": ((currentSize + versionsSize) / 1048576).toFixed(3),
              "Last Datetime of Original Version": lastOriginalVersionDate,
              "First Datetime of History Version": firstHistoryVersionDate
            });
          });

          fileUrl = data.d.__next;
        }

        if (scope === "allfolders" && !isStopping && !isCancelled) {
          const subs = await getSubFolders(currentPath);
          subs.forEach(s => {
            if (!foldersToProcess.includes(s.url)) foldersToProcess.push(s.url);
          });
        }
      } catch (e) {
        console.error("Error folder:", currentPath, e);
      }

      processedFoldersCount++;
      activeWorkers--;
      updateUI();
    }

    async function monitorQueue() {
      while (processedFoldersCount < foldersToProcess.length || activeWorkers > 0) {
        if (isCancelled) return;
        if (isStopping && activeWorkers === 0) break;

        if (!isStopping && activeWorkers < CONCURRENCY_LIMIT && (processedFoldersCount + activeWorkers < foldersToProcess.length)) {
          const nextIndex = processedFoldersCount + activeWorkers;
          const targetPath = foldersToProcess[nextIndex];
          if (targetPath) {
            processFolder(targetPath);
            await sleep(50);
          }
        }

        await sleep(100);
      }
    }

    await monitorQueue();

    if (!isCancelled && logs.length > 0) {
      const suffix = getFileSuffix();
      const finalFileName = `${isStopping ? 'Partial_' : ''}ScanSize_${libraryName}_Report_${suffix}.csv`;
      const csvContent = "\ufeff" + [
        Object.keys(logs[0]).join(","),
        ...logs.map(l => Object.values(l).map(v => `"${String(v).replace(/"/g, '""')}"`).join(","))
      ].join("\n");

      const saveResult = await saveCsvToInitialReceive(csvContent, finalFileName);
      stTxt.textContent = `Saved: ${saveResult.path}`;
    }

    if (document.body.contains(prgOverlay)) document.body.removeChild(prgOverlay);

    if (isCancelled) return "CANCELLED";
    if (currentIdx === totalIdx) {
      alert(`Successfully completed.\nLast Library: ${libraryName}\nFiles were saved to Data\\\\Initial_Receive.`);
      showStep1();
    }
    return "DONE";
  }

  showStep1();
})();
"""

        cleanup_scan_logic = r"""
(async () => {
  const siteUrl = "https://accor.sharepoint.com/sites/H6323_SPOF";

  function escapeOData(str) {
    return str ? str.replace(/'/g, "''") : "";
  }

  const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

  async function saveCsvToInitialReceive(csvContent, fileName) {
    if (!(window.pywebview && window.pywebview.api && window.pywebview.api.save_sharepoint_inventory_csv_auto)) {
      throw new Error("Desktop save bridge is not available.");
    }

    const saveResult = await window.pywebview.api.save_sharepoint_inventory_csv_auto(csvContent, fileName);
    if (!saveResult || !saveResult.success) {
      throw new Error(saveResult && saveResult.error ? saveResult.error : "Unable to auto-save CSV.");
    }
    return saveResult;
  }

  async function getFreshDigest() {
    try {
      const res = await fetch(`${siteUrl}/_api/contextinfo`, {
        method: "POST",
        headers: { "Accept": "application/json;odata=verbose" }
      });
      const data = await res.json();
      return data.d.GetContextWebInformation.FormDigestValue;
    } catch (e) {
      console.error("Failed to refresh digest token", e);
      return null;
    }
  }

  async function fetchWithRetry(url, options = {}, retries = 5) {
    for (let i = 0; i < retries; i++) {
      const res = await fetch(url, options);
      if (res.status === 429 || res.status === 503) {
        const retryAfter = res.headers.get("Retry-After") || 5;
        await sleep(retryAfter * 1000);
        continue;
      }
      return res;
    }
    return null;
  }

  function getThaiTimeParts() {
    const now = new Date();
    const tzOffset = 7 * 60 * 60 * 1000;
    const d = new Date(now.getTime() + tzOffset);
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, '0');
    const day = String(d.getUTCDate()).padStart(2, '0');
    const hh = String(d.getUTCHours()).padStart(2, '0');
    const mm = String(d.getUTCMinutes()).padStart(2, '0');

    return {
      fullStamp: d.toISOString().replace('Z', '').replace('T', ' ').split('.')[0],
      fileSuffix: `${y}${m}${day}_${hh}${mm}`
    };
  }


  async function getLibraries() {
    const res = await fetchWithRetry(`${siteUrl}/_api/web/lists?$filter=BaseTemplate eq 101 and Hidden eq false&$expand=RootFolder`, {
      headers: { "Accept": "application/json;odata=verbose" }
    });
    const data = await res.json();
    return data.d.results
      .map(l => ({ title: l.Title, url: l.RootFolder.ServerRelativeUrl }))
      .filter(lib => !["Form Templates", "Site Assets", "Style Library"].includes(lib.title))
      .sort((a, b) => a.title.localeCompare(b.title));
  }

  async function getSubFolders(folderUrl) {
    try {
      const safePath = escapeOData(folderUrl);
      const endpoint = `${siteUrl}/_api/web/GetFolderByServerRelativeUrl(@target)/folders?@target='${encodeURIComponent(safePath)}'&$filter=Name ne 'Forms'`;
      const res = await fetchWithRetry(endpoint, {
        headers: { "Accept": "application/json;odata=verbose" }
      });
      if (!res || !res.ok) return [];
      const data = await res.json();
      return data.d.results.map(f => ({ name: f.Name, url: f.ServerRelativeUrl })).sort((a, b) => a.name.localeCompare(b.name));
    } catch (e) {
      return [];
    }
  }

  function createModal(titleText) {
    const existing = document.querySelector(".sp-cleanup-overlay");
    if (existing) document.body.removeChild(existing);

    const overlay = document.createElement("div");
    overlay.className = "sp-cleanup-overlay";
    overlay.style = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.4);display:flex;justify-content:center;align-items:center;z-index:10000;";

    const modal = document.createElement("div");
    modal.style = "background:white;padding:25px;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,0.3);width:950px;max-height:90vh;overflow-y:auto;font-family:'Segoe UI',Tahoma,sans-serif;display:flex;flex-direction:column;";

    const title = document.createElement("div");
    title.textContent = titleText;
    title.style = "font-weight:bold;margin-bottom:15px;font-size:18px;color:#0078d4;border-bottom:2px solid #0078d4;padding-bottom:8px;";

    const container = document.createElement("div");
    container.style = "flex-grow:1; overflow-y:auto;";

    modal.appendChild(title);
    modal.appendChild(container);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    return { overlay, container };
  }

  function createBtn(text, color, bgColor) {
    const btn = document.createElement("button");
    btn.textContent = text;
    btn.style = `padding:8px 16px;border:none;border-radius:4px;cursor:pointer;font-weight:bold;color:${color};background:${bgColor};transition:opacity 0.2s;font-size:13px;`;
    btn.onmouseover = () => btn.style.opacity = "0.8";
    btn.onmouseout = () => btn.style.opacity = "1";
    return btn;
  }

  async function showStep1() {
    const libraries = await getLibraries();
    const { overlay, container } = createModal("Step 1: Select Libraries (Cleanup Mode)");

    const utilBox = document.createElement("div");
    utilBox.style = "margin-bottom:15px;display:flex;gap:10px;align-items:center;";
    const selAll = createBtn("Select All", "#0078d4", "#f0f7ff");
    const deSelAll = createBtn("Deselect All", "#666", "#eee");
    const counter = document.createElement("span");
    counter.id = "sel-count";
    counter.textContent = "Selected: 0";
    counter.style = "font-size:14px;color:#555;margin-left:auto;font-weight:600;";

    utilBox.appendChild(selAll);
    utilBox.appendChild(deSelAll);
    utilBox.appendChild(counter);
    container.appendChild(utilBox);

    const listDiv = document.createElement("div");
    listDiv.style = "display:grid;grid-template-columns:repeat(3,1fr);gap:10px 15px;border:1px solid #ddd;padding:15px;border-radius:6px;max-height:600px;overflow-y:auto;margin-bottom:20px;background:#fafafa;";

    libraries.forEach(lib => {
      const lbl = document.createElement("label");
      lbl.style = "display:flex;align-items:center;cursor:pointer;font-size:15px;padding:10px;border-radius:4px;transition:0.2s;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
      lbl.title = lib.title;
      lbl.onmouseover = () => lbl.style.background = "#eef4fb";
      lbl.onmouseout = () => lbl.style.background = "transparent";

      const chk = document.createElement("input");
      chk.type = "checkbox";
      chk.className = "lib-chk";
      chk.value = lib.url;
      chk.dataset.title = lib.title;
      chk.style = "margin-right:12px;cursor:pointer;flex-shrink:0;transform:scale(1.4);";
      chk.onchange = () => {
        const count = container.querySelectorAll('.lib-chk:checked').length;
        counter.textContent = `Selected: ${count}`;
      };

      lbl.appendChild(chk);
      lbl.appendChild(document.createTextNode(lib.title));
      listDiv.appendChild(lbl);
    });

    container.appendChild(listDiv);

    selAll.onclick = () => {
      container.querySelectorAll('.lib-chk').forEach(c => c.checked = true);
      counter.textContent = `Selected: ${libraries.length}`;
    };

    deSelAll.onclick = () => {
      container.querySelectorAll('.lib-chk').forEach(c => c.checked = false);
      counter.textContent = "Selected: 0";
    };

    const btnBox = document.createElement("div");
    btnBox.style = "display:flex;justify-content:flex-end;gap:10px;padding-top:10px;border-top:1px solid #eee;";
    const cancelBtn = createBtn("Cancel", "#333", "#eee");
    const nextBtn = createBtn("Next", "white", "#0078d4");

    cancelBtn.onclick = () => document.body.removeChild(overlay);
    nextBtn.onclick = () => {
      const selected = Array.from(container.querySelectorAll('.lib-chk:checked')).map(c => ({ title: c.dataset.title, url: c.value }));
      if (selected.length === 0) {
        alert("Please select at least one library.");
        return;
      }
      document.body.removeChild(overlay);
      showStep2Multi(selected);
    };

    btnBox.appendChild(cancelBtn);
    btnBox.appendChild(nextBtn);
    container.appendChild(btnBox);
  }

  async function showStep2Multi(selectedLibs) {
    const { overlay, container } = createModal(`Step 2: Scope for ${selectedLibs.length} Libraries`);
    const libListPreview = selectedLibs.map(l => `<span style="display:inline-block;background:#e1f5fe;padding:2px 8px;border-radius:10px;font-size:11px;margin:2px;border:1px solid #b3e5fc;">${l.title}</span>`).join("");

    container.innerHTML = `
      <div style="margin-bottom:15px;max-height:80px;overflow-y:auto;padding:5px;border:1px solid #eee;border-radius:4px;">
        <div style="font-size:11px;font-weight:bold;color:#666;margin-bottom:4px;">Selected Libraries:</div>
        ${libListPreview}
      </div>
      <div style="margin-bottom:15px;">
        <label style="display:block;margin-bottom:8px;font-weight:600;cursor:pointer;"><input type="radio" name="scope" value="allfolders" style="transform:scale(1.2); margin-right:8px;" checked> Clean All Folders (Recursive)</label>
        <label style="display:block;margin-bottom:8px;font-weight:600;cursor:pointer;"><input type="radio" name="scope" value="allfiles" style="transform:scale(1.2); margin-right:8px;"> Files in Root Only</label>
      </div>
      <div style="background:#f9f9f9;padding:12px;border-radius:6px;border-left:4px solid #4caf50;font-size:12px;margin-bottom:20px;color:#444;">
        <div style="font-weight:bold;margin-bottom:4px;color:#2e7d32;">Applied Policy:</div>
        • <b>Older than 365 days:</b> Keep 0 versions<br>
        • <b>Older than 90 days:</b> Keep 4 versions<br>
        • <b>Large files (>300MB) & Older than 30 days:</b> Keep 4 versions
      </div>
    `;

    const btnBox = document.createElement("div");
    btnBox.style = "display:flex;justify-content:space-between;gap:10px;";
    const backBtn = createBtn("Back", "#333", "#eee");
    const startBtn = createBtn(`Start Cleanup (${selectedLibs.length})`, "white", "#28a745");

    backBtn.onclick = () => {
      document.body.removeChild(overlay);
      showStep1();
    };

    startBtn.onclick = async () => {
      const scopeValue = container.querySelector('input[name="scope"]:checked').value;
      document.body.removeChild(overlay);
      for (let i = 0; i < selectedLibs.length; i++) {
        const result = await runCleanup(selectedLibs[i].title, selectedLibs[i].url, scopeValue, i + 1, selectedLibs.length);
        if (result === "STOP_ALL") break;
        await sleep(1000);
      }
    };

    btnBox.appendChild(backBtn);
    btnBox.appendChild(startBtn);
    container.appendChild(btnBox);
  }

  async function runCleanup(libraryTitle, libraryUrl, selectedScope, currentIdx, totalIdx) {
    let cancelled = false;
    let stopAll = false;
    const { overlay: prgOverlay, container: prgContainer } = createModal(`Processing [${currentIdx}/${totalIdx}]`);

    prgContainer.innerHTML = `
      <div id="libTitle" style="font-weight:bold;color:#0078d4;margin-bottom:10px;">Library: ${libraryTitle}</div>
      <div id="stTxt" style="font-size:13px;font-weight:bold;margin-bottom:5px;">Initializing...</div>
      <div id="fTxt" style="font-size:11px;margin-bottom:10px;height:1.5em;overflow:hidden;text-overflow:ellipsis;color:#666;">Waiting...</div>
      <div style="width:100%;background:#eee;height:14px;border-radius:7px;overflow:hidden;margin-bottom:10px;border:1px solid #ddd;">
        <div id="pBar" style="width:0%;height:100%;background:linear-gradient(90deg,#28a745,#5cd65c);transition:width 0.3s;"></div>
      </div>
      <div id="stat" style="font-size:12px;color:#444;margin-bottom:15px;background:#f9f9f9;padding:8px;border-radius:4px;">Folders: 0 | Saved: 0.00 MB</div>
      <div style="text-align:center;display:flex;gap:10px;justify-content:center;">
        <button id="skipBtn" style="padding:6px 12px;cursor:pointer;border-radius:4px;border:1px solid #ff9800;background:white;color:#e65100;font-size:11px;font-weight:bold;">Skip This Lib</button>
        <button id="stopAllBtn" style="padding:6px 12px;cursor:pointer;border-radius:4px;border:1px solid #dc3545;background:white;color:#dc3545;font-size:11px;font-weight:bold;">Stop All Tasks</button>
      </div>
    `;

    const stTxt = prgContainer.querySelector("#stTxt");
    const fTxt = prgContainer.querySelector("#fTxt");
    const pBar = prgContainer.querySelector("#pBar");
    const stat = prgContainer.querySelector("#stat");

    prgContainer.querySelector("#skipBtn").onclick = () => { if (confirm("ข้าม Library นี้?")) cancelled = true; };
    prgContainer.querySelector("#stopAllBtn").onclick = () => { if (confirm("หยุดการทำงานทั้งหมด?")) { cancelled = true; stopAll = true; } };

    const POLICIES = [
      { days: 365, keep: 0, name: "Retention 365 Days" },
      { days: 90, keep: 4, name: "Retention 90 Days" }
    ];
    const SIZE_LIMIT_MB = 300;
    const SIZE_KEEP = 4;
    const SIZE_AGE_THRESHOLD = 30;

    let logs = [];
    let totalSavedMB = 0;
    const nowUTC = new Date();
    let digest = await getFreshDigest();
    let lastTokenTime = Date.now();
    let foldersToProcess = [libraryUrl];
    let processedFoldersCount = 0;
    let activeWorkers = 0;
    const CONCURRENCY_LIMIT = 3;

    const updateUI = (fileName = "") => {
      const total = foldersToProcess.length;
      const percent = total > 0 ? Math.floor((processedFoldersCount / total) * 100) : 0;
      pBar.style.width = percent + "%";
      if (fileName) fTxt.textContent = `File: ${fileName}`;
      stat.textContent = `Folders: ${processedFoldersCount}/${total} | Saved: ${totalSavedMB.toFixed(2)} MB`;
    };

    async function processSingleFolder(currentPath) {
      if (cancelled) return;
      activeWorkers++;
      try {
        const safePath = escapeOData(currentPath);
        let url = `${siteUrl}/_api/web/GetFolderByServerRelativeUrl(@target)/Files?@target='${encodeURIComponent(safePath)}'&$expand=Versions&$top=5000`;

        while (url && !cancelled) {
          const res = await fetchWithRetry(url, { headers: { "Accept": "application/json;odata=verbose" } });
          if (!res || !res.ok) break;
          const data = await res.json();
          for (const file of data.d.results) {
            if (cancelled) break;
            updateUI(file.Name);

            if (!file.Versions || file.Versions.results.length === 0) continue;

            if (Date.now() - lastTokenTime > 15 * 60 * 1000) {
              digest = await getFreshDigest();
              lastTokenTime = Date.now();
            }

            const vRes = await fetchWithRetry(`${siteUrl}/_api/web/GetFileById(guid'${file.UniqueId}')/versions`, {
              headers: { "Accept": "application/json;odata=verbose" }
            });
            if (!vRes || !vRes.ok) continue;

            const versions = (await vRes.json()).d.results;
            versions.sort((a, b) => new Date(a.Created) - new Date(b.Created));

            const currentSizeMB = file.Length / (1024 * 1024);
            const historyVersionSizeMB = versions.reduce((s, v) => s + (v.Size || 0), 0) / (1024 * 1024);
            const totalPreMB = currentSizeMB + historyVersionSizeMB;

            let keepCount = versions.length;
            let policyName = "None";
            const oldestAge = versions.length > 0 ? Math.floor((nowUTC - new Date(versions[0].Created)) / 86400000) : 0;

            let isMatched = false;
            for (const p of POLICIES) {
              if (oldestAge > p.days) {
                keepCount = p.keep;
                policyName = p.name;
                isMatched = true;
                break;
              }
            }

            if (!isMatched && totalPreMB > SIZE_LIMIT_MB && oldestAge > SIZE_AGE_THRESHOLD) {
              keepCount = SIZE_KEEP;
              policyName = "Large File Policy";
              isMatched = true;
            }

            let deletedCount = 0;
            let deletedSizeMB = 0;

            if (versions.length > keepCount) {
              const toDelete = versions.slice(0, versions.length - keepCount);
              for (const v of toDelete) {
                if (cancelled) break;
                const delReq = await fetchWithRetry(`${siteUrl}/_api/web/GetFileById(guid'${file.UniqueId}')/versions(${v.ID})`, {
                  method: "POST",
                  headers: {
                    "X-HTTP-Method": "DELETE",
                    "X-RequestDigest": digest,
                    "IF-MATCH": "*"
                  }
                });

                if (delReq && delReq.ok) {
                  deletedCount++;
                  deletedSizeMB += (v.Size || 0) / (1024 * 1024);
                }
                await sleep(50);
              }
            }

            totalSavedMB += deletedSizeMB;

            if (deletedCount > 0) {
              logs.push({
                Timestamp: getThaiTimeParts().fullStamp,
                File: file.Name,
                Folder: currentPath,
                CurrentSizeMB: currentSizeMB.toFixed(2),
                HistoryVersionsMB: historyVersionSizeMB.toFixed(2),
                TotalOriginalMB: totalPreMB.toFixed(2),
                VersionsFound: versions.length,
                PolicyApplied: policyName,
                VersionsDeleted: deletedCount,
                SpaceSavedMB: deletedSizeMB.toFixed(2),
                FinalSizeMB: (totalPreMB - deletedSizeMB).toFixed(2)
              });
            }
          }
          url = data.d.__next;
        }

        if (selectedScope !== "allfiles" && !cancelled) {
          const subDirs = await getSubFolders(currentPath);
          for (const s of subDirs) {
            if (!foldersToProcess.includes(s.url)) foldersToProcess.push(s.url);
          }
        }
      } catch (e) {
        console.error(e);
      }

      processedFoldersCount++;
      activeWorkers--;
      updateUI();
    }

    async function startQueue() {
      while (processedFoldersCount < foldersToProcess.length || activeWorkers > 0) {
        if (cancelled) break;
        if (activeWorkers < CONCURRENCY_LIMIT && (processedFoldersCount + activeWorkers < foldersToProcess.length)) {
          processSingleFolder(foldersToProcess[processedFoldersCount + activeWorkers]);
          await sleep(200);
        }
        await sleep(100);
      }
    }

    await startQueue();

    const timeData = getThaiTimeParts();
    const csvHeaderList = ["Timestamp", "File", "Folder", "CurrentSizeMB", "HistoryVersionsMB", "TotalOriginalMB", "VersionsFound", "PolicyApplied", "VersionsDeleted", "SpaceSavedMB", "FinalSizeMB"];
    const csvHeaders = csvHeaderList.join(",");
    let csvRows = "";

    if (logs.length > 0) {
      csvRows = logs.map(l => csvHeaderList.map(h => `"${String(l[h] || "").replace(/"/g, '""')}"`).join(",")).join("\n");
    } else {
      const emptyData = {
        Timestamp: timeData.fullStamp,
        File: "N/A (No modifications)",
        Folder: libraryUrl,
        CurrentSizeMB: "0.00",
        HistoryVersionsMB: "0.00",
        TotalOriginalMB: "0.00",
        VersionsFound: "0",
        PolicyApplied: "None",
        VersionsDeleted: "0",
        SpaceSavedMB: "0.00",
        FinalSizeMB: "0.00"
      };
      csvRows = csvHeaderList.map(h => `"${String(emptyData[h]).replace(/"/g, '""')}"`).join(",");
    }

    const safeLibraryTitle = libraryTitle.replace(/[\\/:*?"<>|]/g, '_');
    const csvContent = "\ufeff" + csvHeaders + "\n" + csvRows;
    const saveResult = await saveCsvToInitialReceive(csvContent, `Cleanup_Report_${safeLibraryTitle}_${timeData.fileSuffix}.csv`);
    stTxt.textContent = `Saved: ${saveResult.path}`;

    if (document.body.contains(prgOverlay)) document.body.removeChild(prgOverlay);
    if (stopAll) return "STOP_ALL";
    if (currentIdx === totalIdx) {
      alert("Cleanup task completed for all selected libraries. Files were saved to Data\\Initial_Receive.");
      showStep1();
    }
    return "DONE";
  }

  showStep1();
})();
"""

        scan_logic_json = json.dumps(scan_logic)
        version_scan_logic_json = json.dumps(version_scan_logic)
        cleanup_scan_logic_json = json.dumps(cleanup_scan_logic)
        site_url_json = json.dumps(self.SHAREPOINT_SITE_URL)

        return f"""
(function() {{
  const siteUrl = {site_url_json};
  const currentUrl = window.location.href;
  const isTargetSite = currentUrl.startsWith(siteUrl);
  const existing = document.getElementById('spof-launcher-root');
  if (existing) existing.remove();

  if (!isTargetSite) {{
    return {{
      installed: false,
      page: currentUrl,
      reason: 'not-target-site'
    }};
  }}

  const root = document.createElement('div');
  root.id = 'spof-launcher-root';
  root.style.cssText = 'position:fixed;right:24px;bottom:24px;z-index:9999;font-family:Segoe UI,sans-serif;';

  root.innerHTML = `
    <div id="spof-main-card" style="background:linear-gradient(135deg,#0f172a,#1e3a8a);color:#fff;padding:14px 16px;border-radius:16px;box-shadow:0 18px 40px rgba(15,23,42,.28);width:320px;display:block;">
      <div style="font-size:12px;opacity:.8;letter-spacing:.08em;text-transform:uppercase;">SPOF Helper</div>
      <div style="font-size:16px;font-weight:700;margin-top:6px;">SharePoint Scan Tools</div>
      <div style="font-size:12px;line-height:1.5;opacity:.9;margin-top:6px;">เลือกโหมดสแกนหรือ cleanup ได้จากปุ่มด้านล่าง โดยไฟล์ CSV จะถูกเซฟลง Initial_Receive อัตโนมัติ</div>
      <div style="display:flex;flex-direction:column;gap:8px;margin-top:12px;">
        <button id="spof-run-inventory-btn" style="border:none;background:#38bdf8;color:#082f49;padding:10px 12px;border-radius:10px;font-weight:700;cursor:pointer;">Run Library Inventory</button>
        <button id="spof-run-version-scan-btn" style="border:none;background:#22c55e;color:#052e16;padding:10px 12px;border-radius:10px;font-weight:700;cursor:pointer;">Run Full Version Scan</button>
        <button id="spof-run-cleanup-scan-btn" style="border:none;background:#f59e0b;color:#431407;padding:10px 12px;border-radius:10px;font-weight:700;cursor:pointer;">Run Version Cleanup Policy</button>
        <button id="spof-hide-launcher-btn" style="border:none;background:rgba(255,255,255,.16);color:#fff;padding:10px 12px;border-radius:10px;font-weight:600;cursor:pointer;">Hide</button>
      </div>
    </div>

    <div id="spof-mini-launcher" 
         title="Click to open SPOF Helper" 
         style="display:none; background:#1e3a8a; color:#fff; width:56px; height:56px; border-radius:50%; box-shadow:0 8px 24px rgba(0,0,0,0.3); cursor:pointer; display:none; align-items:center; justify-content:center; font-weight:bold; font-size:11px; border:2px solid #38bdf8; text-align:center; line-height:1.2; padding:4px; box-sizing:border-box; transition:all 0.2s ease;">
       SPOF<br>Script
    </div>
  `;

  document.body.appendChild(root);

  const mainCard = document.getElementById('spof-main-card');
  const miniLauncher = document.getElementById('spof-mini-launcher');

  // Logic การซ่อน/แสดง
  document.getElementById('spof-hide-launcher-btn').onclick = () => {{
    mainCard.style.display = 'none';
    miniLauncher.style.display = 'flex';
  }};

  miniLauncher.onclick = () => {{
    mainCard.style.display = 'block';
    miniLauncher.style.display = 'none';
  }};

// Effect ตอนเอาเมาส์ชี้ปุ่มจิ๋ว
  miniLauncher.onmouseover = () => {{
    miniLauncher.style.transform = 'scale(1.1)';
    miniLauncher.style.background = '#38bdf8';
    miniLauncher.style.color = '#082f49';
  }};
  miniLauncher.onmouseout = () => {{
    miniLauncher.style.transform = 'scale(1)';
    miniLauncher.style.background = '#1e3a8a';
    miniLauncher.style.color = '#fff';
  }};
  
  // Logic ปุ่มการทำงานเดิม
  document.getElementById('spof-run-inventory-btn').onclick = async () => {{
    const button = document.getElementById('spof-run-inventory-btn');
    const original = button.textContent;
    button.disabled = true;
    button.textContent = 'Running...';
    try {{
      const runScan = eval({scan_logic_json});
      await runScan;
    }} finally {{
      button.disabled = false;
      button.textContent = original;
    }}
  }};

  document.getElementById('spof-run-version-scan-btn').onclick = async () => {{
    const button = document.getElementById('spof-run-version-scan-btn');
    const original = button.textContent;
    button.disabled = true;
    button.textContent = 'Preparing...';
    try {{
      const runVersionScan = eval({version_scan_logic_json});
      await runVersionScan;
    }} finally {{
      button.disabled = false;
      button.textContent = original;
    }}
  }};

  document.getElementById('spof-run-cleanup-scan-btn').onclick = async () => {{
    const button = document.getElementById('spof-run-cleanup-scan-btn');
    const original = button.textContent;
    button.disabled = true;
    button.textContent = 'Preparing...';
    try {{
      const runCleanupScan = eval({cleanup_scan_logic_json});
      await runCleanupScan;
    }} finally {{
      button.disabled = false;
      button.textContent = original;
    }}
  }};

  return {{
    installed: true,
    page: currentUrl
  }};
}})();
"""

    def _attach_sharepoint_window_handlers(self, window):
        def inject_launcher(window):
            try:
                window.evaluate_js(self._sharepoint_launcher_js)
            except Exception:
                pass

        def clear_reference():
            if self._sharepoint_window is window:
                self._sharepoint_window = None

        window.events.loaded += inject_launcher
        window.events.closed += clear_reference

    def open_sharepoint_inventory_window(self):
        try:
            if self._sharepoint_window is not None:
                try:
                    self._sharepoint_window.restore()
                except Exception:
                    pass

                try:
                    self._sharepoint_window.show()
                except Exception:
                    pass

                try:
                    self._sharepoint_window.load_url(self.SHAREPOINT_SITE_URL)
                except Exception:
                    pass

                return {
                    "status": "success",
                    "message": "SharePoint scanner window is already open.",
                    "siteUrl": self.SHAREPOINT_SITE_URL,
                }

            window = webview.create_window(
                'SharePoint Inventory Scanner',
                url=self.SHAREPOINT_SITE_URL,
                js_api=self,
                width=1440,
                height=920,
                resizable=True,
                text_select=True
            )
            self._sharepoint_window = window
            self._attach_sharepoint_window_handlers(window)

            return {
                "status": "success",
                "message": "Opened SharePoint scanner window.",
                "siteUrl": self.SHAREPOINT_SITE_URL,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def save_sharepoint_inventory_csv(self, csv_content, suggested_name):
        try:
            root_path = self.get_data_root()
            initial_dir = os.path.join(root_path, "Data")
            os.makedirs(initial_dir, exist_ok=True)

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            file_path = filedialog.asksaveasfilename(
                title="Save SharePoint Inventory Report",
                initialdir=initial_dir,
                initialfile=suggested_name or "SharePoint_Report.csv",
                defaultextension=".csv",
                filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
            )
            root.destroy()

            if not file_path:
                return {"success": False, "cancelled": True}

            with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(csv_content or "")

            return {"success": True, "path": file_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_sharepoint_inventory_csv_auto(self, csv_content, suggested_name):
        try:
            root_path = self.get_data_root()
            target_dir = os.path.join(root_path, "Data", "Initial_Receive")
            os.makedirs(target_dir, exist_ok=True)

            file_name = suggested_name or "SharePoint_Report.csv"
            file_path = os.path.join(target_dir, file_name)

            with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(csv_content or "")

            return {"success": True, "path": file_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

def get_entrypoint():
    if getattr(sys, 'frozen', False):
        # PyInstaller จะเก็บ ui ไว้ใน _MEIPASS/ui
        return os.path.join(sys._MEIPASS, 'ui', 'index.html')
    # ถ้าเป็น Dev: src อยู่ในโปรเจกต์คู่กับ ui
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'ui', 'index.html'))

if __name__ == '__main__':
    api = EnhancedApi()
    entry = get_entrypoint()
    
    window = webview.create_window(
        'SPOF Management System',
        url=entry,
        js_api=api,
        width=1500,
        height=1000,
        text_select=True
    )
    api.set_window(window)
    webview.start(func=window.maximize)
