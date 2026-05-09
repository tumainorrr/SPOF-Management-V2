import os
import subprocess
import shutil

APP_NAME = "SPOF_Management_System" # ชื่อโฟลเดอร์ปลายทาง

print("--- Starting Build Process ---")

if os.path.exists('dist'): shutil.rmtree('dist')
if os.path.exists('build'): shutil.rmtree('build')

subprocess.run([
    'python', '-m', 'PyInstaller',
    '--noconsole',
    '--onedir',
    '--name=' + APP_NAME,
    '--icon=hotel_logo.ico',
    '--add-data=ui;ui',  # ฝังหน้าเว็บไว้ใน EXE (_MEIPASS)
    # ไม่ใส่ --add-data=Data;Data เพราะเราจะสร้างโฟลเดอร์เปล่าข้างนอกแทน
    '--collect-all=webview', # ช่วยเก็บไฟล์ที่จำเป็นของ pywebview
    'src/main.py'
])

# สร้างโครงสร้าง Data ขั้นบันไดใน dist
# โครงสร้างจะเป็น: dist/SP_Dashboard/Data/...
dist_data_path = os.path.join('dist', APP_NAME, 'Data')

folders = [
    'ScanSizeOriginalFirstTime',
    'Previous_Scan_Detail',
    'Current_Scan_Detail',
    'Initial_Receive',
    'DeleteVersion_Detail',
    'Backup'
]

for folder in folders:
    os.makedirs(os.path.join(dist_data_path, folder), exist_ok=True)

# --- ส่วนที่เพิ่ม: สร้าง Folder ย่อยใน Backup เพื่อความเป็นระเบียบ ---
backup_sub_folders = [
    'DeleteVersion_Backup_Detail',
    'ScanSizeOverall',
    'ScanVersionDetail',
    'ScanOriginalVersionDetail'
]

for sub in backup_sub_folders:
    # สร้างโครงสร้าง: dist/SP_Dashboard/Data/Backup/[ชื่อส่วน]
    os.makedirs(os.path.join(dist_data_path, 'Backup', sub), exist_ok=True)
# -------------------------------------------------------

with open(os.path.join(dist_data_path, 'place_csv_here.txt'), 'w', encoding='utf-8') as f:
    f.write('วางไฟล์ CSV ใหม่ที่ Initial_Receive แล้วกดปุ่ม Sync ในโปรแกรม')

print(f"\n--- BUILD SUCCESS! ---")