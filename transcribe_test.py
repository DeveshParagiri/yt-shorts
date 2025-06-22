import os
import subprocess
import json
from dotenv import load_dotenv
from openai import AzureOpenAI

# Load environment variables
load_dotenv()

# ====== CONFIG ======
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
AUDIO_FILE = os.path.join(DOWNLOAD_DIR, 'podcast_audio.mp3')
TRANSCRIPT_FILE = os.path.join(DOWNLOAD_DIR, 'transcript.txt')
TRANSCRIPT_JSON_FILE = os.path.join(DOWNLOAD_DIR, 'transcript_with_timestamps.json')
SUBTITLES_FILE = os.path.join(DOWNLOAD_DIR, 'subtitles.vtt')
# =====================

def get_video_subtitles(url, filename):
    """Try to get existing English subtitles from video"""
    if not url.strip():
        return False
        
    output_path = os.path.join(DOWNLOAD_DIR, filename.replace('.mp4', ''))
    cmd = [
        'yt-dlp',
        '--write-subs',
        '--write-auto-subs',
        '--sub-langs', 'en',
        '--sub-format', 'vtt',
        '--skip-download',  # Only get subtitles, not video
        '-o', output_path,
        url
    ]
    
    print(f"[📝] Checking for English subtitles...")
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        
        # Check if subtitle file was created
        possible_sub_files = [
            f"{output_path}.en.vtt",
            f"{output_path}.en-US.vtt", 
            f"{output_path}.en-GB.vtt"
        ]
        
        for sub_file in possible_sub_files:
            if os.path.exists(sub_file):
                # Move to standard location
                os.rename(sub_file, SUBTITLES_FILE)
                print(f"[✅] Found English subtitles: {SUBTITLES_FILE}")
                return True
                
        print("[❌] No English subtitles found")
        return False
        
    except subprocess.CalledProcessError:
        print("[❌] Failed to check subtitles")
        return False

def parse_vtt_to_json(vtt_file):
    """Convert VTT subtitles to JSON with timestamps"""
    if not os.path.exists(vtt_file):
        return None
        
    segments = []
    current_segment = None
    
    with open(vtt_file, 'r') as f:
        lines = f.readlines()
    
    for line in lines:
        line = line.strip()
        
        # Skip header and empty lines
        if line.startswith('WEBVTT') or line == '' or line.startswith('NOTE'):
            continue
            
        # Timeline format: 00:00:10.500 --> 00:00:13.000
        if '-->' in line:
            parts = line.split(' --> ')
            if len(parts) == 2:
                start_time = vtt_time_to_seconds(parts[0])
                end_time = vtt_time_to_seconds(parts[1])
                current_segment = {
                    'start': start_time,
                    'end': end_time,
                    'text': ''
                }
        # Text content
        elif current_segment is not None and line:
            # Remove VTT formatting tags
            clean_text = line.replace('<c>', '').replace('</c>', '')
            current_segment['text'] += clean_text + ' '
            
        # Empty line means segment ended
        elif current_segment is not None:
            current_segment['text'] = current_segment['text'].strip()
            if current_segment['text']:
                segments.append(current_segment)
            current_segment = None
    
    # Don't forget the last segment
    if current_segment is not None and current_segment['text'].strip():
        segments.append(current_segment)
    
    return {
        'text': ' '.join([seg['text'] for seg in segments]),
        'segments': segments
    }

def vtt_time_to_seconds(time_str):
    """Convert VTT timestamp to seconds"""
    # Format: 00:00:10.500 or 00:10.500
    parts = time_str.split(':')
    if len(parts) == 3:  # HH:MM:SS.mmm
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    elif len(parts) == 2:  # MM:SS.mmm
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    else:
        return float(parts[0])

