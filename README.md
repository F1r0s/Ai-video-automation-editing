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

If you are a beginner, follow this guide step-by-step to get everything running on your PC.

---

## 💻 PC Requirements (Specs)

To run this tool **locally** on your PC without lag, here are the recommended specs:

### Minimum Requirements:
*   **Operating System:** Windows 10 or 11 (64-bit)
*   **CPU (Processor):** Intel Core i5 (8th Gen or newer) or AMD Ryzen 5. The faster the CPU, the faster the video renders.
*   **RAM (Memory):** 8 GB minimum (16 GB is highly recommended for smooth video editing).
*   **Disk Space:** At least 10 GB of free space for storing downloaded videos, temporary files, and final renders.
*   **Internet:** A stable broadband connection for downloading source videos and using AI APIs.
*   **GPU (Graphics Card):** Not strictly required, but having an Nvidia or AMD GPU will make video rendering much faster.

---

## 🛠️ Step 1: Install Required Software

Before you download this folder, your computer needs three things installed:

1.  **Python (Version 3.10 to 3.12):**
    *   Go to [python.org/downloads](https://www.python.org/downloads/) and download the Windows installer.
    *   **CRITICAL:** When installing, make sure to check the box that says **"Add python.exe to PATH"** at the very bottom of the first installation screen.

2.  **Git (To download this folder):**
    *   Go to [git-scm.com/downloads](https://git-scm.com/downloads) and install it with default settings.

3.  **FFmpeg (For video rendering):**
    *   Open your command prompt (Press `Win + R`, type `cmd`, hit Enter).
    *   Type this command and hit enter: `winget install ffmpeg`
    *   Close the command prompt when it finishes.

---

## 📥 Step 2: Download the Project

Now let's download the project to your PC.

1.  Open your command prompt (or PowerShell).
2.  Navigate to where you want to save it (e.g., your Documents folder):
    ```bash
    cd Documents
    ```
3.  Clone (download) the repository:
    ```bash
    git clone https://github.com/YOUR_GITHUB_USERNAME/Ai-video-automation-editing.git
    ```
    *(Note: Replace the URL above with the actual link to your Git repository).*
4.  Open the downloaded folder:
    ```bash
    cd "Script of ai video automation"
    ```

---

## ⚙️ Step 3: Setup & Install Dependencies

1.  Inside the project folder, double-click the **`build_exe.bat`** file (or open terminal and run `pip install -r requirements.txt`). This will install all the necessary Python libraries like MoviePy, yt-dlp, and AI tools.
2.  **Install Playwright Browsers:**
    Open a terminal inside the folder and run:
    ```bash
    playwright install chromium
    ```

---

## 🔑 Step 4: Add Your Secret API Keys

The AI needs API keys to speak and write scripts. 

1.  Find the file named **`.env.example`** in the folder.
2.  Copy it and rename the copy to exactly **`.env`** (make sure it's not `.env.txt`).
3.  Open `.env` in Notepad and fill in your keys:
    *   **ELEVENLABS_API_KEY**: Get this from [ElevenLabs](https://elevenlabs.io/) (for the voiceover).
    *   **GROQ_API_KEY**: Get this from [Groq Cloud](https://console.groq.com/) (for Llama 3 scripts and Whisper captions).
    *   **YOUTUBE / TIKTOK KEYS**: Fill these out if you plan to use the auto-uploader feature.

---

## 🚀 Step 5: Run the App!

You are ready to go!

To start the program, simply double-click the **`Start_App.bat`** file in the folder. 

This will open the visual **AI Video Automation Studio** where you can type in your game name, set your website link, customize your subtitles, and hit **GENERATE**!

### Troubleshooting
*   **"ffmpeg is not recognized"**: You forgot to install FFmpeg or restart your PC after installing it.
*   **"No module named X"**: Make sure you installed the requirements via `pip install -r requirements.txt`.
*   **Cloud Rendering Failed**: If you are using the cloud toggle, ensure `CLOUD_API_URL` in your `.env` file points to your active Hugging Face Space URL.
