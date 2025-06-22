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
PODCAST_VIDEO = os.path.join(DOWNLOAD_DIR, 'podcast.mp4')
OUTPUT_DIR = os.path.join(DOWNLOAD_DIR, 'shorts')

# AssemblyAI API Configuration
ASSEMBLYAI_API_KEY = os.getenv('ASSEMBLYAI_API_KEY')  # Add this to your .env
ASSEMBLYAI_BASE_URL = 'https://api.assemblyai.com/v2'
# =====================

def extract_audio_segment(video_file, start_time, duration, output_audio):
    """Extract audio segment for transcription"""
    cmd = [
        'ffmpeg', '-y',
        '-i', video_file,
        '-ss', str(start_time),
        '-t', str(duration),
        '-vn',  # No video
        '-acodec', 'pcm_s16le',  # Uncompressed audio for best quality
        '-ar', '16000',  # 16kHz sample rate (optimal for speech)
        '-ac', '1',  # Mono
        output_audio
    ]
    
    print(f"[🎵] Extracting audio segment...")
    subprocess.run(cmd, check=True, capture_output=True)

def upload_audio_to_assemblyai(audio_file):
    """Upload audio file to AssemblyAI"""
    headers = {'authorization': ASSEMBLYAI_API_KEY}
    
    with open(audio_file, 'rb') as f:
        response = requests.post(
            f'{ASSEMBLYAI_BASE_URL}/upload',
            headers=headers,
            files={'file': f}
        )
    
    if response.status_code != 200:
        raise Exception(f"Upload failed: {response.text}")
    
    return response.json()['upload_url']

def transcribe_with_assemblyai(audio_url):
    """Transcribe audio with word-level timestamps"""
    headers = {
        'authorization': ASSEMBLYAI_API_KEY,
        'content-type': 'application/json'
    }
    
    # Request transcription with word-level timestamps
    data = {
        'audio_url': audio_url,
        'word_boost': ['Jensen', 'Huang', 'NVIDIA', 'GPU', 'CPU', 'AI'],  # Boost tech terms
        'format_text': True,  # Better punctuation
        'speaker_labels': False,  # Single speaker
        'language_code': 'en_us'
    }
    
    response = requests.post(
        f'{ASSEMBLYAI_BASE_URL}/transcript',
        json=data,
        headers=headers
    )
    
    if response.status_code != 200:
        raise Exception(f"Transcription request failed: {response.text}")
    
    transcript_id = response.json()['id']
    
    # Poll for completion
    print(f"[🤖] Transcribing with AssemblyAI...")
    while True:
        response = requests.get(
            f'{ASSEMBLYAI_BASE_URL}/transcript/{transcript_id}',
            headers=headers
        )
        
        result = response.json()
        
        if result['status'] == 'completed':
            return result
        elif result['status'] == 'error':
            raise Exception(f"Transcription failed: {result['error']}")
        
        print(f"[⏳] Status: {result['status']}...")
        time.sleep(5)

def create_word_groups_from_ai(words, words_per_group=3):
    """Create word groups from AI transcription with perfect timing"""
    groups = []
    
    i = 0
    while i < len(words):
        # Smart grouping: 2-4 words based on natural breaks
        group_size = 3  # Default
        
        # Look ahead for punctuation to create natural breaks
        if i + 3 < len(words):
            next_words = [words[j]['text'] for j in range(i, min(i + 5, len(words)))]
            # If there's punctuation in next 2-4 words, adjust group size
            for j, word in enumerate(next_words[1:4], 1):
                if any(punct in word for punct in ['.', '!', '?', ',', ':']):
                    group_size = j + 1
                    break
        
        group_size = min(group_size, len(words) - i)
        group_words = words[i:i + group_size]
        
        if group_words:
            groups.append({
                'text': ' '.join([w['text'] for w in group_words]),
                'start': group_words[0]['start'] / 1000.0,  # Convert ms to seconds
                'end': group_words[-1]['end'] / 1000.0 + 0.1  # Add small buffer
            })
        
        i += group_size
    
    return groups

