import os
import json
import subprocess
import requests
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from openai import AzureOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ====== CONFIG ======
GOOGLE_SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME', 'Shorts Pipeline')
SHEET_TAB_NAME = os.getenv('SHEET_TAB_NAME', 'Sheet1')
CREDENTIALS_FILE = os.getenv('CREDENTIALS_FILE', 'automations-463516-2987a6762cd6.json')
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
OUTPUT_DIR = os.path.join(DOWNLOAD_DIR, 'shorts')

# AI Configuration
ASSEMBLYAI_API_KEY = os.getenv('ASSEMBLYAI_API_KEY')
ASSEMBLYAI_BASE_URL = 'https://api.assemblyai.com/v2'

client = AzureOpenAI(
    api_key=os.getenv('AZURE_OPENAI_API_KEY'),
    api_version=os.getenv('AZURE_OPENAI_API_VERSION'),
    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT')
)
# =====================

def download_podcast_with_captions(url):
    """Step 1-2: Download podcast video with English captions"""
    print(f"\n=== STEP 1-2: DOWNLOADING PODCAST ===")
    
    if not url.strip():
        print("[❌] Empty URL")
        return False
    
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    # Check for English captions first
    caption_cmd = [
        'yt-dlp',
        '--cookies', 'cookies.txt',  # Use cookies.txt file for auth
        '--write-subs',
        '--sub-langs', 'en',
        '--sub-format', 'vtt',
        '--skip-download',
        '-o', os.path.join(DOWNLOAD_DIR, 'podcast'),
        url
    ]
    
    print("[📝] Checking for English captions...")
    try:
        subprocess.run(caption_cmd, check=True, capture_output=True)
        
        # Check if caption file exists
        vtt_file = os.path.join(DOWNLOAD_DIR, 'podcast.en.vtt')
        if not os.path.exists(vtt_file):
            print("[❌] No English captions found")
            return False
        
        print("[✅] English captions found!")
        
    except subprocess.CalledProcessError:
        print("[❌] Failed to get captions")
        return False
    
    # Download video
    video_cmd = [
        'yt-dlp',
        '--cookies', 'cookies.txt',  # Use cookies.txt file for auth
        '--force-overwrites',
        '--format', 'mp4[height<=1080]/best[height<=1080][ext=mp4]',
        '-o', os.path.join(DOWNLOAD_DIR, 'podcast.mp4'),
        url
    ]
    
    print("[🎥] Downloading podcast video...")
    try:
        subprocess.run(video_cmd, check=True)
        print("[✅] Podcast downloaded successfully!")
        return True
    except subprocess.CalledProcessError:
        print("[❌] Failed to download video")
        return False

