---
title: Ai Video Automation
emoji: 🎥
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# 🤖 AI Video Automation Studio

Welcome to the AI Video Automation Studio! This tool automatically generates high-retention vertical promo videos (for YouTube Shorts, TikTok, Instagram Reels) using AI voiceovers, captions, and automated overlays.

If you are a beginner (or a friend downloading this!), just follow this simple guide step-by-step to get everything running on your PC.

---

## 💻 PC Requirements

To run this tool **locally** on your PC without lag, here are the recommended specs:

*   **Operating System:** Windows 10 or 11 (64-bit)
*   **CPU:** Intel Core i5 (8th Gen or newer) or AMD Ryzen 5. 
*   **RAM:** 8 GB minimum (16 GB is highly recommended).
*   **Disk Space:** At least 10 GB of free space.
*   **Internet:** A stable broadband connection for downloading source videos.

---

## 🛠️ Step 1: Install Required Software

Before you download this app, your computer needs three basic tools installed:

1.  **Python (Version 3.10 to 3.12):**
    *   Go to [python.org/downloads](https://www.python.org/downloads/) and download the Windows installer.
    *   🚨 **CRITICAL:** When installing, make sure to check the box that says **"Add python.exe to PATH"** at the very bottom of the first installation screen.

2.  **Git (To download this folder):**
    *   Go to [git-scm.com/downloads](https://git-scm.com/downloads) and install it with default settings.

3.  **FFmpeg (For video rendering):**
    *   Open your command prompt (Press `Win + R`, type `cmd`, hit Enter).
    *   Type exactly this and hit enter: `winget install ffmpeg`
    *   Close the command prompt when it finishes.

---

## 📥 Step 2: Download the Project

Now let's download the actual app to your PC.

1.  Open your command prompt (or PowerShell).
2.  Navigate to your Documents folder:
    ```bash
    cd Documents
    ```
3.  Download the project:
    ```bash
    git clone https://github.com/F1r0s/Ai-video-automation-editing.git
    ```
4.  Open the downloaded folder:
    ```bash
    cd "Ai-video-automation-editing"
    ```

---

## ⚙️ Step 3: Install Dependencies

1.  Inside the project folder, open a terminal and run this command to install the required Python libraries:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Install Playwright (for scraping):**
    In the exact same terminal, run:
    ```bash
    playwright install chromium
    ```

---

## 🔑 Step 4: Add Your Secret API Keys

The AI needs API keys to speak and write scripts. 

1.  Find the file named **`.env.example`** in the folder.
2.  Copy it and rename the copy to exactly **`.env`** (make sure it's not `.env.txt`).
3.  Open `.env` in Notepad and fill in your keys:
    *   **ELEVENLABS_API_KEY**: Get this from [ElevenLabs](https://elevenlabs.io/) (for the AI voice).
    *   **GROQ_API_KEY**: Get this from [Groq Cloud](https://console.groq.com/) (for AI scripts and captions).

---

## 🚀 Step 5: Run the App!

You are completely ready to go!

To start the program, simply double-click the **`Start_App.bat`** file in the folder. 

This will open the visual **AI Video Automation Studio** window on your desktop. Simply type in your game name, set your website link, customize your subtitles, and hit **GENERATE**!

---

### Troubleshooting
*   **"ffmpeg is not recognized"**: You forgot to install FFmpeg in Step 1, or you didn't restart your PC after installing it.
*   **"No module named X"**: Make sure you installed the requirements via `pip install -r requirements.txt`.
*   **Connection/Timeout Error**: If you have "Render in Cloud" checked, make sure your `.env` file contains the correct `CLOUD_API_URL` of your remote server. If you don't have a cloud server, just uncheck "Render in Cloud" and it will use your local PC!

---

## Local Scrape to Cloud Mode

If you want scraping to use the device that runs the app, use the local bridge script. It downloads the source video on that machine, then sends the file to Oracle Cloud for rendering.

```bash
python local_scrape_to_cloud.py "One State RP" --landing-url "https://example.com" --backend-url "https://your-oracle-host:5000"
```

You can also set `CLOUD_API_URL` in your `.env` file and omit `--backend-url`.
