import os
import json
import subprocess
import logging
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests

# Load environment variables
load_dotenv()

# ========== CONFIG ========== #
GOOGLE_SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME', 'Shorts Pipeline')
SHEET_TAB_NAME = os.getenv('SHEET_TAB_NAME', 'Sheet1')
CREDENTIALS_FILE = os.getenv('CREDENTIALS_FILE', 'automations-463516-2987a6762cd6.json')
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
HIGHLIGHTS_FILE = os.path.join(DOWNLOAD_DIR, 'highlights.json')
OUTPUT_DIR = os.path.join(DOWNLOAD_DIR, 'shorts')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
# ============================ #

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def notify_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured. Skipping notification.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            logger.error(f"Telegram notify failed: {response.text}")
    except Exception as e:
        logger.error(f"Telegram error: {e}")

def format_timestamp(seconds):
    total_seconds = int(round(seconds))
    h, m, s = total_seconds // 3600, (total_seconds % 3600) // 60, total_seconds % 60
    return f"{h:02}:{m:02}:{s:02}"

def run_subprocess(cmd, success_msg, error_msg):
    try:
        subprocess.run(cmd, check=True)
        logger.info(success_msg)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"{error_msg}: {e}")
        return False

def download_segment(url, start_time, duration, output_name):
    start_str = format_timestamp(start_time)
    end_str = format_timestamp(start_time + duration)
    cmd = [
        'yt-dlp', '--force-overwrites',
        '--format', 'mp4[height<=1080]/best[height<=1080][ext=mp4]',
        '--download-sections', f'*{start_str}-{end_str}',
        '-o', output_name, url
    ]
    logger.info(f"Downloading segment: {start_str} - {end_str}")
    return run_subprocess(cmd, f"Downloaded: {output_name}", "Download failed")

def convert_to_vertical(input_file, output_file):
    cmd = [
        'ffmpeg', '-y', '-i', input_file,
        '-vf', 'pad=iw:2*trunc(iw*16/18):0:(oh-ih)/2:black',
        '-c:a', 'copy', '-preset', 'fast', output_file
    ]
    logger.info(f"Converting to vertical: {input_file}")
    return run_subprocess(cmd, f"Vertical output: {output_file}", "Vertical conversion failed")

def authorize_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    gc = gspread.authorize(creds)
    return gc.open(GOOGLE_SHEET_NAME).worksheet(SHEET_TAB_NAME)

def get_video_url_and_highlights():
    if not os.path.exists(HIGHLIGHTS_FILE):
        logger.error(f"Missing file: {HIGHLIGHTS_FILE}")
        notify_telegram("❌ highlights.json file missing.")
        return None, None

    with open(HIGHLIGHTS_FILE) as f:
        data = json.load(f)

    if isinstance(data, dict) and 'video_url' in data:
        return data['video_url'], data['highlights']

    logger.info("Using fallback sheet for video URL...")
    sheet = authorize_sheet()
    for idx, row in enumerate(sheet.get_all_records(), start=2):
        if row.get("status", "").lower() == "captions_downloaded":
            return row.get("podcast_url", "").strip(), data
    return None, None

def update_sheet_status(status):
    try:
        sheet = authorize_sheet()
        for idx, row in enumerate(sheet.get_all_records(), start=2):
            if row.get("status", "").lower() == "captions_downloaded":
                sheet.update_cell(idx, 2, status)
                logger.info(f"Updated sheet row {idx} to '{status}'")
                return
    except Exception as e:
        logger.error(f"Sheet update error: {e}")

def process_highlights(video_url, highlights):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    downloaded = []
    failed = []

    for i, h in enumerate(highlights, 1):
        start, duration = h['start'], h['duration']
        temp_out = os.path.join(OUTPUT_DIR, f"segment_{i}_temp.mp4")
        final_out = os.path.join(OUTPUT_DIR, f"segment_{i}.mp4")

        logger.info(f"[Segment {i}] {h.get('summary', '')[:50]}...")
        if download_segment(video_url, start, duration, temp_out):
            if convert_to_vertical(temp_out, final_out):
                os.remove(temp_out)
                downloaded.append(final_out)
            else:
                os.rename(temp_out, final_out)
                downloaded.append(final_out)
        else:
            failed.append(i)

    if failed:
        logger.warning(f"Failed segments: {failed}")

    return downloaded

def main():
    logger.info("=== STARTING SEGMENT PROCESSING ===")
    video_url, highlights = get_video_url_and_highlights()
    if not video_url or not highlights:
        logger.error("Failed to retrieve video URL or highlights.")
        notify_telegram("❌ Could not retrieve video URL or highlights.")
        return

    segments = process_highlights(video_url, highlights)
    status = "segments_downloaded" if segments else "segments_failed"
    update_sheet_status(status)

    if segments:
        msg = f"✅ Processed {len(segments)} segments."
        logger.info(msg)
        notify_telegram(msg)
    else:
        logger.error("No segments processed.")
        notify_telegram("❌ No segments were processed.")

if __name__ == "__main__":
    main()
