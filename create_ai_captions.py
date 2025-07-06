import os
import json
import requests
import time
import subprocess
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ====== CONFIG ======
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
HIGHLIGHTS_FILE = os.path.join(DOWNLOAD_DIR, 'highlights.json')
OUTPUT_DIR = os.path.join(DOWNLOAD_DIR, 'shorts')

ASSEMBLYAI_API_KEY = os.getenv('ASSEMBLYAI_API_KEY')
ASSEMBLYAI_BASE_URL = 'https://api.assemblyai.com/v2'

def extract_audio(video_file, output_audio):
    """Extract audio as mp3 from video"""
    print(f"[AUDIO] Extracting audio from {video_file}")
    output_audio = output_audio.replace('.wav', '.mp3')
    cmd = [
        'ffmpeg', '-y',
        '-i', video_file,
        '-vn', '-acodec', 'libmp3lame',
        '-ar', '44100', '-ab', '192k', '-ac', '1',
        output_audio
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"ffmpeg error: {result.stderr}")
    print(f"[SUCCESS] Audio extracted: {output_audio}")
    return output_audio

def transcribe_audio(audio_file):
    """Transcribe audio with AssemblyAI and return transcript JSON"""
    if not ASSEMBLYAI_API_KEY:
        raise Exception("ASSEMBLYAI_API_KEY not set")

    headers = {'authorization': ASSEMBLYAI_API_KEY}

    # Upload audio
    print("[UPLOAD] Uploading to AssemblyAI...")
    with open(audio_file, 'rb') as f:
        response = requests.post(f'{ASSEMBLYAI_BASE_URL}/upload', headers=headers, files={'file': ('audio.mp3', f, 'audio/mpeg')})
    response.raise_for_status()
    audio_url = response.json()['upload_url']

    # Request transcription
    response = requests.post(f'{ASSEMBLYAI_BASE_URL}/transcript',
                             json={'audio_url': audio_url, 'format_text': True, 'language_code': 'en_us'},
                             headers=headers)
    response.raise_for_status()
    transcript_id = response.json()['id']

    # Poll for completion
    print("[AI] Transcribing...")
    while True:
        response = requests.get(f'{ASSEMBLYAI_BASE_URL}/transcript/{transcript_id}', headers=headers)
        status = response.json()
        if status['status'] == 'completed':
            print("[SUCCESS] Transcription complete!")
            return status
        elif status['status'] == 'error':
            raise Exception(f"Transcription failed: {status['error']}")
        time.sleep(3)

def create_caption_groups(words):
    """Group words into caption chunks with no overlaps"""
    if not words:
        return []

    captions = []
    current_group = []

    for word in words:
        if (not current_group or len(current_group) >= 4 or
            any(p in word['text'] for p in ['.', '!', '?', ',']) or
            (current_group and (word['start'] - current_group[0]['start']) / 1000.0 > 3.0)):
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

def get_video_info(video_file):
    """Get video info using ffprobe"""
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_format', '-show_streams', video_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
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

def create_ass_subtitles(captions, output_file, video_info):
    """Create ASS subtitle file with in-place word highlighting"""
    print(f"[INFO] Creating in-place word highlighting subtitles: {output_file}")
    ass_content = f"""[Script Info]
Title: AI In-Place Word Captions
ScriptType: v4.00+
PlayResX: {video_info['width']}
PlayResY: {video_info['height']}
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{int(video_info['height']/12)},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,30,30,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    for caption in captions:
        words = caption['words']
        for i, word in enumerate(words):
            word_start = word['start'] / 1000.0
            word_end = word['end'] / 1000.0

            start_str = f"{int(word_start//3600)}:{int((word_start%3600)//60):02d}:{int(word_start%60):02d}.{int((word_start%1)*100):02d}"
            end_str = f"{int(word_end//3600)}:{int((word_end%3600)//60):02d}:{int(word_end%60):02d}.{int((word_end%1)*100):02d}"

            # Build the highlighted text with correct { } wrapping for ASS overrides
            highlighted_words = []
            for j, w in enumerate(words):
                if i == j:
                    highlighted_words.append(f"{{\\c&H0000FF&}}{w['text'].upper()}{{\\c&HFFFFFF&}}")
                else:
                    highlighted_words.append(w['text'].upper())
            highlighted_text = ' '.join(highlighted_words)
            highlighted_text = highlighted_text.replace(',', '\\,')

            ass_content += f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{highlighted_text}\n"

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(ass_content)
    print("[SUCCESS] Subtitle file created")
    return output_file

def create_captioned_video_ffmpeg(input_video, subtitle_file, output_video):
    """Create final video with captions using ffmpeg and ASS subtitles"""
    print(f"[VIDEO] Creating captioned video with ffmpeg: {output_video}")

    input_video_ffmpeg = input_video.replace('\\', '/')
    subtitle_file_ffmpeg = subtitle_file.replace('\\', '/')
    output_video_ffmpeg = output_video.replace('\\', '/')

    cmd = [
        'ffmpeg', '-y',
        '-i', input_video_ffmpeg,
        '-vf', f'ass={subtitle_file_ffmpeg}',
        '-c:a', 'copy',
        '-preset', 'fast',
        '-vsync', 'cfr',
        output_video_ffmpeg
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"ffmpeg error: {result.stderr}")
    print("[SUCCESS] Video created successfully")

def process_video(input_video, output_video):
    """Process a single video"""
    video_info = get_video_info(input_video)
    audio_file = input_video.replace('.mp4', '_audio.mp3')
    extract_audio(input_video, audio_file)
    transcript = transcribe_audio(audio_file)
    captions = create_caption_groups(transcript['words'])
    subtitle_file = output_video.replace('.mp4', '.ass')
    create_ass_subtitles(captions, subtitle_file, video_info)
    create_captioned_video_ffmpeg(input_video, subtitle_file, output_video)
    os.remove(audio_file)

def main():
    print("=== AI CAPTION CREATOR (Word Highlight Fix) ===")
    if not ASSEMBLYAI_API_KEY:
        raise Exception("ASSEMBLYAI_API_KEY not set")
    if not os.path.exists(HIGHLIGHTS_FILE):
        raise Exception(f"No highlights file found: {HIGHLIGHTS_FILE}")

    with open(HIGHLIGHTS_FILE, 'r') as f:
        highlights = json.load(f)

    for i, highlight in enumerate(highlights, 1):
        input_video = os.path.join(OUTPUT_DIR, f'segment_{i}.mp4')
        output_video = os.path.join(OUTPUT_DIR, f'short_{i}_ai_captions.mp4')
        print(f"\n[TARGET] Processing video {i}/{len(highlights)}")
        process_video(input_video, output_video)

    print("\n[SUCCESS] All videos processed successfully!")

if __name__ == '__main__':
    main()
