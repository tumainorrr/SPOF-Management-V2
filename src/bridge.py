import os
import sys
import pandas as pd
import re
import shutil
import tkinter as tk
from tkinter import filedialog
import os

class SharePointApi:
    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def _get_base_path(self):
        # วิธีหา Path ที่เสถียรที่สุดสำหรับ PyInstaller
        if getattr(sys, 'frozen', False):
            # ถ้าเป็น .exe ให้ใช้ Path ของไฟล์ executable โดยตรง
            return os.path.dirname(os.path.realpath(sys.argv[0]))
        # ถ้าเป็น .py ปกติ ให้ถอยออกไป 1 ชั้นจาก src
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _is_supported_import_filename(self, filename):
        if not filename or not filename.lower().endswith('.csv'):
            return False

        supported_patterns = [
            r"^SharePoint_Report_\d{8}_\d{4}\.csv$",
            r"^ScanSize_(?:DPT-[A-Za-z0-9-]+|Forum)_Report_\d{8}_\d{4}\.csv$",
            r"^Cleanup_Report_(?:DPT-[A-Za-z0-9-]+|Forum)_\d{8}_\d{4}\.csv$",
        ]

        return any(re.fullmatch(pattern, filename) for pattern in supported_patterns)

    def sync_department_data():
        base_path = "Data"
        folders = {
            "new": os.path.join(base_path, "Initial_Receive"),
            "after": os.path.join(base_path, "Current_Scan_Detail"),
            "before": os.path.join(base_path, "Previous_Scan_Detail"),
            "backup": os.path.join(base_path, "Backup")
        }

        # เช็คว่ามีโฟลเดอร์ครบไหม ถ้าไม่มีให้สร้าง (ป้องกัน Error)
        for path in folders.values():
            os.makedirs(path, exist_ok=True)

        new_files = glob.glob(os.path.join(folders["new"], "ScanSize_*_Report_*.csv"))
        
        if not new_files:
            return "No new data to sync."

        for filepath in new_files:
            try:
                filename = os.path.basename(filepath)
                dept_tag = filename.split('_')[1] 

                # 1. Move BEFORE -> BACKUP (ใส่ Timestamp ป้องกันชื่อซ้ำ)
                old_before = glob.glob(os.path.join(folders["before"], f"ScanSize_{dept_tag}_Report__*.csv"))
                for f in old_before:
                    ts = int(time.time())
                    shutil.move(f, os.path.join(folders["backup"], f"{ts}_{os.path.basename(f)}"))

                # 2. Move AFTER -> BEFORE
                current_after = glob.glob(os.path.join(folders["after"], f"ScanSize_{dept_tag}_Report__*.csv"))
                for f in current_after:
                    shutil.move(f, os.path.join(folders["before"], os.path.basename(f)))

                # 3. Move NEW -> AFTER
                shutil.move(filepath, os.path.join(folders["after"], filename))
                
                print(f"✅ [Sync] {dept_tag} updated successfully.")
            
            except Exception as e:
                print(f"❌ [Error] Could not sync {filename}: {str(e)}")

        return "Sync Complete"
            
    def _process_csv(self, path):
        try:
            # พยายามอ่านด้วย UTF-8 ถ้าไม่ได้ให้ใช้ CP1252 (Windows Thai)
            try:
                df = pd.read_csv(path, encoding='utf-8-sig', low_memory=False)
            except:
                df = pd.read_csv(path, encoding='cp1252', low_memory=False)
            
            df.columns = df.columns.str.strip()
            df = df.fillna("-")
            return df.to_dict(orient='records')
            print(f"Columns in CSV: {df.columns.tolist()}")
        except Exception as e:
            print(f"Columns in CSV: {df.columns.tolist()}")
            return {"error": f"อ่านไฟล์ไม่สำเร็จ: {str(e)}"}

    # --- ฟังก์ชันใหม่: ดึงรายชื่อแผนกจากชื่อไฟล์ ---
    def get_available_departments(self, category):
        base_dir = self._get_base_path()
        target_dir = os.path.join(base_dir, "Data", category)
        
        if not os.path.exists(target_dir):
            print(f"Directory not found: {target_dir}") # ดูใน terminal ว่า path ถูกไหม
            return []

        departments = set()
        pattern = r"ScanSize_([A-Za-z0-9-]+)_Report"

        for filename in os.listdir(target_dir):
            match = re.search(pattern, filename)
            if match:
                departments.add(match.group(1))

        return sorted(list(departments)) # ต้องส่งเป็น List กลับไป

    # --- ฟังก์ชันใหม่: ดึงข้อมูลจากไฟล์ล่าสุดของแผนกนั้นๆ ---
    def get_latest_scan_data(self, category, dept_name):
        base_dir = self._get_base_path()
        target_dir = os.path.join(base_dir, "Data", category)
        
        # ค้นหาไฟล์ที่ขึ้นต้นด้วยชื่อแผนกและลงท้ายด้วย .csv
        pattern = f"ScanSize_{dept_name}_Report"
        
        files = [
            os.path.join(target_dir, f) 
            for f in os.listdir(target_dir) 
            if f.startswith(pattern) and f.lower().endswith('.csv')
        ]

        if not files:
            return {"error": f"ไม่พบไฟล์สำหรับแผนก {dept_name}"}

        # เลือกไฟล์ที่แก้ไขล่าสุด (mtime)
        latest_file = max(files, key=os.path.getmtime)
        
        return self._process_csv(latest_file)

    def get_main_dashboard_data(self):
        base_dir = self._get_base_path()
        data_dir = os.path.join(base_dir, "Data")
        
        if not os.path.exists(data_dir): 
            os.makedirs(data_dir)
        
        # 1. ค้นหาไฟล์ SharePoint_Report_*.csv ก่อน (ลำดับความสำคัญสูงสุด)
        sp_files = [
            os.path.join(data_dir, f) for f in os.listdir(data_dir) 
            if f.startswith("SharePoint_Report_") and f.lower().endswith('.csv')
        ]
        
        if sp_files:
            # เลือกไฟล์ SharePoint_Report ที่เพิ่งซิงค์เข้ามาล่าสุด (ดูจากเวลา mtime)
            latest_sp = max(sp_files, key=os.path.getmtime)
            return self._process_csv(latest_sp)

        # 2. ถ้าไม่เจอ SharePoint_Report ให้ลองหาไฟล์ data.csv (เผื่อไว้สำหรับระบบเก่า)
        main_csv = os.path.join(data_dir, "data.csv")
        if os.path.exists(main_csv):
            return self._process_csv(main_csv)

        # 3. ถ้าไม่เจอทั้งสองอย่าง ให้หยิบไฟล์ .csv ใดก็ได้ที่ใหม่ที่สุดในโฟลเดอร์ Data
        all_csv_files = [
            os.path.join(data_dir, f) for f in os.listdir(data_dir) 
            if f.lower().endswith('.csv') and os.path.isfile(os.path.join(data_dir, f))
        ]
        
        if not all_csv_files: 
            return {"error": "ไม่พบไฟล์ข้อมูล (.csv) ในโฟลเดอร์ Data สำหรับแสดงผล Dashboard"}
            
        latest_file = max(all_csv_files, key=os.path.getmtime)
        return self._process_csv(latest_file)

    def get_comparison_data(self, mode, dept_name):
        try:
            base_dir = self._get_base_path()
            
            if mode == "vs_original":
                folder_before = "ScanSizeOriginalFirstTime"
            else:
                folder_before = "Previous_Scan_Detail"
            
            path_before_dir = os.path.join(base_dir, "Data", folder_before)
            path_after_dir = os.path.join(base_dir, "Data", "Current_Scan_Detail")

            files_before = [os.path.join(path_before_dir, f) for f in os.listdir(path_before_dir) 
                            if f.startswith(f"ScanSize_{dept_name}_Report")]
            files_after = [os.path.join(path_after_dir, f) for f in os.listdir(path_after_dir) 
                           if f.startswith(f"ScanSize_{dept_name}_Report")]

            if not files_before or not files_after:
                return {"summary": {}, "chartData": [], "error": "ไม่พบข้อมูลของแผนกที่เลือก"}

            file_before = max(files_before, key=os.path.getmtime)
            file_after = max(files_after, key=os.path.getmtime)

            df_b = pd.read_csv(file_before)
            df_a = pd.read_csv(file_after)

            # --- จุดที่ 1: แก้ไข extract_lib ไม่ให้เป็น Unknown หรือ ROOT พร่ำเพรื่อ ---
            # --- แก้ไข Logic การดึงชื่อ Library ---
            def extract_lib(path):
                if pd.isna(path) or str(path).strip() == "": 
                    return dept_name # รวมเข้ากับชื่อแผนกหลักไปเลย
                
                parts = str(path).split('/')
                
                # ถ้า Path ยาวพอจะหา Library เจอ (ลำดับที่ 3) ให้ใช้ชื่อนั้น
                if len(parts) > 3:
                    return parts[3].strip().upper()
                else:
                    # ถ้าหาไม่เจอ (เป็นไฟล์หน้าแรก) ให้ปัดไปรวมกับชื่อแผนกหลัก
                    return dept_name 

            df_b['Lib'] = df_b['Folder Path'].apply(extract_lib).str.strip().str.upper()
            df_a['Lib'] = df_a['Folder Path'].apply(extract_lib).str.strip().str.upper()

            # เมื่อ Groupby 'Lib' ข้อมูลที่เคยเป็น ROOT หรือ MAIN 
            # จะถูกบวกเข้าไปในยอดของ Library ที่ชื่อเดียวกับแผนกทันที
            df_b_g = df_b.groupby('Lib')['Total Size (MB)'].sum().reset_index()
            df_a_g = df_a.groupby('Lib')['Total Size (MB)'].sum().reset_index()
            
            df_final = pd.merge(df_b_g, df_a_g, on='Lib', how='outer').fillna(0)
            df_final.columns = ['Library Name', 'Before', 'After']

            # คลีนข้อมูลเล็กน้อย ไม่ให้มี Library ชื่อ '0' หรือ 'ROOT' หลุดมา
            df_final = df_final[~df_final['Library Name'].isin(['0', 'ROOT', 'UNKNOWN'])]
            
            # (ตรวจสอบ Log) ตอนนี้ Rows before/after ควรจะเท่ากันแล้ว
            # print(f"Total Rows: {len(df_final)}") 

            df_final['Before'] = (df_final['Before'] / 1024).round(2)
            df_final['After'] = (df_final['After'] / 1024).round(2)

            summary = {
                "totalBefore": float(df_final['Before'].sum()),
                "totalAfter": float(df_final['After'].sum())
            }

            # แสดง Top 10 ตามเดิม
            chart_data = df_final.sort_values(by='Before', ascending=False).head(10)

            return {
                "summary": summary,
                "chartData": chart_data.to_dict(orient='records')
            }
            
        except Exception as e:
            return {"summary": {}, "chartData": [], "error": str(e)}


    def get_after_delete_summary(self):
        """ ดึงไฟล์ล่าสุดของทุกแผนกใน Current_Scan_Detail มาสรุป Current vs Version """
        try:
            base_dir = self._get_base_path()
            target_dir = os.path.join(base_dir, "Data", "Current_Scan_Detail")
            
            if not os.path.exists(target_dir):
                return []

            # 1. หาไฟล์ล่าสุดของแต่ละแผนก (ป้องกันกรณีมีไฟล์ซ้ำวัน)
            latest_files = {}
            pattern = r"ScanSize_([A-Za-z0-9-]+)_Report"
            
            for filename in os.listdir(target_dir):
                match = re.search(pattern, filename)
                if match and filename.lower().endswith('.csv'):
                    dept = match.group(1)
                    full_path = os.path.join(target_dir, filename)
                    # เก็บเฉพาะไฟล์ที่ใหม่ที่สุดของแผนกนั้น
                    if dept not in latest_files or os.path.getmtime(full_path) > os.path.getmtime(latest_files[dept]):
                        latest_files[dept] = full_path

            summary_data = []
            
            # 2. อ่านไฟล์และคำนวณ Size
            for dept, filepath in latest_files.items():
                df = pd.read_csv(filepath)
                # ล้างชื่อ Column เผื่อมี Space
                df.columns = df.columns.str.strip()
                
                current_mb = df['Current Size (MB)'].sum()
                total_mb = df['Total Size (MB)'].sum()
                version_mb = total_mb - current_mb
                
                summary_data.append({
                    "dept": dept.replace("DPT-", ""), # เอาแค่ชื่อแผนก เช่น FO, FB
                    "current": round(current_mb / 1024, 2), # แปลงเป็น GB
                    "versions": round(version_mb / 1024, 2)
                })

            # เรียงลำดับตามขนาดจากมากไปน้อย
            return sorted(summary_data, key=lambda x: x['current'] + x['versions'], reverse=True)
            
        except Exception as e:
            print(f"Error in get_after_delete_summary: {str(e)}")
            return []


    def import_csv_file(self, category): # category เก็บไว้เผื่อคุณอยากเติม Prefix ที่ชื่อไฟล์
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            
            file_paths = filedialog.askopenfilenames(
                title="เลือกไฟล์ CSV เพื่อเตรียม Sync",
                filetypes=[("CSV Files", "*.csv")]
            )
            root.destroy()

            if not file_paths:
                return {"error": "No file selected"}

            base_dir = self._get_base_path()
            
            # ปรับให้ไปที่ Initial_Receive ตามที่คุณต้องการ
            target_path = os.path.join(base_dir, "Data", "Initial_Receive")
            os.makedirs(target_path, exist_ok=True)
            
            imported_count = 0
            skipped_files = []
            for path in file_paths:
                filename = os.path.basename(path)
                # ป้องกันชื่อไฟล์ซ้ำแล้วระบบมองไม่เห็น: อาจเติม category นำหน้าชื่อไฟล์
                # new_filename = f"{category}_{filename}" 
                if not self._is_supported_import_filename(filename):
                    skipped_files.append(filename)
                    continue

                shutil.copy2(path, os.path.join(target_path, filename))
                imported_count += 1
            
            accepted_formats = (
                "Accepted formats only:\n"
                "- SharePoint_Report_YYYYMMDD_HHMM.csv\n"
                "- ScanSize_DPT-XX_Report_YYYYMMDD_HHMM.csv or ScanSize_Forum_Report_YYYYMMDD_HHMM.csv\n"
                "- Cleanup_Report_DPT-XX_YYYYMMDD_HHMM.csv or Cleanup_Report_Forum_YYYYMMDD_HHMM.csv"
            )

            if imported_count == 0:
                skipped_text = ""
                if skipped_files:
                    skipped_text = "\n\nSkipped:\n- " + "\n- ".join(skipped_files[:10])
                    if len(skipped_files) > 10:
                        skipped_text += f"\n- ... and {len(skipped_files) - 10} more"

                return {"error": "No supported CSV filename found.\n\n" + accepted_formats + skipped_text}

            details = f"Imported {imported_count} file(s)."
            if skipped_files:
                details += "\n\nSkipped unsupported filenames:\n- " + "\n- ".join(skipped_files[:10])
                if len(skipped_files) > 10:
                    details += f"\n- ... and {len(skipped_files) - 10} more"
                details += "\n\n" + accepted_formats

            return {
                "success": True,
                "count": imported_count,
                "skipped_count": len(skipped_files),
                "details": details
            }
        except Exception as e:
            return {"error": str(e)}


    # เพิ่มฟังก์ชันนี้ต่อจากฟังก์ชันเดิมใน class SharePointApi

    def get_delete_version_departments(self):
        """ดึงรายชื่อแผนกจากไฟล์ในโฟลเดอร์ DeleteVersion_Detail"""
        base_dir = self._get_base_path()
        target_dir = os.path.join(base_dir, "Data", "DeleteVersion_Detail")
        
        if not os.path.exists(target_dir):
            return []

        departments = set()
        # ปรับ pattern ให้รองรับทั้ง DPT-FO และ DPT_FB
        # โดยการจับกลุ่มข้อความที่อยู่หลัง Cleanup_Report_ จนถึงวันที่ (ตัวเลข 8 หลัก)
        pattern = r"Cleanup_Report_(.*?)_\d{8}"

        for filename in os.listdir(target_dir):
            match = re.search(pattern, filename)
            if match:
                departments.add(match.group(1))

        return sorted(list(departments))

    def get_delete_version_data(self, dept_name):

        """ดึงข้อมูลการลบ Version ล่าสุดของแผนกนั้นๆ"""
        base_dir = self._get_base_path()
        target_dir = os.path.join(base_dir, "Data", "DeleteVersion_Detail")
        
        if not os.path.exists(target_dir):
            return {"error": "Directory not found"}

        # ใช้ List Comprehension ตรวจสอบไฟล์ที่ขึ้นต้นด้วย Cleanup_Report_ ตามด้วยชื่อแผนกและขีดล่าง
        prefix = f"Cleanup_Report_{dept_name}_"
        files = [
            os.path.join(target_dir, f) 
            for f in os.listdir(target_dir) 
            if f.startswith(prefix) and f.lower().endswith('.csv')
        ]

        if not files:
            return {"error": f"ไม่พบข้อมูลการลบสำหรับแผนก {dept_name}"}

        # เลือกไฟล์ล่าสุดตามเวลาที่แก้ไขไฟล์ (Modification Time)
        latest_file = max(files, key=os.path.getmtime)
        return self._process_csv(latest_file)

