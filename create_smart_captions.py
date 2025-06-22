import os
import json
import subprocess
import re
from openai import AzureOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ====== CONFIG ======
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
HIGHLIGHTS_FILE = os.path.join(DOWNLOAD_DIR, 'highlights.json')
VTT_FILE = os.path.join(DOWNLOAD_DIR, 'podcast.en.vtt')
OUTPUT_DIR = os.path.join(DOWNLOAD_DIR, 'shorts')

# Azure OpenAI Configuration
client = AzureOpenAI(
    api_key=os.getenv('AZURE_OPENAI_API_KEY'),
    api_version=os.getenv('AZURE_OPENAI_API_VERSION'),
    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT')
)
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

def extract_vtt_segment(start_sec, end_sec):
    """Extract VTT captions for a specific time segment"""
    if not os.path.exists(VTT_FILE):
        return ""
    
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
            
            # Collect text lines after timestamp
            j = i + 1
            while j < len(lines) and lines[j].strip() != '':
                text_line = lines[j].strip()
                if text_line and not text_line.isdigit():
                    text_lines.append(text_line)
                j += 1
            
            if text_lines:
                # Parse time range
                start_time, end_time = time_line.split(' --> ')
                seg_start = parse_vtt_time_to_seconds(start_time.strip())
                seg_end = parse_vtt_time_to_seconds(end_time.strip())
                
                # Check if this segment overlaps with our target range
                if seg_start < end_sec and seg_end > start_sec:
                    segments.append({
                        'start': seg_start,
                        'end': seg_end,
                        'text': ' '.join(text_lines)
                    })
            
            i = j
        else:
            i += 1
    
    # Combine all text from overlapping segments
    full_text = ' '.join([seg['text'] for seg in segments])
    return full_text.strip()

