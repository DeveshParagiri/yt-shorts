import os
import subprocess
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ====== CONFIG ======
GOOGLE_SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME', 'Shorts Pipeline')
SHEET_TAB_NAME = os.getenv('SHEET_TAB_NAME', 'Sheet1')
CREDENTIALS_FILE = os.getenv('CREDENTIALS_FILE', 'automations-463516-2987a6762cd6.json')
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
# =====================

def get_english_captions(url, output_name):
    """Download ONLY human-created English captions (not auto-generated)"""
    if not url.strip():
        print(f"[skip] Empty URL for {output_name}")
        return False
        
    output_path = os.path.join(DOWNLOAD_DIR, output_name.replace('.mp4', ''))
    cmd = [
        'yt-dlp',
        '--write-subs',           # Only manual subs
        '--sub-langs', 'en',      # English only
        '--sub-format', 'vtt',    # VTT format
        '--skip-download',        # Don't download video
        '-o', output_path,
        url
    ]
    
    print(f"[📝] Checking for English captions (non-auto)...")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Check if caption file was created
        possible_caption_files = [
            f"{output_path}.en.vtt",
            f"{output_path}.en-US.vtt", 
            f"{output_path}.en-GB.vtt"
        ]
        
        for caption_file in possible_caption_files:
            if os.path.exists(caption_file):
                print(f"[✅] Found English captions: {caption_file}")
                return True
                
        print("[❌] No English captions found - SKIPPING this row")
        return False
        
    except subprocess.CalledProcessError:
        print("[❌] Failed to check captions - SKIPPING this row")
        return False

def download_video(url, filename, is_broll=False):
    """Download video at 1080p"""
    if not url.strip():
        print(f"[skip] Empty URL for {filename}")
        return False

    output_path = os.path.join(DOWNLOAD_DIR, filename)
    cmd = [
        'yt-dlp',
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
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError:
        print(f"[❌] Failed to download {filename}")
        return False

def main():
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
