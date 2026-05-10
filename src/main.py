import webview
import os
import sys
import shutil
import glob
from bridge import SharePointApi 
from sharepoint_launcher import build_sharepoint_launcher_js
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
        return build_sharepoint_launcher_js(self.SHAREPOINT_SITE_URL)

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
