import os
import json
import glob
import logging
import gspread
import requests
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from openai import AzureOpenAI

# Load environment variables
load_dotenv()

# ====== CONFIG ====== #
GOOGLE_SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME', 'Shorts Pipeline')
SHEET_TAB_NAME = os.getenv('SHEET_TAB_NAME', 'Sheet1')
CREDENTIALS_FILE = os.getenv('CREDENTIALS_FILE', 'automations-463516-2987a6762cd6.json')
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
HIGHLIGHTS_FILE = os.path.join(DOWNLOAD_DIR, 'highlights.json')
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# ==================== #

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def notify_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            logger.error(f"Telegram notify failed: {response.text}")
    except Exception as e:
        logger.error(f"Telegram error: {e}")

def get_video_url_from_sheet():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        gc = gspread.authorize(creds)
        sheet = gc.open(GOOGLE_SHEET_NAME).worksheet(SHEET_TAB_NAME)
        for row in sheet.get_all_records():
            if row.get("status", "").lower() == "captions_downloaded":
                video_url = row.get("podcast_url", "").strip()
                if video_url:
                    logger.info(f"Found video URL: {video_url}")
                    return video_url
        logger.warning("No video URL found with 'captions_downloaded' status")
        return None
    except Exception as e:
        logger.error(f"Sheet error: {e}")
        return None

