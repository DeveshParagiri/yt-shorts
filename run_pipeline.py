import os
import sys
import subprocess
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_script(script_name, description):
    """Run a Python script and handle errors"""
    print(f"\n{'='*60}")
    print(f"[STEP] {description}")
    print(f"[RUNNING] {script_name}")
    print(f"{'='*60}")
    
    try:
        # Run the script
        result = subprocess.run([sys.executable, script_name], 
                              capture_output=True, 
                              text=True, 
                              check=True)
        
        print(f"[SUCCESS] {description} completed successfully!")
        if result.stdout:
            print("[OUTPUT]")
            print(result.stdout)
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] {description} failed!")
        print(f"Error code: {e.returncode}")
        if e.stdout:
            print("[OUTPUT]")
            print(e.stdout)
        if e.stderr:
            print("[ERROR]")
            print(e.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error in {description}: {e}")
        return False

def check_dependencies():
    """Check if all required files exist"""
    required_files = [
        'download_captions.py',
        'find_highlights.py', 
        'download_segments.py',
        'create_ai_captions.py'
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print("[ERROR] Missing required files:")
        for file in missing_files:
            print(f"   - {file}")
        return False
    
    print("[SUCCESS] All required files found!")
    return True

def main():
    """Run the complete pipeline"""
    print("[PIPELINE] YOUTUBE SHORTS PIPELINE")
    print("=" * 60)
    print("This will run the complete pipeline:")
    print("1. Download captions from Google Sheet")
    print("2. Find viral highlights using AI")
    print("3. Download highlighted segments")
    print("4. Generate AI captions with word highlighting")
    print("=" * 60)
    
    # Check dependencies
    if not check_dependencies():
        print("\n[ERROR] Pipeline cannot start - missing files!")
        return
    
    # Check environment variables
    required_env_vars = [
        'ASSEMBLYAI_API_KEY',
        'AZURE_OPENAI_API_KEY',
        'AZURE_OPENAI_ENDPOINT',
        'GOOGLE_SHEET_NAME'
    ]
    
    missing_env = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_env.append(var)
    
    if missing_env:
        print("[WARNING] Missing environment variables:")
        for var in missing_env:
            print(f"   - {var}")
        print("Please check your .env file!")
    
    # Pipeline steps
    pipeline_steps = [
        ('download_captions.py', 'Download captions from Google Sheet'),
        ('find_highlights.py', 'Find viral highlights using AI'),
        ('download_segments.py', 'Download highlighted segments'),
        ('create_ai_captions.py', 'Generate AI captions with word highlighting')
    ]
    
    # Run each step
    for script, description in pipeline_steps:
        success = run_script(script, description)
        
        if not success:
            print(f"\n[ERROR] Pipeline failed at: {description}")
            print("Please fix the error and run again.")
            return
        
        # Small delay between steps
        time.sleep(1)
    
    print(f"\n{'='*60}")
    print("[SUCCESS] PIPELINE COMPLETED SUCCESSFULLY!")
    print("[INFO] Check the 'downloads/shorts' directory for your videos")
    print(f"{'='*60}")

if __name__ == '__main__':
    main() 