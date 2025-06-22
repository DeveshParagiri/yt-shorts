import os
import json
import subprocess
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ====== CONFIG ======
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
HIGHLIGHTS_FILE = os.path.join(DOWNLOAD_DIR, 'highlights.json')
VTT_FILE = os.path.join(DOWNLOAD_DIR, 'podcast.en.vtt')
OUTPUT_DIR = os.path.join(DOWNLOAD_DIR, 'shorts')
# =====================

def parse_vtt_time_to_seconds(time_str):
    """Convert VTT timestamp to seconds"""
    time_str = time_str.replace(',', '.')
    parts = time_str.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    else:
        m, s = parts
        return int(m) * 60 + float(s)

def extract_transcript_for_segment(start_sec, end_sec):
    """Extract transcript text for a specific time segment"""
    with open(VTT_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    segments = []
    lines = content.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if '-->' in line:
            time_line = line
            text_lines = []
            
            j = i + 1
            while j < len(lines) and lines[j].strip() != '':
                text_lines.append(lines[j].strip())
                j += 1
            
            if text_lines:
                try:
                    start_time, end_time = time_line.split(' --> ')
                    seg_start = parse_vtt_time_to_seconds(start_time.strip())
                    seg_end = parse_vtt_time_to_seconds(end_time.strip())
                    
                    if seg_start <= end_sec and seg_end >= start_sec:
                        text = ' '.join(text_lines).replace('&nbsp;', ' ').strip()
                        # Clean up text
                        text = re.sub(r'\s+', ' ', text)
                        segments.append({
                            'start': seg_start,
                            'end': seg_end,
                            'text': text
                        })
                except:
                    pass
            i = j
        else:
            i += 1
    
    return sorted(segments, key=lambda x: x['start'])

def estimate_word_timings(segments, start_offset=0):
    """Estimate word-level timings based on actual speaking rate from segments"""
    word_timings = []
    
    for segment in segments:
        words = segment['text'].split()
        if not words:
            continue
            
        segment_duration = segment['end'] - segment['start']
        if segment_duration <= 0:
            continue
            
        # Calculate actual speaking rate for this segment
        words_per_second = len(words) / segment_duration
        time_per_word = segment_duration / len(words)
        
        # Start time for this segment (adjusted for clip start)
        segment_start_adjusted = segment['start'] - start_offset
        
        for i, word in enumerate(words):
            word_start = segment_start_adjusted + (i * time_per_word)
            word_end = word_start + time_per_word
            
            # Only include words that appear in our clip (after 0 seconds)
            if word_end > 0:
                word_timings.append({
                    'word': word,
                    'start': max(0, word_start),
                    'end': max(0, word_end)
                })
    
    return word_timings

def create_word_groups(word_timings, words_per_group=3):
    """Group words into 2-4 word chunks for display with better timing"""
    groups = []
    
    i = 0
    while i < len(word_timings):
        # Vary group size between 2-4 words for more natural flow
        if i + 4 <= len(word_timings):
            group_size = 3  # Prefer 3 words when possible
        elif i + 3 <= len(word_timings):
            group_size = 3
        elif i + 2 <= len(word_timings):
            group_size = 2
        else:
            group_size = 1
            
        group_words = word_timings[i:i + group_size]
        
        if group_words:
            # Add small buffer between groups for readability
            end_time = group_words[-1]['end'] + 0.1
            
            groups.append({
                'text': ' '.join([w['word'] for w in group_words]),
                'start': group_words[0]['start'],
                'end': end_time
            })
        
        i += group_size
    
    return groups

def create_text_overlay_video(input_video, word_groups, output_video):
    """Create video with burned-in text overlays using ASS subtitle format"""
    
    # Create ASS subtitle file
    ass_file = output_video.replace('.mp4', '.ass')
    
    # ASS file header with better styling for mobile
    ass_content = """[Script Info]
Title: Word-level captions
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,32,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,2,1,2,20,20,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # Add each word group as a subtitle event
    for group in word_groups:
        start_time = f"{int(group['start']//3600):01d}:{int((group['start']%3600)//60):02d}:{group['start']%60:06.3f}"
        end_time = f"{int(group['end']//3600):01d}:{int((group['end']%3600)//60):02d}:{group['end']%60:06.3f}"
        text = group['text'].replace(',', '\\,')  # Escape commas for ASS format
        
        ass_content += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}\n"
    
    # Write ASS file
    with open(ass_file, 'w', encoding='utf-8') as f:
        f.write(ass_content)
    
    # Use ffmpeg with subtitle filter
    cmd = [
        'ffmpeg', '-y',
        '-i', input_video,
        '-vf', f'ass={ass_file}',
        '-c:a', 'copy',
        '-preset', 'fast',
        output_video
    ]
    
    print(f"[📝] Adding word-level text overlays...")
    subprocess.run(cmd, check=True)
    
    # Clean up ASS file
    os.remove(ass_file)

def create_short_with_text(highlight, index):
    """Create a YouTube Short with word-level text overlays"""
    print(f"\n=== CREATING SHORT {index} WITH TEXT ===")
    
    start_time = highlight['start']
    duration = highlight['duration']
    
    # File paths
    layout_video = os.path.join(OUTPUT_DIR, f'short_{index}_layout.mp4')
    final_video = os.path.join(OUTPUT_DIR, f'short_{index}_with_text.mp4')
    
    # Extract transcript for this segment
    segments = extract_transcript_for_segment(start_time, start_time + duration)
    
    if not segments:
        print(f"[⚠️] No transcript found for Short {index}")
        return layout_video
    
    # Estimate word timings
    word_timings = estimate_word_timings(segments, start_time)
    
    # Group words into 3-4 word chunks
    word_groups = create_word_groups(word_timings, words_per_group=3)
    
    print(f"[📊] Found {len(word_groups)} text groups:")
    for group in word_groups[:5]:  # Show first 5 groups
        print(f"   {group['start']:.1f}s-{group['end']:.1f}s: '{group['text']}'")
    
    # Create video with text overlays
    if os.path.exists(layout_video):
        create_text_overlay_video(layout_video, word_groups, final_video)
        print(f"[✅] Created Short {index} with text: {final_video}")
        return final_video
    else:
        print(f"[❌] Layout video not found: {layout_video}")
        return None

def main():
    print("=== WORD-LEVEL CAPTION CREATOR ===\n")
    
    # Load highlights
    if not os.path.exists(HIGHLIGHTS_FILE):
        print(f"[❌] No highlights file found: {HIGHLIGHTS_FILE}")
        return
    
    with open(HIGHLIGHTS_FILE, 'r') as f:
        highlights = json.load(f)
    
    # Check if layout videos exist
    layout_videos = []
    for i in range(1, len(highlights) + 1):
        layout_video = os.path.join(OUTPUT_DIR, f'short_{i}_layout.mp4')
        if os.path.exists(layout_video):
            layout_videos.append(layout_video)
        else:
            print(f"[⚠️] Layout video not found: {layout_video}")
    
    if not layout_videos:
        print("[❌] No layout videos found. Run create_shorts.py first!")
        return
    
    # Create text overlays for each short
    created_shorts = []
    for i, highlight in enumerate(highlights, 1):
        print(f"\n[🎯] Processing Short {i}: {highlight['summary'][:50]}...")
        
        short_file = create_short_with_text(highlight, i)
        if short_file:
            created_shorts.append(short_file)
    
    print(f"\n[🎉] SUCCESS! Created {len(created_shorts)} Shorts with text:")
    for short in created_shorts:
        print(f"   📱 {short}")

if __name__ == "__main__":
    main() 