def parse_vtt_captions():
    vtt_files = glob.glob(os.path.join(DOWNLOAD_DIR, "*.vtt"))
    if not vtt_files:
        logger.error("No VTT caption files found")
        return None

    vtt_file = vtt_files[0]
    logger.info(f"Parsing VTT file: {vtt_file}")

    segments = []
    with open(vtt_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('WEBVTT') or line == '' or line.startswith('NOTE') or line.isdigit():
            i += 1
            continue

        if '-->' in line:
            parts = line.split(' --> ')
            if len(parts) == 2:
                start_time = vtt_time_to_seconds(parts[0])
                end_time = vtt_time_to_seconds(parts[1])
                i += 1
                text_lines = []
                while i < len(lines) and '-->' not in lines[i].strip() and lines[i].strip() != '':
                    clean = lines[i].strip().replace('<c>', '').replace('</c>', '').replace('<v ', '').replace('>', '')
                    if clean and not clean.isdigit():
                        text_lines.append(clean)
                    i += 1
                if text_lines:
                    segments.append({'start': start_time, 'end': end_time, 'text': ' '.join(text_lines)})
                continue
        i += 1

    logger.info(f"Parsed {len(segments)} caption segments")
    return segments

def vtt_time_to_seconds(time_str):
    parts = time_str.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(parts[0])

def parse_mmss_to_seconds(mmss_str):
    m, s = map(int, mmss_str.strip().split(':'))
    return m * 60 + s

def find_viral_highlights(segments):
    logger.info("🧠 Analyzing captions with GPT-4o...")

    transcript = ""
    for seg in segments:
        timestamp = f"[{int(seg['start'] // 60):02}:{int(seg['start'] % 60):02}]"
        transcript += f"{timestamp} {seg['text']}\n"

    if len(transcript) > 8000:
        transcript = transcript[:8000] + "\n...[truncated]"

    prompt = f"""
You are an expert content editor working on short-form viral videos.

Your task is to analyze the following transcript of a long-form video (e.g., podcast, interview, talk) and extract **exactly 3 non-overlapping moments** that are likely to go viral when turned into short-form clips.

🎯 REQUIREMENTS:

1. You must return **exactly 3 moments** — only return fewer if the transcript is absolutely too short.
2. Each moment must be **between 30 and 90 seconds long**, inclusive.
3. All moments must be **non-overlapping** in time.
4. Each moment must start and end at **natural points in speech** — do not cut mid-sentence or mid-word.
5. Timestamps must be in `MM:SS` format (e.g., "01:20").
6. Select **compelling and emotionally engaging moments** that would perform well on YouTube Shorts, TikTok, or Instagram Reels.

📦 OUTPUT FORMAT (JSON only):

```json
[
  {{
    "start_time": "MM:SS",
    "end_time": "MM:SS",
    "hook": "Opening line of the clip that grabs attention",
    "summary": "One-line explanation of why this moment is viral-worthy"
  }},
  ...
]
If you cannot find 3 valid moments within the 30–90 second duration range, return as many as possible and explain why in a comment above the JSON, like:
// Only 2 valid clips due to short transcript. All clips strictly within 30–90s.

Now analyze the transcript and return the 3 best viral moments.

📄 TRANSCRIPT:
{transcript}
"""

    try:
        client = AzureOpenAI(
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY")
        )

        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=800
        )

        ai_text = response.choices[0].message.content.strip()

        if ai_text.startswith("```json"):
            ai_text = ai_text.replace("```json", "").replace("```", "")
        elif ai_text.startswith("```"):
            ai_text = ai_text.replace("```", "")

        json_start = ai_text.find('[')
        json_end = ai_text.rfind(']') + 1
        json_str = ai_text[json_start:json_end]

        highlights_raw = json.loads(json_str)
        logger.info(f"GPT returned {len(highlights_raw)} highlight(s)")

        seen_ranges = []
        segments_out = []

        for h in highlights_raw:
            try:
                start_sec = parse_mmss_to_seconds(h['start_time'])
                end_sec = parse_mmss_to_seconds(h['end_time'])
                duration = end_sec - start_sec

                if not (30 <= duration <= 90):
                    logger.warning(f"Skipping: duration {duration}s out of bounds")
                    continue

                # Check for overlaps
                if any(abs(start_sec - s['start']) < 5 or abs(end_sec - s['end']) < 5 for s in segments_out):
                    logger.warning(f"Skipping overlapping segment: {h}")
                    continue

                segments_out.append({
                    'start': start_sec,
                    'end': end_sec,
                    'duration': duration,
                    'summary': h['summary'],
                    'hook': h['hook'],
                    'viral_score': 10
                })
                logger.info(f"Segment: {h['hook']} → {duration:.1f}s")

            except Exception as parse_err:
                logger.warning(f"Skipping invalid entry: {h} ({parse_err})")

        if len(segments_out) != 3:
            notify_telegram(f"⚠️ GPT returned {len(segments_out)} valid highlights (expected 3).")

        return segments_out[:3]

    except json.JSONDecodeError as json_err:
        logger.error(f"❌ JSON parse error: {json_err}")
        logger.error(f"Raw GPT output:\n{ai_text}")
        notify_telegram("❌ JSON parsing failed for GPT highlights.")
        return None

    except Exception as e:
        logger.error(f"❌ GPT error: {e}")
        notify_telegram("❌ GPT call failed.")
        return None


def main():
    logger.info("=== VIRAL HIGHLIGHT DETECTION ===")
    video_url = get_video_url_from_sheet()
    if not video_url:
        notify_telegram("❌ No video URL found.")
        return

    segments = parse_vtt_captions()
    if not segments:
        notify_telegram("❌ No captions parsed.")
        return

    highlights = find_viral_highlights(segments)
    if not highlights:
        notify_telegram("❌ No viral highlights found.")
        return

    highlights_data = {
        'video_url': video_url,
        'highlights': highlights
    }

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    with open(HIGHLIGHTS_FILE, 'w') as f:
        json.dump(highlights_data, f, indent=2)

    logger.info(f"Saved highlights to: {HIGHLIGHTS_FILE}")
    notify_telegram(f"✅ Found {len(highlights)} viral highlights!\n[✓] Saved: {HIGHLIGHTS_FILE}")

    for i, h in enumerate(highlights, 1):
        logger.info(f"HIGHLIGHT {i}: {h['hook']} → {h['summary']} ({h['duration']:.1f}s)")

if __name__ == "__main__":
    main()
