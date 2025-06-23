import os
import subprocess
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import platform
import shutil

# Load environment variables
load_dotenv()

# ====== CONFIG ======
GOOGLE_SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME', 'Shorts Pipeline')
SHEET_TAB_NAME = os.getenv('SHEET_TAB_NAME', 'Sheet1')
CREDENTIALS_FILE = os.getenv('CREDENTIALS_FILE', 'automations-463516-2987a6762cd6.json')
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
# =====================

def check_dependencies():
    """Check if required dependencies are available"""
    # Check if yt-dlp is available
    yt_dlp_path = shutil.which('yt-dlp')
    if not yt_dlp_path:
        print("[❌] yt-dlp not found in PATH. Please install yt-dlp first.")
        print("Install with: pip install yt-dlp")
        return False
    
    print(f"[✅] Found yt-dlp at: {yt_dlp_path}")
    
    # Test yt-dlp basic functionality
    try:
        result = subprocess.run([yt_dlp_path, '--version'], 
                              capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"[✅] yt-dlp version: {result.stdout.strip()}")
        else:
            print(f"[❌] yt-dlp test failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"[❌] Error testing yt-dlp: {e}")
        return False
    
    return True

def get_english_captions(url, output_name):
    """Download ONLY human-created English captions (not auto-generated)"""
    if not url.strip():
        print(f"[skip] Empty URL for {output_name}")
        return False
        
    output_path = os.path.join(DOWNLOAD_DIR, output_name.replace('.mp4', ''))
    
    # Use full path to yt-dlp if on Windows
    yt_dlp_cmd = 'yt-dlp'
    if platform.system() == 'Windows':
        yt_dlp_path = shutil.which('yt-dlp')
        if yt_dlp_path:
            yt_dlp_cmd = yt_dlp_path
    
    cmd = [
        yt_dlp_cmd,
        '--write-subs',           # Only manual subs
        '--sub-langs', 'en',      # English only
        '--sub-format', 'vtt',    # VTT format
        '--skip-download',        # Don't download video
        '--no-warnings',          # Reduce noise
        '-o', output_path,
        url
    ]
    
    print(f"[📝] Checking for English captions (non-auto)...")
    print(f"[DEBUG] Command: {' '.join(cmd)}")
    
    try:
        # Use shell=True on Windows for better compatibility
        use_shell = platform.system() == 'Windows'
        
        result = subprocess.run(cmd, 
                              check=False,  # Don't raise on non-zero exit
                              capture_output=True, 
                              text=True, 
                              timeout=120,  # 2 minute timeout
                              shell=use_shell)
        
        print(f"[DEBUG] Return code: {result.returncode}")
        print(f"[DEBUG] STDOUT: {result.stdout}")
        print(f"[DEBUG] STDERR: {result.stderr}")
        
        # Check if caption file was created
        possible_caption_files = [
            f"{output_path}.en.vtt",
            f"{output_path}.en-US.vtt", 
            f"{output_path}.en-GB.vtt"
        ]
        
        for caption_file in possible_caption_files:
            if os.path.exists(caption_file):
                print(f"[✅] Found English captions: {caption_file}")
                # Clean up the caption file since we only needed to check
                try:
                    os.remove(caption_file)
                except:
                    pass
                return True
        
        # Check if yt-dlp succeeded but no captions were found
        if result.returncode == 0:
            print("[❌] No English captions found - SKIPPING this row")
        else:
            print(f"[❌] yt-dlp failed with return code {result.returncode}")
            if "ERROR" in result.stderr or "error" in result.stderr:
                print(f"[ERROR] Details: {result.stderr}")
        
        return False
        
    except subprocess.TimeoutExpired:
        print("[❌] Caption check timed out - SKIPPING this row")
        return False
    except FileNotFoundError:
        print("[❌] yt-dlp command not found. Please ensure yt-dlp is installed and in PATH")
        return False
    except Exception as e:
        print(f"[❌] Unexpected error during caption check: {e}")
        return False

def download_video(url, filename, is_broll=False):
    """Download video at 1080p"""
    if not url.strip():
        print(f"[skip] Empty URL for {filename}")
        return False

    output_path = os.path.join(DOWNLOAD_DIR, filename)
    
    # Use full path to yt-dlp if on Windows
    yt_dlp_cmd = 'yt-dlp'
    if platform.system() == 'Windows':
        yt_dlp_path = shutil.which('yt-dlp')
        if yt_dlp_path:
            yt_dlp_cmd = yt_dlp_path
    
    cmd = [
        yt_dlp_cmd,
        '--force-overwrites',
        '--format', 'mp4[height<=1080]/best[height<=1080][ext=mp4]',
        '-o', output_path,
        url
    ]

    if is_broll:
        cmd.insert(-1, '--download-sections')
        cmd.insert(-1, '*00:00:00-00:03:00')  # 3 minutes of broll

    print(f"[yt-dlp] Downloading {url} → {filename} {'(3-min b-roll)' if is_broll else ''}")
    try:
        # Use shell=True on Windows for better compatibility
        use_shell = platform.system() == 'Windows'
        
        result = subprocess.run(cmd, 
                              check=False, 
                              capture_output=True, 
                              text=True,
                              shell=use_shell)
        
        if result.returncode == 0:
            return True
        else:
            print(f"[❌] Failed to download {filename}")
            print(f"[ERROR] Details: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"[❌] Failed to download {filename}: {e}")
        return False

def main():
    print(f"[ℹ️] Running on {platform.system()} {platform.release()}")
    
    # Check dependencies first
    if not check_dependencies():
        print("[❌] Dependency check failed. Please fix the issues above.")
        return
    
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)

    sheet = client.open(GOOGLE_SHEET_NAME).worksheet(SHEET_TAB_NAME)
    data = sheet.get_all_records()

    for idx, row in enumerate(data, start=2):  # Row 2 = first data row
        if row.get("status", "").lower() == "pending":
            podcast_url = row.get("podcast_url", "").strip()
            broll_url = row.get("broll_url", "").strip()

            if not podcast_url:
                print(f"[skip] Row {idx}: No podcast URL")
                continue

            os.makedirs(DOWNLOAD_DIR, exist_ok=True)

            try:
                # Step 1: Check if podcast has English captions
                print(f"\n=== ROW {idx}: Checking captions ===")
                has_captions = get_english_captions(podcast_url, "podcast.mp4")
                
                if not has_captions:
                    print(f"[⏭️] Row {idx}: No English captions - SKIPPING")
                    sheet.update_cell(idx, list(row.keys()).index("status") + 1, "no_captions")
                    continue

                # Step 2: Download podcast video
                print(f"\n=== ROW {idx}: Downloading videos ===")
                podcast_success = download_video(podcast_url, "podcast.mp4", is_broll=False)
                
                broll_success = True
                if broll_url:
                    broll_success = download_video(broll_url, "broll.mp4", is_broll=True)

                if podcast_success:
                    sheet.update_cell(idx, list(row.keys()).index("status") + 1, "downloaded")
                    print(f"[✅] Row {idx}: Downloaded with captions")
                else:
                    sheet.update_cell(idx, list(row.keys()).index("status") + 1, "download_failed")
                    print(f"[❌] Row {idx}: Download failed")

            except Exception as e:
                print(f"[❌] Row {idx}: Error - {e}")
                sheet.update_cell(idx, list(row.keys()).index("status") + 1, "error")
            
            break  # Process only one row at a time
    else:
        print("[ℹ️] No pending rows found.")

if __name__ == "__main__":
    main()
