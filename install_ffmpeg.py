import os
import subprocess
import sys
import zipfile
import shutil
import requests
from pathlib import Path

def download_file(url, filename):
    """Download a file with progress indication"""
    print(f"Downloading {filename}...")
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    
    with open(filename, 'wb') as file, response:
        if total_size == 0:
            file.write(response.content)
        else:
            downloaded = 0
            for data in response.iter_content(chunk_size=8192):
                downloaded += len(data)
                file.write(data)
                done = int(50 * downloaded / total_size)
                sys.stdout.write(f"\r[{'=' * done}{' ' * (50-done)}] {downloaded}/{total_size} bytes")
                sys.stdout.flush()
    print("\nDownload complete!")

def install_ffmpeg():
    """Download and install FFmpeg for Windows"""
    # Create temp directory for downloads
    temp_dir = Path("ffmpeg_temp")
    temp_dir.mkdir(exist_ok=True)
    
    try:
        # Download FFmpeg
        ffmpeg_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        zip_path = temp_dir / "ffmpeg.zip"
        
        print("Step 1: Downloading FFmpeg...")
        download_file(ffmpeg_url, zip_path)
        
        # Extract the zip file
        print("\nStep 2: Extracting FFmpeg...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Find the extracted ffmpeg directory
        ffmpeg_dir = next(temp_dir.glob("ffmpeg-master-*"))
        bin_dir = ffmpeg_dir / "bin"
        
        # Get the user's home directory
        home = Path.home()
        
        # Create FFmpeg directory in user's home
        ffmpeg_install_dir = home / "ffmpeg"
        ffmpeg_install_dir.mkdir(exist_ok=True)
        
        print("Step 3: Installing FFmpeg...")
        # Copy FFmpeg files to install directory
        for file in bin_dir.glob("*"):
            shutil.copy2(file, ffmpeg_install_dir)
        
        # Add to PATH
        print("\nStep 4: Adding FFmpeg to PATH...")
        
        # Get the current PATH
        cmd = ["powershell", "-Command", "[Environment]::GetEnvironmentVariable('Path', 'User')"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        current_path = result.stdout.strip()
        
        # Add FFmpeg to PATH if not already there
        ffmpeg_path = str(ffmpeg_install_dir)
        if ffmpeg_path not in current_path:
            new_path = current_path + ";" + ffmpeg_path if current_path else ffmpeg_path
            cmd = ["powershell", "-Command", f"[Environment]::SetEnvironmentVariable('Path', '{new_path}', 'User')"]
            subprocess.run(cmd, check=True)
            print("FFmpeg added to PATH!")
        else:
            print("FFmpeg already in PATH!")
        
        print("\nStep 5: Verifying installation...")
        # Test FFmpeg
        try:
            subprocess.run([str(ffmpeg_install_dir / "ffmpeg.exe"), "-version"], check=True)
            print("\n✅ FFmpeg installed successfully!")
            print(f"\nFFmpeg is installed in: {ffmpeg_install_dir}")
            print("Please restart your terminal/IDE for PATH changes to take effect.")
        except subprocess.CalledProcessError:
            print("\n❌ FFmpeg installation verification failed.")
            print("Please try running 'ffmpeg -version' in a new terminal window.")
            
    except Exception as e:
        print(f"\n❌ Error during installation: {e}")
    finally:
        # Cleanup
        print("\nCleaning up temporary files...")
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    install_ffmpeg() 