def find_viral_segments_with_gpt():
    """Step 3: Use GPT-4o to find 60-second viral segments"""
    print(f"\n=== STEP 3: FINDING VIRAL SEGMENTS ===")
    
    vtt_file = os.path.join(DOWNLOAD_DIR, 'podcast.en.vtt')
    if not os.path.exists(vtt_file):
        print("[❌] No VTT file found")
        return None
    
    # Parse VTT file
    with open(vtt_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract full transcript with timestamps
    full_text = ""
    lines = content.split('\n')
    
    for i, line in enumerate(lines):
        if '-->' in line:
            # Get timestamp
            timestamp = line.split(' --> ')[0].strip()
            
            # Get text from next lines
            j = i + 1
            text_lines = []
            while j < len(lines) and lines[j].strip() and not '-->' in lines[j]:
                if not lines[j].strip().isdigit():
                    text_lines.append(lines[j].strip())
                j += 1
            
            if text_lines:
                full_text += f"{timestamp}: {' '.join(text_lines)}\n"
    
    print(f"[📊] Extracted {len(full_text.split('\\n'))} caption segments")
    
    # GPT-4o prompt for finding viral segments
    prompt = f"""
FIND 3 VIRAL 60-SECOND YOUTUBE SHORTS FROM THIS PODCAST TRANSCRIPT.

TRANSCRIPT WITH TIMESTAMPS:
{full_text}

Find 3 different continuous 60-second segments that will go VIRAL on YouTube Shorts.

VIRAL CRITERIA:
- Strong emotional hook at the beginning
- Shocking revelations or contrarian takes
- Specific numbers, stats, or examples
- Makes people want to share or comment
- Complete thought/story arc in 60 seconds

Return ONLY this JSON:
[
  {{
    "start_time": "MM:SS",
    "summary": "Why this will go viral",
    "hook": "Opening line that grabs attention"
  }},
  {{
    "start_time": "MM:SS", 
    "summary": "Why this will go viral",
    "hook": "Opening line that grabs attention"
  }},
  {{
    "start_time": "MM:SS",
    "summary": "Why this will go viral", 
    "hook": "Opening line that grabs attention"
  }}
]
"""

    try:
        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o"),
            messages=[
                {"role": "system", "content": "You are an expert at finding viral YouTube Shorts moments from podcast transcripts."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800
        )
        
        response_text = response.choices[0].message.content.strip()
        print(f"[🤖] GPT-4o found viral segments!")
        
        # Extract JSON
        if '[' in response_text and ']' in response_text:
            start = response_text.find('[')
            end = response_text.rfind(']') + 1
            json_text = response_text[start:end]
            segments = json.loads(json_text)
            
            # Convert MM:SS to seconds and add duration
            for segment in segments:
                time_parts = segment['start_time'].split(':')
                start_seconds = int(time_parts[0]) * 60 + int(time_parts[1])
                segment['start_seconds'] = start_seconds
                segment['duration'] = 60  # Fixed 60-second clips
            
            print(f"[📊] Found {len(segments)} viral segments:")
            for i, seg in enumerate(segments, 1):
                print(f"   {i}. {seg['start_time']} - {seg['summary'][:50]}...")
            
            return segments
        else:
            print("[❌] No JSON found in GPT response")
            return None
            
    except Exception as e:
        print(f"[❌] GPT-4o segment detection failed: {e}")
        return None

def create_fullscreen_clip(segment, index):
    """Step 4: Create full-screen MP4 and MP3 clips"""
    print(f"\n=== STEP 4: CREATING FULLSCREEN CLIP {index} ===")
    
    start_time = segment['start_seconds']
    duration = segment['duration']
    
    podcast_video = os.path.join(DOWNLOAD_DIR, 'podcast.mp4')
    clip_video = os.path.join(OUTPUT_DIR, f'clip_{index}.mp4')
    clip_audio = os.path.join(OUTPUT_DIR, f'clip_{index}.mp3')
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Create full-screen 9:16 video clip
    video_cmd = [
        'ffmpeg', '-y',
        '-i', podcast_video,
        '-ss', str(start_time),
        '-t', str(duration),
        '-vf', 'scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280',
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-preset', 'fast',
        clip_video
    ]
    
    print(f"[🎬] Creating full-screen video clip...")
    subprocess.run(video_cmd, check=True)
    
    # Extract audio for AssemblyAI
    audio_cmd = [
        'ffmpeg', '-y',
        '-i', clip_video,
        '-vn',
        '-acodec', 'libmp3lame',
        '-ar', '16000',
        '-ac', '1',
        '-b:a', '64k',
        clip_audio
    ]
    
    print(f"[🎵] Extracting audio for transcription...")
    subprocess.run(audio_cmd, check=True)
    
    print(f"[✅] Created clip {index}: {clip_video}")
    return clip_video, clip_audio

def get_assemblyai_transcript(audio_file):
    """Step 5: Get word-level transcript from AssemblyAI"""
    print(f"\n=== STEP 5: ASSEMBLYAI TRANSCRIPTION ===")
    
    if not ASSEMBLYAI_API_KEY:
        print("[❌] ASSEMBLYAI_API_KEY not found in .env")
        print("Get your API key at: https://www.assemblyai.com/")
        return None
    
    headers = {'authorization': ASSEMBLYAI_API_KEY}
    
    # Upload audio
    print("[☁️] Uploading to AssemblyAI...")
    with open(audio_file, 'rb') as f:
        upload_response = requests.post(
            f'{ASSEMBLYAI_BASE_URL}/upload',
            headers=headers,
            files={'file': f}
        )
    
    if upload_response.status_code != 200:
        print(f"[❌] Upload failed: {upload_response.text}")
        return None
    
    audio_url = upload_response.json()['upload_url']
    
    # Request transcription with word-level timestamps
    transcript_request = {
        'audio_url': audio_url,
        'word_boost': ['Jensen', 'Huang', 'NVIDIA', 'GPU', 'CPU', 'AI', 'technology'],
        'format_text': True,
        'speaker_labels': False,
        'language_code': 'en_us'
    }
    
    response = requests.post(
        f'{ASSEMBLYAI_BASE_URL}/transcript',
        json=transcript_request,
        headers=headers
    )
    
    if response.status_code != 200:
        print(f"[❌] Transcription request failed: {response.text}")
        return None
    
    transcript_id = response.json()['id']
    
    # Poll for completion
    print("[🤖] Transcribing with AssemblyAI...")
    while True:
        result_response = requests.get(
            f'{ASSEMBLYAI_BASE_URL}/transcript/{transcript_id}',
            headers=headers
        )
        
        result = result_response.json()
        
        if result['status'] == 'completed':
            print(f"[✅] Transcription completed!")
            return result
        elif result['status'] == 'error':
            print(f"[❌] Transcription failed: {result['error']}")
            return None
        
        print(f"[⏳] Status: {result['status']}...")
        time.sleep(3)

def create_word_highlighted_video(clip_video, transcript_result, segment, index):
    """Step 6: Create video with real-time word highlighting"""
    print(f"\n=== STEP 6: CREATING WORD-HIGHLIGHTED VIDEO {index} ===")
    
    if not transcript_result or 'words' not in transcript_result:
        print("[❌] No word-level data available")
        return None
    
    words = transcript_result['words']
    final_video = os.path.join(OUTPUT_DIR, f'short_{index}_final.mp4')
    
    # Create word groups (3-4 words each)
    word_groups = []
    i = 0
    while i < len(words):
        group_size = min(4, len(words) - i)  # 3-4 words per group
        group_words = words[i:i + group_size]
        
        if group_words:
            word_groups.append({
                'text': ' '.join([w['text'] for w in group_words]),
                'start': group_words[0]['start'] / 1000.0,  # Convert ms to seconds
                'end': group_words[-1]['end'] / 1000.0 + 0.1
            })
        
        i += group_size
    
    print(f"[📊] Created {len(word_groups)} word groups for highlighting")
    
    # Create ASS subtitle file with word highlighting
    ass_file = final_video.replace('.mp4', '.ass')
    
    ass_content = """[Script Info]
Title: Real-time Word Highlighting
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,32,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,3,1,2,30,30,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # Add word groups with perfect timing
    for group in word_groups:
        start_time = f"{int(group['start']//3600):01d}:{int((group['start']%3600)//60):02d}:{group['start']%60:06.3f}"
        end_time = f"{int(group['end']//3600):01d}:{int((group['end']%3600)//60):02d}:{group['end']%60:06.3f}"
        
        # Emphasize key words
        text = group['text']
        key_words = ['Jensen', 'Huang', 'NVIDIA', 'GPU', 'CPU', 'AI', 'billion', 'trillion']
        for word in key_words:
            text = text.replace(word, word.upper())
        
        ass_content += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}\n"
    
    # Write ASS file
    with open(ass_file, 'w', encoding='utf-8') as f:
        f.write(ass_content)
    
    # Apply captions to video
    cmd = [
        'ffmpeg', '-y',
        '-i', clip_video,
        '-vf', f'ass={ass_file}',
        '-c:a', 'copy',
        '-preset', 'fast',
        final_video
    ]
    
    print(f"[📝] Adding real-time word highlighting...")
    subprocess.run(cmd, check=True)
    
    # Clean up temporary files
    os.remove(ass_file)
    
    print(f"[✅] Created final short: {final_video}")
    return final_video

def update_sheet_status(row_idx, status):
    """Update Google Sheet status"""
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).worksheet(SHEET_TAB_NAME)
        
        # Update status column (assuming it's column 2)
        sheet.update_cell(row_idx, 2, status)
        print(f"[📊] Updated sheet status: {status}")
    except Exception as e:
        print(f"[⚠️] Failed to update sheet: {e}")

def main():
    print("=== FULLSCREEN SHORTS PIPELINE ===\n")
    
    # Check AssemblyAI API key
    if not ASSEMBLYAI_API_KEY:
        print("[❌] Please add ASSEMBLYAI_API_KEY to your .env file")
        print("Get your free API key at: https://www.assemblyai.com/")
        return
    
    # Get pending URL from Google Sheets
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        gc = gspread.authorize(creds)
        sheet = gc.open(GOOGLE_SHEET_NAME).worksheet(SHEET_TAB_NAME)
        data = sheet.get_all_records()
        
        pending_row = None
        row_idx = None
        
        for idx, row in enumerate(data, start=2):
            if row.get("status", "").lower() == "pending":
                pending_row = row
                row_idx = idx
                break
        
        if not pending_row:
            print("[ℹ️] No pending rows found in Google Sheets")
            return
        
        podcast_url = pending_row.get("podcast_url", "").strip()
        if not podcast_url:
            print("[❌] No podcast URL in pending row")
            return
        
        print(f"[🎯] Processing: {podcast_url}")
        
    except Exception as e:
        print(f"[❌] Google Sheets error: {e}")
        return
    
    try:
        # Step 1-2: Download podcast with captions
        if not download_podcast_with_captions(podcast_url):
            update_sheet_status(row_idx, "no_captions")
            return
        
        # Step 3: Find viral segments
        segments = find_viral_segments_with_gpt()
        if not segments:
            update_sheet_status(row_idx, "no_segments")
            return
        
        # Step 4-6: Process each segment
        created_shorts = []
        for i, segment in enumerate(segments, 1):
            print(f"\n[🎯] Processing Segment {i}: {segment['summary'][:50]}...")
            
            # Step 4: Create fullscreen clip
            clip_video, clip_audio = create_fullscreen_clip(segment, i)
            
            # Step 5: Get AssemblyAI transcript
            transcript = get_assemblyai_transcript(clip_audio)
            
            if transcript:
                # Step 6: Create final video with word highlighting
                final_video = create_word_highlighted_video(clip_video, transcript, segment, i)
                if final_video:
                    created_shorts.append(final_video)
            
            # Clean up temporary audio file
            if os.path.exists(clip_audio):
                os.remove(clip_audio)
        
        if created_shorts:
            update_sheet_status(row_idx, "completed")
            print(f"\n[🎉] SUCCESS! Created {len(created_shorts)} viral shorts:")
            for short in created_shorts:
                print(f"   📱 {short}")
        else:
            update_sheet_status(row_idx, "failed")
            print(f"\n[❌] Failed to create any shorts")
            
    except Exception as e:
        print(f"[❌] Pipeline error: {e}")
        update_sheet_status(row_idx, "error")

if __name__ == "__main__":
    main() 