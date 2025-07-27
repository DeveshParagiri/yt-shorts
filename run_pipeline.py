import os
import subprocess
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

scripts = [
    "download_captions.py",
    "find_highlights.py",
    "download_segments.py",
    "create_ai_captions.py"
]

venv_python = os.path.join("env", "Scripts", "python.exe")
def run_script(script):
    if not os.path.exists(script):
        logging.error(f"File not found: {script}")
        sys.exit(1)

    if not os.path.exists(venv_python):
        logging.error("Virtual environment not found at 'env/Scripts/python.exe'")
        sys.exit(1)

    logging.info(f"Running {script} using {venv_python}...")
    result = subprocess.run([venv_python, script])
    if result.returncode != 0:
        logging.error(f"{script} exited with code {result.returncode}")
        sys.exit(result.returncode)
    logging.info(f"Completed: {script}")

if __name__ == "__main__":
    for script in scripts:
        run_script(script)

    logging.info("All scripts completed successfully.")
