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
        print("[ERROR] yt-dlp not found in PATH. Please install yt-dlp first.")
        print("Install with: pip install yt-dlp")
        return False
    
    print(f"[SUCCESS] Found yt-dlp at: {yt_dlp_path}")
    
    # Test yt-dlp basic functionality
    try:
        result = subprocess.run([yt_dlp_path, '--version'], 
                              capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"[SUCCESS] yt-dlp version: {result.stdout.strip()}")
            return yt_dlp_path
        else:
            print(f"[ERROR] yt-dlp test failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"[ERROR] Error testing yt-dlp: {e}")
        return False

def download_captions(url, output_name, yt_dlp_path):
    """Download ONLY human-created English captions (not auto-generated)"""
    if not url.strip():
        print(f"[SKIP] Empty URL for {output_name}")
        return False
        
    # Clean output path - use forward slashes and ensure proper extension handling
    output_path = os.path.join(DOWNLOAD_DIR, f"captions_{output_name}").replace('\\', '/')
    
    # Build command list
    cmd = [
        yt_dlp_path,
        '--write-subs',           # Only manual subs
        '--sub-langs', 'en',      # English only
        '--sub-format', 'vtt',    # VTT format
        '--skip-download',        # Don't download video
        '--no-warnings',          # Reduce noise
        '-o', f"{output_path}.%(ext)s",  # Ensure proper extension handling
        url
    ]
    
    print(f"[INFO] Downloading English captions for {url}...")
    
    # Handle Windows shell compatibility
    use_shell = platform.system() == 'Windows'
    if use_shell:
        # Convert command list to properly quoted string for Windows
        cmd = ' '.join(f'"{c}"' if ' ' in str(c) else str(c) for c in cmd)
    
    print(f"[RUNNING] {'(shell)' if use_shell else ''} Command: {cmd}")
    
    try:
        result = subprocess.run(cmd, 
                              check=False,
                              capture_output=True, 
                              text=True, 
                              timeout=120,
                              shell=use_shell)
        
        print(f"[DEBUG] Return code: {result.returncode}")
        print(f"[STDOUT]\n{result.stdout}")
        print(f"[STDERR]\n{result.stderr}")
        
        # Check if caption file was created - use forward slashes in paths
        base_path = output_path.replace('\\', '/')
        possible_caption_files = [
            f"{base_path}.en.vtt",
            f"{base_path}.en-US.vtt", 
            f"{base_path}.en-GB.vtt"
        ]
        
        for caption_file in possible_caption_files:
            if os.path.exists(caption_file):
                print(f"[SUCCESS] Successfully downloaded captions: {caption_file}")
                return True
        
        # Check if yt-dlp succeeded but no captions were found
        if result.returncode == 0:
            print("[ERROR] No English captions found - SKIPPING this row")
        else:
            print(f"[ERROR] yt-dlp failed with return code {result.returncode}")
            if "ERROR" in result.stderr or "error" in result.stderr:
                print(f"[ERROR] Details: {result.stderr}")
        
        return False
        
    except subprocess.TimeoutExpired:
        print("[ERROR] Caption download timed out - SKIPPING this row")
        return False
    except FileNotFoundError:
        print("[ERROR] yt-dlp command not found. Please ensure yt-dlp is installed and in PATH")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error during caption download: {e}")
        return False

def main():
    print(f"[INFO] Running on {platform.system()} {platform.release()}")
    
    # Check dependencies first and get yt-dlp path
    yt_dlp_path = check_dependencies()
    if not yt_dlp_path:
        print("[ERROR] Dependency check failed. Please fix the issues above.")
        return
    
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)

    sheet = client.open(GOOGLE_SHEET_NAME).worksheet(SHEET_TAB_NAME)
    data = sheet.get_all_records()

    for idx, row in enumerate(data, start=2):  # Row 2 = first data row
        if row.get("status", "").lower() == "pending":
            podcast_url = row.get("podcast_url", "").strip()

            if not podcast_url:
                print(f"[SKIP] Row {idx}: No podcast URL")
                continue

            os.makedirs(DOWNLOAD_DIR, exist_ok=True)

            try:
                print(f"\n=== ROW {idx}: Downloading captions ===")
                caption_success = download_captions(podcast_url, str(idx), yt_dlp_path)
                
                if caption_success:
                    sheet.update_cell(idx, list(row.keys()).index("status") + 1, "captions_downloaded")
                    print(f"[SUCCESS] Row {idx}: Captions downloaded successfully")
                else:
                    sheet.update_cell(idx, list(row.keys()).index("status") + 1, "no_captions")
                    print(f"[ERROR] Row {idx}: No captions available")

            except Exception as e:
                print(f"[ERROR] Row {idx}: Error - {e}")
                sheet.update_cell(idx, list(row.keys()).index("status") + 1, "error")
            
            break  # Process only one row at a time
    else:
        print("[INFO] No pending rows found.")

if __name__ == "__main__":
    main() 