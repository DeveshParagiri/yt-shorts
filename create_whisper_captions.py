import os
import json
import subprocess
from openai import AzureOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ====== CONFIG ======
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
HIGHLIGHTS_FILE = os.path.join(DOWNLOAD_DIR, 'highlights.json')
PODCAST_VIDEO = os.path.join(DOWNLOAD_DIR, 'podcast.mp4')
OUTPUT_DIR = os.path.join(DOWNLOAD_DIR, 'shorts')

# Azure OpenAI Configuration (you already have this!)
client = AzureOpenAI(
    api_key=os.getenv('AZURE_OPENAI_API_KEY'),
    api_version=os.getenv('AZURE_OPENAI_API_VERSION'),
    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT')
)
# =====================

def extract_audio_segment(video_file, start_time, duration, output_audio):
    """Extract audio segment for Whisper transcription"""
    cmd = [
        'ffmpeg', '-y',
        '-i', video_file,
        '-ss', str(start_time),
        '-t', str(duration),
        '-vn',  # No video
        '-acodec', 'libmp3lame',  # MP3 for Whisper
        '-ar', '16000',  # 16kHz sample rate
        '-ac', '1',  # Mono
        '-b:a', '64k',  # Compress for faster upload
        output_audio
    ]
    
    print(f"[🎵] Extracting audio segment...")
    subprocess.run(cmd, check=True, capture_output=True)

def transcribe_with_whisper(audio_file):
    """Transcribe audio with OpenAI Whisper (word-level timestamps)"""
    print(f"[🤖] Transcribing with OpenAI Whisper...")
    
    with open(audio_file, 'rb') as f:
        transcript = client.audio.transcriptions.create(
            model=os.getenv('AZURE_OPENAI_WHISPER_DEPLOYMENT', 'whisper'),
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["word"]
        )
    
    return transcript

def create_word_groups_from_whisper(words, words_per_group=3):
    """Create word groups from Whisper transcription with perfect timing"""
    groups = []
    
    i = 0
    while i < len(words):
        # Smart grouping based on natural speech patterns
        group_size = 3  # Default
        
        # Look for natural breaks (punctuation, pauses)
        if i + 3 < len(words):
            # Check for longer pauses between words (>0.5s gap)
            for j in range(1, min(4, len(words) - i)):
                if j < len(words) - i - 1:
                    current_end = words[i + j]['end']
                    next_start = words[i + j + 1]['start']
                    if next_start - current_end > 0.5:  # 500ms pause
                        group_size = j + 1
                        break
        
        group_size = min(group_size, len(words) - i)
        group_words = words[i:i + group_size]
        
        if group_words:
            groups.append({
                'text': ' '.join([w['word'] for w in group_words]),
                'start': group_words[0]['start'],
                'end': group_words[-1]['end'] + 0.1  # Small buffer
            })
        
        i += group_size
    
    return groups

def create_whisper_caption_video(input_video, word_groups, output_video):
    """Create video with Whisper-generated captions"""
    
    # Create ASS subtitle file with perfect timing
    ass_file = output_video.replace('.mp4', '.ass')
    
    # Professional ASS styling optimized for mobile
    ass_content = """[Script Info]
Title: Whisper AI Captions
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,30,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,2,1,2,25,25,45,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # Add each word group with precise timing
    for group in word_groups:
        start_time = f"{int(group['start']//3600):01d}:{int((group['start']%3600)//60):02d}:{group['start']%60:06.3f}"
        end_time = f"{int(group['end']//3600):01d}:{int((group['end']%3600)//60):02d}:{group['end']%60:06.3f}"
        
        # Smart capitalization for impact
        text = group['text'].replace(',', '\\,')
        # Capitalize key words
        key_words = ['Jensen', 'Huang', 'NVIDIA', 'GPU', 'CPU', 'AI', 'time', 'machine', 'future']
        for word in key_words:
            text = text.replace(word.lower(), word.upper())
            text = text.replace(word.capitalize(), word.upper())
        
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
    
    print(f"[📝] Adding Whisper-generated captions...")
    subprocess.run(cmd, check=True)
    
    # Clean up
    os.remove(ass_file)

def create_whisper_captioned_short(highlight, index):
    """Create a YouTube Short with Whisper AI captions"""
    print(f"\n=== CREATING WHISPER-CAPTIONED SHORT {index} ===")
    
    start_time = highlight['start']
    duration = highlight['duration']
    
    # File paths
    layout_video = os.path.join(OUTPUT_DIR, f'short_{index}_layout.mp4')
    audio_file = os.path.join(OUTPUT_DIR, f'short_{index}_audio.mp3')
    final_video = os.path.join(OUTPUT_DIR, f'short_{index}_whisper_captions.mp4')
    
    if not os.path.exists(layout_video):
        print(f"[❌] Layout video not found: {layout_video}")
        return None
    
    try:
        # Step 1: Extract audio segment
        extract_audio_segment(PODCAST_VIDEO, start_time, duration, audio_file)
        
        # Step 2: Transcribe with Whisper
        transcript_result = transcribe_with_whisper(audio_file)
        
        # Step 3: Create word groups from Whisper data
        if hasattr(transcript_result, 'words') and transcript_result.words:
            # Convert Whisper word objects to dictionaries
            words = []
            for word in transcript_result.words:
                words.append({
                    'word': word.word,
                    'start': word.start,
                    'end': word.end
                })
            
            word_groups = create_word_groups_from_whisper(words)
            
            print(f"[📊] Whisper found {len(word_groups)} caption groups:")
            for group in word_groups[:5]:  # Show first 5
                print(f"   {group['start']:.1f}s-{group['end']:.1f}s: '{group['text']}'")
            
            # Step 4: Create video with Whisper captions
            create_whisper_caption_video(layout_video, word_groups, final_video)
            
            print(f"[✅] Created Whisper-captioned Short {index}: {final_video}")
            
            # Cleanup
            os.remove(audio_file)
            
            return final_video
        else:
            print(f"[❌] No word-level data from Whisper")
            # Fallback: use sentence-level transcription
            print(f"[📝] Full transcript: {transcript_result.text}")
            return None
            
    except Exception as e:
        print(f"[❌] Error creating Whisper captions: {e}")
        # Cleanup on error
        if os.path.exists(audio_file):
            os.remove(audio_file)
        return None

def main():
    print("=== WHISPER AI CAPTION CREATOR ===\n")
    
    # Load highlights
    if not os.path.exists(HIGHLIGHTS_FILE):
        print(f"[❌] No highlights file found: {HIGHLIGHTS_FILE}")
        return
    
    with open(HIGHLIGHTS_FILE, 'r') as f:
        highlights = json.load(f)
    
    # Create Whisper-captioned shorts
    created_shorts = []
    for i, highlight in enumerate(highlights, 1):
        print(f"\n[🎯] Processing Short {i}: {highlight['summary'][:50]}...")
        
        short_file = create_whisper_captioned_short(highlight, i)
        if short_file:
            created_shorts.append(short_file)
    
    print(f"\n[🎉] SUCCESS! Created {len(created_shorts)} Whisper-captioned Shorts:")
    for short in created_shorts:
        print(f"   📱 {short}")
    
    print(f"\n[💡] These use your existing Azure OpenAI Whisper deployment!")

if __name__ == "__main__":
    main() 