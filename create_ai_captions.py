import os
import json
import time
import subprocess
import logging
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ====== CONFIG ======
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
HIGHLIGHTS_FILE = os.path.join(DOWNLOAD_DIR, 'highlights.json')
OUTPUT_DIR = os.path.join(DOWNLOAD_DIR, 'shorts')
ASSEMBLYAI_API_KEY = os.getenv('ASSEMBLYAI_API_KEY')
ASSEMBLYAI_BASE_URL = 'https://api.assemblyai.com/v2'
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# ====== LOGGING ======
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def notify_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not set.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        res = requests.post(url, json=payload)
        res.raise_for_status()
    except Exception as e:
        logger.error(f"Telegram notify failed: {e}")

def run_subprocess(cmd, success_msg, error_msg):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(success_msg)
        return result
    except subprocess.CalledProcessError as e:
        logger.error(f"{error_msg}: {e.stderr}")
        notify_telegram(f"❌ {error_msg}")
        raise

def extract_audio(video_file, output_audio):
    output_audio = output_audio.replace('.wav', '.mp3')
    logger.info(f"[AUDIO] Extracting audio from {video_file}")
    cmd = ['ffmpeg', '-y', '-i', video_file, '-vn', '-acodec', 'libmp3lame', '-ar', '44100', '-ab', '192k', '-ac', '1', output_audio]
    run_subprocess(cmd, f"Audio extracted: {output_audio}", "Audio extraction failed")
    return output_audio

def transcribe_audio(audio_file):
    if not ASSEMBLYAI_API_KEY:
        raise Exception("ASSEMBLYAI_API_KEY not set")
    headers = {'authorization': ASSEMBLYAI_API_KEY}

    logger.info("[UPLOAD] Uploading to AssemblyAI...")
    with open(audio_file, 'rb') as f:
        response = requests.post(f'{ASSEMBLYAI_BASE_URL}/upload', headers=headers, files={'file': f})
    response.raise_for_status()
    audio_url = response.json()['upload_url']

    response = requests.post(f'{ASSEMBLYAI_BASE_URL}/transcript', json={'audio_url': audio_url, 'format_text': True, 'language_code': 'en_us'}, headers=headers)
    response.raise_for_status()
    transcript_id = response.json()['id']

    logger.info("[AI] Waiting for transcription...")
    while True:
        response = requests.get(f'{ASSEMBLYAI_BASE_URL}/transcript/{transcript_id}', headers=headers)
        status = response.json()
        if status['status'] == 'completed':
            logger.info("Transcription complete.")
            return status
        elif status['status'] == 'error':
            raise Exception(f"Transcription failed: {status['error']}")
        time.sleep(3)

def get_video_info(video_file):
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', video_file]
    result = run_subprocess(cmd, "Fetched video info", "Video info fetch failed")
    data = json.loads(result.stdout)
    for stream in data['streams']:
        if stream['codec_type'] == 'video':
            return {
                'width': int(stream['width']),
                'height': int(stream['height']),
                'fps': eval(stream['r_frame_rate']),
                'duration': float(data['format']['duration'])
            }
    raise Exception("No video stream found")

def create_caption_groups(words):
    if not words:
        return []
    captions = []
    current_group = []
    for word in words:
        if (not current_group or len(current_group) >= 4 or any(p in word['text'] for p in ['.', '!', '?', ',']) or (current_group and (word['start'] - current_group[0]['start']) / 1000.0 > 3.0)):
            if current_group:
                captions.append({
                    'words': current_group.copy(),
                    'text': ' '.join(w['text'] for w in current_group),
                    'start': current_group[0]['start'] / 1000.0,
                    'end': current_group[-1]['end'] / 1000.0
                })
            current_group = [word]
        else:
            current_group.append(word)
    if current_group:
        captions.append({
            'words': current_group.copy(),
            'text': ' '.join(w['text'] for w in current_group),
            'start': current_group[0]['start'] / 1000.0,
            'end': current_group[-1]['end'] / 1000.0
        })
    return captions

