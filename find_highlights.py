import os
import json
import glob
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
from openai import AzureOpenAI

# Load environment variables
load_dotenv()

# ====== CONFIG ======
GOOGLE_SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME', 'Shorts Pipeline')
SHEET_TAB_NAME = os.getenv('SHEET_TAB_NAME', 'Sheet1')
CREDENTIALS_FILE = os.getenv('CREDENTIALS_FILE', 'automations-463516-2987a6762cd6.json')
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads')
HIGHLIGHTS_FILE = os.path.join(DOWNLOAD_DIR, 'highlights.json')
# =====================

def get_video_url_from_sheet():
    """Get the video URL from the Google Sheet for the row with captions_downloaded status"""
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        gc = gspread.authorize(creds)
        sheet = gc.open(GOOGLE_SHEET_NAME).worksheet(SHEET_TAB_NAME)
        data = sheet.get_all_records()
        
        # Find row with status "captions_downloaded"
        for row in data:
            if row.get("status", "").lower() == "captions_downloaded":
                video_url = row.get("podcast_url", "").strip()
                if video_url:
                    print(f"[INFO] Found video URL from sheet: {video_url}")
                    return video_url
        
        print("[WARNING] No video URL found in sheet with captions_downloaded status")
        return None
        
    except Exception as e:
        print(f"[ERROR] Error reading from Google Sheet: {e}")
        return None

def parse_vtt_captions():
    """Find and parse VTT caption files"""
    # Look for VTT files in downloads
    vtt_files = glob.glob(os.path.join(DOWNLOAD_DIR, "*.vtt"))
    
    if not vtt_files:
        print("[ERROR] No VTT caption files found")
        return None
        
    vtt_file = vtt_files[0]  # Use first VTT file found
    print(f"[INFO] Parsing captions: {vtt_file}")
    
    segments = []
    current_segment = None
    
    with open(vtt_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip header and empty lines
        if line.startswith('WEBVTT') or line == '' or line.startswith('NOTE') or line.isdigit():
            i += 1
            continue
            
        # Timeline format: 00:00:10.500 --> 00:00:13.000
        if '-->' in line:
            parts = line.split(' --> ')
            if len(parts) == 2:
                start_time = vtt_time_to_seconds(parts[0])
                end_time = vtt_time_to_seconds(parts[1])
                
                # Collect all text lines until next timestamp or end
                text_lines = []
                i += 1
                while i < len(lines) and '-->' not in lines[i].strip() and lines[i].strip() != '':
                    if not lines[i].strip().isdigit():  # Skip sequence numbers
                        clean_text = lines[i].strip()
                        # Remove VTT formatting tags
                        clean_text = clean_text.replace('<c>', '').replace('</c>', '')
                        clean_text = clean_text.replace('<v ', '').replace('>', '')
                        if clean_text:
                            text_lines.append(clean_text)
                    i += 1
                
                if text_lines:
                    segments.append({
                        'start': start_time,
                        'end': end_time,
                        'text': ' '.join(text_lines)
                    })
                continue
        
        i += 1
    
    print(f"[SUCCESS] Parsed {len(segments)} caption segments")
    return segments

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

def find_viral_highlights(segments):
    """Use GPT-4o to find viral highlight moments"""
    print("[AI] Analyzing content with GPT-4o for viral moments...")
    
    # Combine segments into full transcript with timestamps
    full_text = ""
    for segment in segments:
        timestamp = f"[{int(segment['start']//60):02d}:{int(segment['start']%60):02d}]"
        full_text += f"{timestamp} {segment['text']}\n"
    
    # Limit to manageable size for GPT-4o (keep first 8000 chars)
    if len(full_text) > 8000:
        full_text = full_text[:8000] + "\n...[transcript continues]"
    
    client = AzureOpenAI(
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY")
    )
    
    # Improved Hormozi-style viral moment detection prompt
    prompt = f"""
FIND 3 VIRAL 60-SECOND YOUTUBE SHORTS FROM THIS PODCAST TRANSCRIPT.

You need to find 3 different continuous 60-second segments that will go viral on YouTube Shorts.

WHAT MAKES EACH VIRAL:
- Strong emotional hook at the beginning
- Builds tension or curiosity throughout  
- Contains shocking revelations or contrarian takes
- Includes specific numbers, stats, or examples
- Has a satisfying payoff or cliffhanger ending
- Makes people want to share or comment

TRANSCRIPT WITH TIMESTAMPS:
{full_text}

Find the 3 BEST different 60-second segments and return ONLY this JSON:
[
  {{
    "start_time": "MM:SS",
    "end_time": "MM:SS",
    "summary": "Why this will go viral",
    "hook": "Opening line that grabs attention"
  }},
  {{
    "start_time": "MM:SS", 
    "end_time": "MM:SS",
    "summary": "Why this will go viral",
    "hook": "Opening line that grabs attention"
  }},
  {{
    "start_time": "MM:SS",
    "end_time": "MM:SS", 
    "summary": "Why this will go viral",
    "hook": "Opening line that grabs attention"
  }}
]

RULES:
- Each must be 55-65 seconds long
- No overlapping time ranges
- Use exact [MM:SS] timestamps from transcript
- Pick segments with highest viral potential
- Return ONLY the JSON array, nothing else
"""

    try:
        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o"),  # Use chat deployment
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500  # Much smaller since we only need one result
        )
        
        ai_response = response.choices[0].message.content.strip()
        print(f"[AI] GPT-4o found 1-minute viral segment")
        
        # Try to parse JSON from response
        try:
            # Clean up response and find JSON
            if ai_response.startswith('```json'):
                ai_response = ai_response.replace('```json', '').replace('```', '')
            
            # Find JSON object in response
            start_idx = ai_response.find('[')
            end_idx = ai_response.rfind(']') + 1
            
            if start_idx == -1 or end_idx == 0:
                print(f"[ERROR] No JSON found in response:\n{ai_response}")
                return None
                
            json_str = ai_response[start_idx:end_idx]
            highlights = json.loads(json_str)
            
            # Convert to seconds and validate
            segments = []
            for highlight in highlights:
                start_seconds = parse_mmss_to_seconds(highlight['start_time'])
                end_seconds = parse_mmss_to_seconds(highlight['end_time'])
                duration = end_seconds - start_seconds
                
                print(f"[TARGET] Found {duration:.1f}s segment: {highlight['summary']}")
                
                # Validation for 1-minute clips
                if duration < 45 or duration > 75:
                    print(f"[WARNING] Duration {duration}s is not close to 60 seconds")
                    continue
                
                segments.append({
                    'start': start_seconds,
                    'end': end_seconds,
                    'duration': duration,
                    'summary': highlight['summary'],
                    'viral_score': 10  # Single best segment
                })
            
            return segments
            
        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse JSON: {e}")
            print(f"Raw response:\n{ai_response}")
            return None
            
    except Exception as e:
        print(f"[ERROR] Error calling GPT-4o: {e}")
        return None

