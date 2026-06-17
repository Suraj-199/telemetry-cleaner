# Telemetry Analytics Platform

This tool is designed to clean, normalize, and analyze raw telemetry data from an Excel or CSV file. It provides an intuitive local web interface to configure metric and network mappings dynamically.

## How to use on Windows

To run this application on a Windows machine, the only requirement is that **Python** is installed.

### Step 1: Install Python (If not already installed)
1. Go to [python.org/downloads](https://www.python.org/downloads/) and download the latest installer for Windows.
2. **IMPORTANT**: When running the installer, you MUST check the box that says **"Add Python to PATH"** at the very bottom of the screen before clicking Install.

### Step 2: Run the App
1. Download or unzip this entire project folder onto your computer.
2. Double-click the **`run_windows.bat`** file.
3. A black command window will appear. The first time you run it, it will automatically download and install the required background libraries (Pandas, Streamlit, etc.). 
4. After a few seconds, it will automatically launch your default web browser and open the Telemetry Analytics App.

### Note for Mac Users
If you are running this on a Mac, you can run the app by opening your terminal in this folder and running:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run src/app.py
```