def transcribe_audio():
    """Transcribe audio with Azure OpenAI"""
    print("[🧠] Transcribing via GPT-4o Transcribe (Azure)...")
    
    client = AzureOpenAI(
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY")
    )
    deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-transcribe")

    # Check if audio file is too large/long - chunk it if needed
    chunk_duration = 20 * 60  # 20 minutes in seconds (safe limit)
    chunks_dir = os.path.join(DOWNLOAD_DIR, 'audio_chunks')
    os.makedirs(chunks_dir, exist_ok=True)
    
    # Get audio duration
    cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', AUDIO_FILE]
    result = subprocess.run(cmd, capture_output=True, text=True)
    duration = float(result.stdout.strip())
    
    transcripts = []
    
    if duration <= chunk_duration:
        # File is small enough, transcribe directly
        print(f"[🎧] Audio duration: {duration/60:.1f} minutes - transcribing directly")
        with open(AUDIO_FILE, 'rb') as audio_file:
            transcript = client.audio.transcriptions.create(
                model=deployment_name,
                file=audio_file,
                response_format="json"
            )
        transcripts.append(transcript)
    else:
        # File is too long, chunk it
        print(f"[🎧] Audio duration: {duration/60:.1f} minutes - chunking into {chunk_duration/60} minute segments")
        
        chunk_count = int(duration // chunk_duration) + 1
        for i in range(chunk_count):
            start_time = i * chunk_duration
            chunk_file = os.path.join(chunks_dir, f'chunk_{i:03d}.mp3')
            
            # Create chunk with ffmpeg
            cmd = [
                'ffmpeg', '-y', '-i', AUDIO_FILE,
                '-ss', str(start_time),
                '-t', str(chunk_duration),
                '-acodec', 'libmp3lame',
                '-ar', '16000', '-ac', '1',
                chunk_file
            ]
            print(f"[✂️] Creating chunk {i+1}/{chunk_count} ({start_time/60:.1f}-{(start_time+chunk_duration)/60:.1f} min)")
            subprocess.run(cmd, check=True)
            
            # Transcribe chunk
            if os.path.exists(chunk_file):
                with open(chunk_file, 'rb') as audio_file:
                    chunk_transcript = client.audio.transcriptions.create(
                        model=deployment_name,
                        file=audio_file,
                        response_format="json"
                    )
                transcripts.append(chunk_transcript)
                print(f"[✅] Transcribed chunk {i+1}/{chunk_count}")
                
                # Clean up chunk file
                os.remove(chunk_file)
    
    # Process and combine all transcripts
    combined_json = {
        "text": "",
        "segments": []
    }
    
    total_offset = 0
    plain_text_parts = []
    
    for i, transcript_json in enumerate(transcripts):
        # Extract plain text
        plain_text_parts.append(transcript_json.text)
        
        # Create a basic segment for each chunk (no detailed timestamps from GPT-4o-transcribe)
        chunk_duration = 20 * 60  # 20 minutes
        segment = {
            'start': total_offset,
            'end': total_offset + chunk_duration,
            'text': transcript_json.text
        }
        combined_json['segments'].append(segment)
        total_offset += chunk_duration
    
    # Combine plain text
    combined_json['text'] = ' '.join(plain_text_parts)
    
    return combined_json

def main():
    # Test URL (replace with your test URL)
    test_url = input("Enter YouTube URL to test: ").strip()
    
    if not test_url:
        print("No URL provided")
        return
    
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    # Step 1: Try to get existing subtitles
    print("\n=== STEP 1: Checking for existing subtitles ===")
    has_subtitles = get_video_subtitles(test_url, "podcast.mp4")
    
    transcript_data = None
    
    if has_subtitles:
        print("\n=== STEP 2: Converting subtitles to JSON ===")
        transcript_data = parse_vtt_to_json(SUBTITLES_FILE)
        if transcript_data:
            print(f"[✅] Converted subtitles to JSON format")
        else:
            print(f"[❌] Failed to parse subtitles")
            has_subtitles = False
    
    # Step 3: If no subtitles, transcribe audio
    if not has_subtitles:
        print("\n=== STEP 3: No subtitles found, checking for audio file ===")
        if not os.path.exists(AUDIO_FILE):
            print(f"[❌] Audio file not found: {AUDIO_FILE}")
            print("Run the main download script first to get audio file")
            return
            
        print("\n=== STEP 4: Transcribing audio ===")
        transcript_data = transcribe_audio()
    
    # Save results
    if transcript_data:
        print("\n=== SAVING RESULTS ===")
        
        # Save timestamped JSON version
        with open(TRANSCRIPT_JSON_FILE, 'w') as f:
            json.dump(transcript_data, f, indent=2)
        
        # Save plain text version
        with open(TRANSCRIPT_FILE, 'w') as f:
            f.write(transcript_data['text'])

        print(f"[✅] Timestamped transcript saved to {TRANSCRIPT_JSON_FILE}")
        print(f"[✅] Plain text transcript saved to {TRANSCRIPT_FILE}")
        
        # Show first few segments as preview
        if 'segments' in transcript_data and transcript_data['segments']:
            print(f"\n=== PREVIEW (first 3 segments) ===")
            for i, segment in enumerate(transcript_data['segments'][:3]):
                start_min = int(segment['start'] // 60)
                start_sec = int(segment['start'] % 60)
                end_min = int(segment['end'] // 60) 
                end_sec = int(segment['end'] % 60)
                print(f"[{start_min:02d}:{start_sec:02d} - {end_min:02d}:{end_sec:02d}] {segment['text'][:100]}...")

if __name__ == "__main__":
    main() 