def parse_mmss_to_seconds(mmss_str):
    """Convert MM:SS to seconds"""
    parts = mmss_str.split(':')
    return int(parts[0]) * 60 + int(parts[1])

def main():
    print("=== VIRAL HIGHLIGHT DETECTION ===\n")
    
    # Step 1: Get video URL from sheet
    video_url = get_video_url_from_sheet()
    if not video_url:
        print("[ERROR] Could not get video URL from sheet")
        return
    
    # Step 2: Parse VTT captions
    segments = parse_vtt_captions()
    if not segments:
        return
    
    total_duration = segments[-1]['end'] if segments else 0
    print(f"[INFO] Total content: {total_duration/60:.1f} minutes")
    
    # Step 3: Find viral highlights with GPT-4o
    highlights = find_viral_highlights(segments)
    
    if not highlights:
        print("[ERROR] No viral highlights found")
        return
    
    # Step 4: Add video URL to highlights data
    highlights_data = {
        'video_url': video_url,
        'highlights': highlights
    }
    
    # Step 5: Save highlights with video URL
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    with open(HIGHLIGHTS_FILE, 'w') as f:
        json.dump(highlights_data, f, indent=2)
    
    print(f"\n[SUCCESS] Found {len(highlights)} viral highlights:")
    print(f"[SAVE] Saved to: {HIGHLIGHTS_FILE}")
    print(f"[VIDEO] Source URL: {video_url}")
    
    # Step 6: Preview highlights
    for i, highlight in enumerate(highlights, 1):
        start_min = int(highlight['start'] // 60)
        start_sec = int(highlight['start'] % 60)
        end_min = int(highlight['end'] // 60) 
        end_sec = int(highlight['end'] % 60)
        
        print(f"\n[TARGET] HIGHLIGHT {i} (Score: {highlight['viral_score']}/10)")
        print(f"[TIME] {start_min:02d}:{start_sec:02d} - {end_min:02d}:{end_sec:02d} ({highlight['duration']:.1f}s)")
        print(f"[SUMMARY] {highlight['summary']}")

if __name__ == "__main__":
    main() 