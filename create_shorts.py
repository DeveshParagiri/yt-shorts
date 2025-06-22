import os
import json
import subprocess
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ====== CONFIG ======
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
HIGHLIGHTS_FILE = os.path.join(DOWNLOAD_DIR, 'highlights.json')
PODCAST_VIDEO = os.path.join(DOWNLOAD_DIR, 'podcast.mp4')
BROLL_VIDEO = os.path.join(DOWNLOAD_DIR, 'broll.mp4')
OUTPUT_DIR = os.path.join(DOWNLOAD_DIR, 'shorts')
# =====================

def load_highlights():
    """Load viral highlights from JSON"""
    if not os.path.exists(HIGHLIGHTS_FILE):
        print(f"[❌] No highlights file found: {HIGHLIGHTS_FILE}")
        return None
    
    with open(HIGHLIGHTS_FILE, 'r') as f:
        highlights = json.load(f)
    
    print(f"[📊] Loaded {len(highlights)} viral highlights")
    return highlights

def extract_clip(input_video, start_time, duration, output_file):
    """Extract a clip from video using ffmpeg"""
    cmd = [
        'ffmpeg', '-y',
        '-i', input_video,
        '-ss', str(start_time),
        '-t', str(duration),
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-preset', 'fast',
        output_file
    ]
    
    print(f"[✂️] Extracting {duration}s clip starting at {start_time}s")
    subprocess.run(cmd, check=True)

def create_portrait_layout(podcast_clip, broll_clip, output_file):
    """Create 9:16 portrait layout with podcast on top, broll on bottom"""
    cmd = [
        'ffmpeg', '-y',
        '-i', podcast_clip,
        '-i', broll_clip,
        '-filter_complex', 
        f"""
        [0:v]scale=720:640[podcast];
        [1:v]scale=720:640[broll];
        [podcast][broll]vstack=inputs=2[v];
        [0:a][1:a]amix=inputs=2:duration=shortest[a]
        """,
        '-map', '[v]',
        '-map', '[a]',
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-preset', 'fast',
        '-t', '60',  # Limit to 60 seconds
        output_file
    ]
    
    print(f"[🎬] Creating portrait layout: {output_file}")
    subprocess.run(cmd, check=True)

def add_captions_overlay(input_video, captions_vtt, output_file):
    """Add captions overlay using VTT file"""
    cmd = [
        'ffmpeg', '-y',
        '-i', input_video,
        '-vf', 
        f"""
        subtitles={captions_vtt}:force_style='FontName=Arial Black,FontSize=24,PrimaryColour=&Hffffff&,OutlineColour=&H000000&,Outline=2,Shadow=1,Alignment=2,MarginV=100'
        """,
        '-c:a', 'copy',
        output_file
    ]
    
    print(f"[📝] Adding captions to: {output_file}")
    subprocess.run(cmd, check=True)

def create_short_from_highlight(highlight, index):
    """Create a complete YouTube Short from a highlight"""
    print(f"\n=== CREATING SHORT {index} ===")
    
    start_time = highlight['start']
    duration = highlight['duration']
    
    # File paths
    podcast_clip = os.path.join(OUTPUT_DIR, f'short_{index}_podcast.mp4')
    broll_clip = os.path.join(OUTPUT_DIR, f'short_{index}_broll.mp4')
    layout_video = os.path.join(OUTPUT_DIR, f'short_{index}_layout.mp4')
    final_video = os.path.join(OUTPUT_DIR, f'short_{index}_final.mp4')
    
    try:
        # Step 1: Extract podcast clip
        extract_clip(PODCAST_VIDEO, start_time, duration, podcast_clip)
        
        # Step 2: Extract broll clip (loop if needed)
        extract_clip(BROLL_VIDEO, 0, duration, broll_clip)
        
        # Step 3: Create portrait layout (podcast top, broll bottom)
        create_portrait_layout(podcast_clip, broll_clip, layout_video)
        
        # Step 4: Skip VTT captions - we'll add word-level text overlays separately
        final_video = layout_video  # Use layout video as final for now
        
        print(f"[✅] Created Short {index}: {final_video}")
        
        # Clean up intermediate files
        for temp_file in [podcast_clip, broll_clip, layout_video]:
            if os.path.exists(temp_file) and temp_file != final_video:
                os.remove(temp_file)
        
        return final_video
        
    except subprocess.CalledProcessError as e:
        print(f"[❌] Error creating Short {index}: {e}")
        return None

def main():
    print("=== YOUTUBE SHORTS CREATOR ===\n")
    
    # Load highlights
    highlights = load_highlights()
    if not highlights:
        return
    
    # Check input files
    if not os.path.exists(PODCAST_VIDEO):
        print(f"[❌] Podcast video not found: {PODCAST_VIDEO}")
        return
    
    if not os.path.exists(BROLL_VIDEO):
        print(f"[⚠️] B-roll video not found: {BROLL_VIDEO}")
        print("[ℹ️] Will create Shorts without b-roll overlay")
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Create Shorts for each highlight
    created_shorts = []
    for i, highlight in enumerate(highlights, 1):
        print(f"\n[🎯] Highlight {i}: {highlight['summary'][:60]}...")
        
        short_file = create_short_from_highlight(highlight, i)
        if short_file:
            created_shorts.append(short_file)
    
    print(f"\n[🎉] SUCCESS! Created {len(created_shorts)} YouTube Shorts:")
    for short in created_shorts:
        print(f"   📱 {short}")
    
    print(f"\n[📁] All Shorts saved in: {OUTPUT_DIR}")

if __name__ == "__main__":
    main() 