def optimize_captions_with_gpt(raw_text, duration):
    """Use GPT-4o to create optimized captions for YouTube Shorts"""
    
    prompt = f"""
OPTIMIZE THESE CAPTIONS FOR YOUTUBE SHORTS:

Raw transcript: "{raw_text}"
Video duration: {duration} seconds

Create SHORT, PUNCHY captions that will appear on screen 3-4 words at a time.

REQUIREMENTS:
- Break into 2-4 word chunks for mobile readability
- Emphasize KEY WORDS in CAPS (names, shocking facts, numbers)
- Remove filler words (um, uh, like, you know)
- Fix grammar and punctuation
- Make it hook viewers and keep them watching
- Total should be {duration} seconds of captions

Return ONLY a JSON array like this:
[
  {{"text": "JENSEN HUANG is", "duration": 1.2}},
  {{"text": "shaping YOUR future", "duration": 1.5}},
  {{"text": "He's the CEO", "duration": 1.0}},
  {{"text": "of NVIDIA", "duration": 0.8}}
]

Make it VIRAL and ENGAGING for TikTok/YouTube Shorts audience.
"""

    try:
        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o"),  # Use chat deployment
            messages=[
                {"role": "system", "content": "You are an expert at creating viral YouTube Shorts captions. Make text punchy, engaging, and optimized for mobile viewing."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        # Parse JSON response
        response_text = response.choices[0].message.content.strip()
        print(f"[🤖] GPT-4o response: {response_text[:200]}...")
        
        # Try to extract JSON from response (sometimes GPT adds extra text)
        if '[' in response_text and ']' in response_text:
            start = response_text.find('[')
            end = response_text.rfind(']') + 1
            json_text = response_text[start:end]
            caption_data = json.loads(json_text)
            return caption_data
        else:
            print(f"[❌] No JSON array found in response")
            return None
        
    except Exception as e:
        print(f"[❌] GPT-4o optimization failed: {e}")
        return None

def create_timed_captions(optimized_captions):
    """Convert optimized captions to timed groups"""
    groups = []
    current_time = 0
    
    for caption in optimized_captions:
        groups.append({
            'text': caption['text'],
            'start': current_time,
            'end': current_time + caption['duration']
        })
        current_time += caption['duration']
    
    return groups

def create_smart_caption_video(input_video, word_groups, output_video):
    """Create video with GPT-4o optimized captions"""
    
    # Create ASS subtitle file
    ass_file = output_video.replace('.mp4', '.ass')
    
    # Mobile-optimized styling
    ass_content = """[Script Info]
Title: GPT-4o Optimized Captions
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,26,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,2,1,2,20,20,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # Add each caption group
    for group in word_groups:
        start_time = f"{int(group['start']//3600):01d}:{int((group['start']%3600)//60):02d}:{group['start']%60:06.3f}"
        end_time = f"{int(group['end']//3600):01d}:{int((group['end']%3600)//60):02d}:{group['end']%60:06.3f}"
        text = group['text'].replace(',', '\\,')
        
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
    
    print(f"[📝] Adding GPT-4o optimized captions...")
    subprocess.run(cmd, check=True)
    
    # Clean up
    os.remove(ass_file)

def create_smart_captioned_short(highlight, index):
    """Create YouTube Short with GPT-4o optimized captions"""
    print(f"\n=== CREATING SMART-CAPTIONED SHORT {index} ===")
    
    start_time = highlight['start']
    duration = highlight['duration']
    end_time = start_time + duration
    
    # File paths
    layout_video = os.path.join(OUTPUT_DIR, f'short_{index}_layout.mp4')
    final_video = os.path.join(OUTPUT_DIR, f'short_{index}_smart_captions.mp4')
    
    if not os.path.exists(layout_video):
        print(f"[❌] Layout video not found: {layout_video}")
        return None
    
    try:
        # Step 1: Extract raw VTT text for this segment
        print(f"[📝] Extracting VTT text for {start_time}s-{end_time}s...")
        raw_text = extract_vtt_segment(start_time, end_time)
        
        if not raw_text:
            print(f"[❌] No VTT text found for this segment")
            return None
        
        print(f"[📊] Raw text: {raw_text[:100]}...")
        
        # Step 2: Optimize with GPT-4o
        print(f"[🤖] Optimizing captions with GPT-4o...")
        optimized_captions = optimize_captions_with_gpt(raw_text, duration)
        
        if not optimized_captions:
            print(f"[❌] GPT-4o optimization failed")
            return None
        
        # Step 3: Create timed caption groups
        word_groups = create_timed_captions(optimized_captions)
        
        print(f"[📊] GPT-4o created {len(word_groups)} caption groups:")
        for group in word_groups[:5]:  # Show first 5
            print(f"   {group['start']:.1f}s-{group['end']:.1f}s: '{group['text']}'")
        
        # Step 4: Create video with smart captions
        create_smart_caption_video(layout_video, word_groups, final_video)
        
        print(f"[✅] Created smart-captioned Short {index}: {final_video}")
        return final_video
        
    except Exception as e:
        print(f"[❌] Error creating smart captions: {e}")
        return None

def main():
    print("=== GPT-4O SMART CAPTION CREATOR ===\n")
    
    # Load highlights
    if not os.path.exists(HIGHLIGHTS_FILE):
        print(f"[❌] No highlights file found: {HIGHLIGHTS_FILE}")
        return
    
    with open(HIGHLIGHTS_FILE, 'r') as f:
        highlights = json.load(f)
    
    # Create smart-captioned shorts
    created_shorts = []
    for i, highlight in enumerate(highlights, 1):
        print(f"\n[🎯] Processing Short {i}: {highlight['summary'][:50]}...")
        
        short_file = create_smart_captioned_short(highlight, i)
        if short_file:
            created_shorts.append(short_file)
    
    print(f"\n[🎉] SUCCESS! Created {len(created_shorts)} smart-captioned Shorts:")
    for short in created_shorts:
        print(f"   📱 {short}")
    
    print(f"\n[💡] These use GPT-4o to optimize your existing VTT captions!")

if __name__ == "__main__":
    main() 