import os
import json
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
HIGHLIGHTS_FILE = os.path.join(DOWNLOAD_DIR, 'highlights.json')
OUTPUT_DIR = os.path.join(DOWNLOAD_DIR, 'shorts')
# =====================

def format_timestamp(seconds):
    """Convert seconds to HH:MM:SS format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def download_segment(url, start_time, duration, output_name):
    """Download a specific segment of the video"""
    end_time = start_time + duration
    
    # Format timestamps for yt-dlp
    start_str = format_timestamp(start_time)
    end_str = format_timestamp(end_time)
    
    cmd = [
        'yt-dlp',
        '--force-overwrites',
        '--format', 'mp4[height<=1080]/best[height<=1080][ext=mp4]',
        '--download-sections', f'*{start_str}-{end_str}',
        '-o', output_name,
        url
    ]
    
    print(f"[DOWNLOAD] Downloading segment {start_str} - {end_str}...")
    try:
        subprocess.run(cmd, check=True)
        print(f"[SUCCESS] Successfully downloaded: {output_name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to download segment: {e}")
        return False

def update_sheet_status(sheet, row_idx, status):
    """Update Google Sheet status"""
    try:
        # Update status column (assuming it's column 2)
        sheet.update_cell(row_idx, 2, status)
        print(f"[INFO] Updated sheet status: {status}")
    except Exception as e:
        print(f"[WARNING] Failed to update sheet: {e}")

def main():
    print("=== DOWNLOADING VIRAL SEGMENTS ===\n")
    
    # Load highlights and get video URL
    if not os.path.exists(HIGHLIGHTS_FILE):
        print(f"[ERROR] No highlights file found: {HIGHLIGHTS_FILE}")
        return
    
    with open(HIGHLIGHTS_FILE, 'r') as f:
        highlights_data = json.load(f)
    
    # Check if highlights file has the new format with video_url
    if isinstance(highlights_data, dict) and 'video_url' in highlights_data:
        video_url = highlights_data['video_url']
        highlights = highlights_data['highlights']
        print(f"[INFO] Using video URL from highlights file: {video_url}")
    else:
        # Fallback to old format - get URL from sheet
        print("[WARNING] Using old highlights format, getting URL from sheet...")
        try:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
            gc = gspread.authorize(creds)
            sheet = gc.open(GOOGLE_SHEET_NAME).worksheet(SHEET_TAB_NAME)
            data = sheet.get_all_records()
            
            # Find row with status "captions_downloaded"
            pending_row = None
            row_idx = None
            
            for idx, row in enumerate(data, start=2):
                if row.get("status", "").lower() == "captions_downloaded":
                    pending_row = row
                    row_idx = idx
                    break
            
            if not pending_row:
                print("[INFO] No rows with status 'captions_downloaded' found")
                return
            
            video_url = pending_row.get("podcast_url", "").strip()
            if not video_url:
                print("[ERROR] No podcast URL found in row")
                return
            
            highlights = highlights_data  # Old format
            
        except Exception as e:
            print(f"[ERROR] Google Sheets error: {e}")
            return
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Download each segment
    downloaded_segments = []
    for i, highlight in enumerate(highlights, 1):
        start_time = highlight['start']
        duration = highlight['duration']
        output_file = os.path.join(OUTPUT_DIR, f'segment_{i}.mp4')
        
        print(f"\n[TARGET] Downloading segment {i}: {highlight['summary'][:50]}...")
        if download_segment(video_url, start_time, duration, output_file):
            downloaded_segments.append(output_file)
    
    # Update status based on results
    if downloaded_segments:
        # Try to update sheet status if we have sheet access
        try:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
            gc = gspread.authorize(creds)
            sheet = gc.open(GOOGLE_SHEET_NAME).worksheet(SHEET_TAB_NAME)
            data = sheet.get_all_records()
            
            # Find row with status "captions_downloaded"
            row_idx = None
            for idx, row in enumerate(data, start=2):
                if row.get("status", "").lower() == "captions_downloaded":
                    row_idx = idx
                    break
            
            if row_idx:
                update_sheet_status(sheet, row_idx, "segments_downloaded")
        except Exception as e:
            print(f"[WARNING] Could not update sheet status: {e}")
        
        print(f"\n[SUCCESS] Successfully downloaded {len(downloaded_segments)} segments:")
        for segment in downloaded_segments:
            print(f"   [VIDEO] {segment}")
    else:
        # Try to update sheet status if we have sheet access
        try:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
            gc = gspread.authorize(creds)
            sheet = gc.open(GOOGLE_SHEET_NAME).worksheet(SHEET_TAB_NAME)
            data = sheet.get_all_records()
            
            # Find row with status "captions_downloaded"
            row_idx = None
            for idx, row in enumerate(data, start=2):
                if row.get("status", "").lower() == "captions_downloaded":
                    row_idx = idx
                    break
            
            if row_idx:
                update_sheet_status(sheet, row_idx, "segments_failed")
        except Exception as e:
            print(f"[WARNING] Could not update sheet status: {e}")
        
        print("\n[ERROR] Failed to download any segments")

if __name__ == "__main__":
    main() 