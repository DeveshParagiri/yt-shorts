# YouTube Shorts Pipeline 🎬

Automatically create viral YouTube Shorts from YouTube videos using AI-powered highlight detection and dynamic word-level captions.

## What This Does 📋

This project takes a podcast episode and automatically:
1. **Downloads captions** from the video
2. **Finds viral moments** using AI (GPT-4o)
3. **Downloads 60-second segments** of the best moments
4. **Creates dynamic captions** with word-level highlighting

The result? Ready-to-upload YouTube Shorts with professional captions that highlight each word as it's spoken!

## Features ✨

- 🤖 **AI-Powered Highlight Detection**: Uses GPT-4o to find the most viral 60-second segments
- 🎯 **Dynamic Word Highlighting**: Each word lights up in blue as it's spoken
- 📊 **Google Sheets Integration**: Manage your pipeline through a spreadsheet
- 🔄 **Automated Pipeline**: Run everything with one command
- 📱 **YouTube Shorts Optimized**: Perfect 9:16 aspect ratio and timing

## Quick Start 🚀

### Prerequisites
- Python 3.8+
- FFmpeg installed
- YouTube-DL installed

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/DeveshParagiri/yt-shorts.git
   cd yt-shorts
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   Create a `.env` file with:
   ```env
   ASSEMBLYAI_API_KEY=your_assemblyai_key
   AZURE_OPENAI_API_KEY=your_azure_openai_key
   AZURE_OPENAI_ENDPOINT=your_azure_endpoint
   GOOGLE_SHEET_NAME=your_sheet_name
   GOOGLE_SHEET_TAB_NAME=Sheet1
   CREDENTIALS_FILE=your_google_credentials.json
   ```

4. **Set up Google Sheets**
   - Create a Google Sheet with columns: `podcast_url`, `status`
   - Add your Google service account credentials file
   - Update the sheet name in your `.env` file

### Usage

1. **Add a podcast URL to your Google Sheet**
   - Set status to "pending"
   - Add the YouTube/podcast URL

2. **Run the pipeline**
   ```bash
   python run_pipeline.py
   ```

3. **Find your videos**
   - Check the `downloads/shorts/` folder
   - Each video has dynamic captions ready for YouTube Shorts

## How It Works 🔧

### Step 1: Download Captions
- Extracts English captions from the video
- Converts to VTT format for processing

### Step 2: Find Viral Highlights
- Uses GPT-4o to analyze the transcript
- Identifies 3 best 60-second segments
- Looks for emotional hooks, shocking revelations, and shareable content

### Step 3: Download Segments
- Downloads each 60-second segment
- Ensures same video source as captions
- Creates MP4 files ready for editing

### Step 4: Generate Dynamic Captions
- Creates ASS subtitle files
- Highlights each word in red as it's spoken
- Uses blue/green for different word groups
- Perfect timing for YouTube Shorts

## File Structure 📁

```
yt-shorts/
├── run_pipeline.py          # Main orchestrator script
├── download_captions.py     # Downloads captions from videos
├── find_highlights.py       # AI-powered viral moment detection
├── download_segments.py     # Downloads video segments
├── create_ai_captions.py    # Creates dynamic word-level captions
├── requirements.txt         # Python dependencies
├── .env                    # Environment variables (create this)
├── downloads/              # Output folder
│   ├── shorts/            # Final videos with captions
│   └── highlights.json    # AI-detected viral moments
└── README.md              # This file
```

## Configuration ⚙️

### Environment Variables
- `ASSEMBLYAI_API_KEY`: For AssemblyAI transcription
- `AZURE_OPENAI_API_KEY`: For GPT-4o AI analysis
- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint
- `GOOGLE_SHEET_NAME`: Your Google Sheet name
- `GOOGLE_SHEET_TAB_NAME`: Sheet tab name (default: Sheet1)
- `CREDENTIALS_FILE`: Google service account JSON file

### Google Sheets Setup
Your sheet should have these columns:
- `podcast_url`: The YouTube/podcast URL
- `status`: Pipeline status (pending → captions_downloaded → segments_downloaded)

## Output 🎯

After running the pipeline, you'll get:
- **3 MP4 files** (60-second segments)
- **ASS subtitle files** with dynamic word highlighting
- **Ready-to-upload** YouTube Shorts content

## Troubleshooting 🔧

### Common Issues

**"yt-dlp not found"**
```bash
pip install yt-dlp
```

**"FFmpeg not found"**
- Windows: Download from https://ffmpeg.org/
- Mac: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

**"Google Sheets error"**
- Check your service account credentials
- Ensure the sheet name matches your `.env` file
- Verify the sheet has the required columns

**"No captions found"**
- The video might not have English captions
- Try a different video with manual captions

## Contributing 🤝

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test the pipeline
5. Submit a pull request

## License 📄

This project is licensed under the MIT License - see the LICENSE file for details.

## Support 💬

If you encounter issues:
1. Check the troubleshooting section above
2. Look at the console output for error messages
3. Ensure all environment variables are set correctly
4. Verify your Google Sheets setup

---