def remove_unnecessary_backslashes(text):
    import re
    def clean_line(line):
        parts = re.split(r'(\{.*?\})', line)
        cleaned = ''
        for p in parts:
            if p.startswith('{') and p.endswith('}'):
                cleaned += p
            else:
                cleaned += p.replace('\\', '')
        return cleaned
    cleaned_lines = [clean_line(l) for l in text.splitlines()]
    return '\n'.join(cleaned_lines)

def create_ass_subtitles(captions, output_file, video_info):
    logger.info(f"Creating subtitles: {output_file}")
    ass_content = f"""[Script Info]
Title: AI Captions
ScriptType: v4.00+
PlayResX: {video_info['width']}
PlayResY: {video_info['height']}
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Impact,{int(video_info['height']/12)},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,3,2,2,30,30,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def to_ass_time(sec):
        return f"{int(sec//3600)}:{int((sec%3600)//60):02}:{int(sec%60):02}.{int((sec%1)*100):02}"
    for caption in captions:
        start = to_ass_time(caption['start'])
        end = to_ass_time(caption['end'])
        full_text = ' '.join(w['text'].upper() for w in caption['words']).replace(',', '\\,')
        ass_content += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{full_text}\n"
        for i, word in enumerate(caption['words']):
            word_start = to_ass_time(word['start'] / 1000.0)
            word_end = to_ass_time(word['end'] / 1000.0)
            highlighted = ' '.join(f"{{\\c&HFF0000&}}{w['text'].upper()}{{\\c&HFFFFFF&}}" if j == i else w['text'].upper() for j, w in enumerate(caption['words'])).replace(',', '\\,')
            ass_content += f"Dialogue: 1,{word_start},{word_end},Default,,0,0,0,,{highlighted}\n"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(ass_content)
    content_clean = remove_unnecessary_backslashes(ass_content)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content_clean)
    logger.info("Subtitles created and cleaned")
    return output_file

def create_captioned_video_ffmpeg(input_video, subtitle_file, output_video):
    logger.info(f"Creating captioned video: {output_video}")
    subtitle_path_clean = subtitle_file.replace("\\", "/")
    input_path_clean = input_video.replace("\\", "/")
    output_path_clean = output_video.replace("\\", "/")
    cmd = ['ffmpeg', '-y', '-i', input_path_clean, '-vf', f'ass={subtitle_path_clean}', '-c:a', 'copy', '-preset', 'fast', '-vsync', 'cfr', output_path_clean]
    run_subprocess(cmd, f"Video created: {output_video}", "Video creation failed")

def process_video(input_video, output_video):
    try:
        video_info = get_video_info(input_video)
        audio_file = input_video.replace('.mp4', '_audio.mp3')
        extract_audio(input_video, audio_file)
        transcript = transcribe_audio(audio_file)
        captions = create_caption_groups(transcript['words'])
        subtitle_file = output_video.replace('.mp4', '.ass')
        create_ass_subtitles(captions, subtitle_file, video_info)
        create_captioned_video_ffmpeg(input_video, subtitle_file, output_video)
        os.remove(audio_file)
        notify_telegram(f"✅ Processed: {os.path.basename(input_video)}")
    except Exception as e:
        logger.error(f"Error processing {input_video}: {e}")
        notify_telegram(f"❌ Failed processing {os.path.basename(input_video)}\n{str(e)}")

def main():
    logger.info("=== AI Caption Creator Started ===")
    if not ASSEMBLYAI_API_KEY:
        raise EnvironmentError("ASSEMBLYAI_API_KEY not set")
    if not os.path.exists(HIGHLIGHTS_FILE):
        raise FileNotFoundError(f"No highlights file found: {HIGHLIGHTS_FILE}")
    with open(HIGHLIGHTS_FILE, 'r') as f:
        data = json.load(f)
        highlights = data["highlights"]
    for i, highlight in enumerate(highlights, 1):
        input_video = os.path.join(OUTPUT_DIR, f'segment_{i}.mp4')
        output_video = os.path.join(OUTPUT_DIR, f'short_{i}_ai_captions.mp4')
        logger.info(f"Processing video {i}/{len(highlights)}")
        process_video(input_video, output_video)
    logger.info("All videos processed.")
    notify_telegram("✅ All videos processed successfully!")

if __name__ == '__main__':
    main()
