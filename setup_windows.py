#!/usr/bin/env python3
"""
Windows setup script for yt-shorts pipeline
This script will help you install and configure the required dependencies on Windows
"""

import subprocess
import sys
import os
import platform
import shutil

def run_command(cmd, description=""):
    """Run a command and return success status"""
    print(f"\n{'='*50}")
    print(f"Running: {description or ' '.join(cmd)}")
    print(f"{'='*50}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, shell=True)
        print(f"✅ SUCCESS: {description}")
        if result.stdout:
            print(f"Output: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ FAILED: {description}")
        print(f"Error: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")
        return False

def check_python():
    """Check Python version"""
    version = sys.version_info
    print(f"Python version: {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8+ is required")
        return False
    
    print("✅ Python version is compatible")
    return True

def check_pip():
    """Check if pip is available"""
    try:
        import pip
        print("✅ pip is available")
        return True
    except ImportError:
        print("❌ pip is not available")
        return False

def install_dependencies():
    """Install Python dependencies"""
    print("\n🔧 Installing Python dependencies...")
    
    # Upgrade pip first
    if not run_command([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], 
                      "Upgrading pip"):
        return False
    
    # Install requirements
    if os.path.exists("requirements.txt"):
        if not run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                          "Installing requirements from requirements.txt"):
            return False
    else:
        # Install individual packages
        packages = [
            "yt-dlp>=2023.11.16",
            "gspread>=5.12.4", 
            "oauth2client>=4.1.3",
            "python-dotenv>=1.0.0",
            "pycryptodomex>=3.19.0"
        ]
        
        for package in packages:
            if not run_command([sys.executable, "-m", "pip", "install", package], 
                              f"Installing {package}"):
                return False
    
    return True

def check_yt_dlp():
    """Check if yt-dlp is working"""
    print("\n🔧 Checking yt-dlp installation...")
    
    # Check if yt-dlp is in PATH
    yt_dlp_path = shutil.which('yt-dlp')
    if yt_dlp_path:
        print(f"✅ Found yt-dlp at: {yt_dlp_path}")
    else:
        print("⚠️ yt-dlp not found in PATH, trying Python module...")
    
    # Test yt-dlp functionality
    try:
        # Try command line version first
        if yt_dlp_path:
            result = subprocess.run([yt_dlp_path, '--version'], 
                                  capture_output=True, text=True, timeout=30, shell=True)
        else:
            # Try Python module version
            result = subprocess.run([sys.executable, '-m', 'yt_dlp', '--version'], 
                                  capture_output=True, text=True, timeout=30, shell=True)
        
        if result.returncode == 0:
            print(f"✅ yt-dlp version: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ yt-dlp test failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing yt-dlp: {e}")
        return False

def check_ffmpeg():
    """Check if FFmpeg is available (optional but recommended)"""
    print("\n🔧 Checking FFmpeg (optional)...")
    
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        print(f"✅ Found FFmpeg at: {ffmpeg_path}")
        return True
    else:
        print("⚠️ FFmpeg not found in PATH")
        print("FFmpeg is optional but recommended for better video processing")
        print("You can install it from: https://ffmpeg.org/download.html")
        return False

def create_env_file():
    """Create a sample .env file if it doesn't exist"""
    if not os.path.exists('.env'):
        print("\n🔧 Creating sample .env file...")
        env_content = """# Google Sheets Configuration
GOOGLE_SHEET_NAME=Shorts Pipeline
SHEET_TAB_NAME=Sheet1
CREDENTIALS_FILE=automations-463516-2987a6762cd6.json

# Download Configuration  
DOWNLOAD_DIR=downloads
"""
        try:
            with open('.env', 'w') as f:
                f.write(env_content)
            print("✅ Created .env file with sample configuration")
            print("🔧 Please edit .env file with your actual values")
        except Exception as e:
            print(f"❌ Failed to create .env file: {e}")
            return False
    else:
        print("✅ .env file already exists")
    
    return True

def main():
    """Main setup function"""
    print("🚀 Windows Setup for yt-shorts Pipeline")
    print(f"Running on: {platform.system()} {platform.release()}")
    print(f"Architecture: {platform.machine()}")
    
    success = True
    
    # Check Python
    if not check_python():
        success = False
    
    # Check pip
    if not check_pip():
        success = False
    
    if not success:
        print("\n❌ Basic requirements not met. Please install Python 3.8+ with pip")
        return False
    
    # Install dependencies
    if not install_dependencies():
        print("\n❌ Failed to install dependencies")
        return False
    
    # Check yt-dlp
    if not check_yt_dlp():
        print("\n❌ yt-dlp is not working properly")
        return False
    
    # Check FFmpeg (optional)
    check_ffmpeg()
    
    # Create .env file
    create_env_file()
    
    print("\n" + "="*60)
    print("🎉 SETUP COMPLETE!")
    print("="*60)
    print("Next steps:")
    print("1. Edit the .env file with your Google Sheets credentials")
    print("2. Make sure you have the Google service account JSON file")
    print("3. Run: python download_from_sheet.py")
    print("="*60)
    
    return True

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ Setup interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        print("Please check your Python installation and try again") 