def create_ai_caption_video(input_video, word_groups, output_video):
    """Create video with AI-generated captions"""
    
    # Create ASS subtitle file with perfect timing
    ass_file = output_video.replace('.mp4', '.ass')
    
    # Professional ASS styling
    ass_content = """[Script Info]
Title: AI-Generated Captions
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,28,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,2,1,2,30,30,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # Add each word group with precise timing
    for group in word_groups:
        start_time = f"{int(group['start']//3600):01d}:{int((group['start']%3600)//60):02d}:{group['start']%60:06.3f}"
        end_time = f"{int(group['end']//3600):01d}:{int((group['end']%3600)//60):02d}:{group['end']%60:06.3f}"
        text = group['text'].replace(',', '\\,').upper()  # Uppercase for impact
        
        ass_content += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}\n"
    
    # Write ASS file
    with open(ass_file, 'w', encoding='utf-8') as f:
        f.write(ass_content)
    
    # Apply captions to video
    cmd = [
        'ffmpeg', '-y',
        '-i', input_video,
        '-vf', f'ass={ass_file}',
        '-c:a', 'copy',
        '-preset', 'fast',
        output_video
    ]
    
    print(f"[📝] Adding AI-generated captions...")
    subprocess.run(cmd, check=True)
    
    # Clean up
    os.remove(ass_file)

def create_ai_captioned_short(highlight, index):
    """Create a YouTube Short with AI-generated captions"""
    print(f"\n=== CREATING AI-CAPTIONED SHORT {index} ===")
    
    start_time = highlight['start']
    duration = highlight['duration']
    
    # File paths
    layout_video = os.path.join(OUTPUT_DIR, f'short_{index}_layout.mp4')
    audio_file = os.path.join(OUTPUT_DIR, f'short_{index}_audio.wav')
    final_video = os.path.join(OUTPUT_DIR, f'short_{index}_ai_captions.mp4')
    
    if not os.path.exists(layout_video):
        print(f"[❌] Layout video not found: {layout_video}")
        return None
    
    try:
        # Step 1: Extract audio segment
        extract_audio_segment(PODCAST_VIDEO, start_time, duration, audio_file)
        
        # Step 2: Upload to AssemblyAI
        print(f"[☁️] Uploading to AssemblyAI...")
        audio_url = upload_audio_to_assemblyai(audio_file)
        
        # Step 3: Get AI transcription with word timestamps
        transcript_result = transcribe_with_assemblyai(audio_url)
        
        # Step 4: Create word groups from AI data
        if 'words' in transcript_result:
            word_groups = create_word_groups_from_ai(transcript_result['words'])
            
            print(f"[📊] AI found {len(word_groups)} caption groups:")
            for group in word_groups[:5]:  # Show first 5
                print(f"   {group['start']:.1f}s-{group['end']:.1f}s: '{group['text']}'")
            
            # Step 5: Create video with AI captions
            create_ai_caption_video(layout_video, word_groups, final_video)
            
            print(f"[✅] Created AI-captioned Short {index}: {final_video}")
            
            # Cleanup
            os.remove(audio_file)
            
            return final_video
        else:
            print(f"[❌] No word-level data from AssemblyAI")
            return None
            
    except Exception as e:
        print(f"[❌] Error creating AI captions: {e}")
        # Cleanup on error
        if os.path.exists(audio_file):
            os.remove(audio_file)
        return None

def main():
    print("=== AI-POWERED CAPTION CREATOR ===\n")
    
    # Check API key
    if not ASSEMBLYAI_API_KEY:
        print("[❌] Please add ASSEMBLYAI_API_KEY to your .env file")
        print("Get your API key at: https://www.assemblyai.com/")
        return
    
    # Load highlights
    if not os.path.exists(HIGHLIGHTS_FILE):
        print(f"[❌] No highlights file found: {HIGHLIGHTS_FILE}")
        return
    
    with open(HIGHLIGHTS_FILE, 'r') as f:
        highlights = json.load(f)
    
    # Create AI-captioned shorts
    created_shorts = []
    for i, highlight in enumerate(highlights, 1):
        print(f"\n[🎯] Processing Short {i}: {highlight['summary'][:50]}...")
        
        short_file = create_ai_captioned_short(highlight, i)
        if short_file:
            created_shorts.append(short_file)
    
    print(f"\n[🎉] SUCCESS! Created {len(created_shorts)} AI-captioned Shorts:")
    for short in created_shorts:
        print(f"   📱 {short}")
    
    print(f"\n[💡] Pro tip: Compare these AI captions with your VTT-based ones!")

if __name__ == "__main__":
    main() 