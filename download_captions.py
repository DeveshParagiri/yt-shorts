import os
import subprocess
import platform
import shutil
import logging
import gspread
import requests
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

# Load environment variables
load_dotenv()

# ====== CONFIG ====== #
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Shorts Pipeline")
SHEET_TAB_NAME = os.getenv("SHEET_TAB_NAME", "Sheet1")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "automations-463516-2987a6762cd6.json")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# ===================== #

# Setup logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def notify_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        response = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        })
        if response.status_code != 200:
            logger.error(f"Telegram error: {response.text}")
    except Exception as e:
        logger.error(f"Telegram exception: {e}")

def check_yt_dlp_dependency():
    yt_dlp_path = shutil.which("yt-dlp")
    if not yt_dlp_path:
        logger.error("yt-dlp not found. Install with: pip install yt-dlp")
        return None

    try:
        result = subprocess.run([yt_dlp_path, "--version"], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            logger.info(f"yt-dlp version: {result.stdout.strip()}")
            return yt_dlp_path
        logger.error("yt-dlp version check failed")
    except Exception as e:
        logger.error(f"Dependency check error: {e}")
    return None

def download_captions(url, output_name, yt_dlp_path):
    if not url.strip():
        logger.warning(f"[SKIP] Empty URL for {output_name}")
        return False

    output_path = os.path.join(DOWNLOAD_DIR, f"captions_{output_name}").replace("\\", "/")
    cmd = [
        yt_dlp_path,
        "--write-subs",
        "--sub-langs", "en",
        "--sub-format", "vtt",
        "--skip-download",
        "--no-warnings",
        "-o", f"{output_path}.%(ext)s",
        url
    ]

    use_shell = platform.system() == "Windows"
    if use_shell:
        cmd = " ".join(f'"{c}"' if " " in c else c for c in cmd)

    logger.info(f"Downloading captions for {url}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, shell=use_shell)
        logger.debug(result.stdout)
        logger.debug(result.stderr)

        for ext in [".en.vtt", ".en-US.vtt", ".en-GB.vtt"]:
            if os.path.exists(output_path + ext):
                logger.info(f"Captions downloaded: {output_path + ext}")
                return True

        logger.warning("No English captions found")
        return False
    except subprocess.TimeoutExpired:
        logger.error("Caption download timed out")
    except Exception as e:
        logger.error(f"Download error: {e}")
    return False

def update_sheet_status(sheet, row_idx, status):
    try:
        headers = sheet.row_values(1)
        if "status" not in headers:
            raise ValueError("Missing 'status' column in sheet")
        col_idx = headers.index("status") + 1  # gspread is 1-indexed
        sheet.update_cell(row_idx, col_idx, status)
        logger.info(f"Updated row {row_idx} status → '{status}'")
    except Exception as e:
        logger.error(f"Failed to update sheet status: {e}")


def process_sheet(yt_dlp_path):
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        CREDENTIALS_FILE,
        [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    gc = gspread.authorize(creds)
    sheet = gc.open(GOOGLE_SHEET_NAME).worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_records()

    for idx, row in enumerate(rows, start=2):
        if row.get("status", "").lower() == "pending":
            url = row.get("podcast_url", "").strip()
            if not url:
                logger.warning(f"Row {idx} has empty URL")
                continue

            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            logger.info(f"Processing row {idx}")
            success = download_captions(url, str(idx), yt_dlp_path)
            status = "captions_downloaded" if success else "no_captions"
            update_sheet_status(sheet, idx, status)

            notify_telegram(
                f"{'✅ Captions downloaded' if success else '⚠️ No captions found'} for row {idx}"
            )
            break
    else:
        logger.info("No pending rows found.")
        notify_telegram("ℹ️ No pending rows found.")

def main():
    logger.info(f"Running on {platform.system()} {platform.release()}")
    yt_dlp_path = check_yt_dlp_dependency()
    if yt_dlp_path:
        process_sheet(yt_dlp_path)

if __name__ == "__main__":
    main()
