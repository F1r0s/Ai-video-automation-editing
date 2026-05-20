# 🚀 Deploying to Hugging Face Spaces

This guide walks you through deploying the video rendering backend to Hugging Face Spaces using the Docker SDK.

---

## 🛠️ Step 1: Create a Space on Hugging Face

1. Log in to [Hugging Face](https://huggingface.co/). If you don't have an account, create one.
2. Go to **Spaces** and click **Create new Space**.
3. Fill out the creation form:
   - **Space Name:** Choose a name (e.g., `ai-video-automation-rendering`).
   - **License:** Select your preference (e.g., `mit`).
   - **Select the Space SDK:** Click **Docker**.
   - **Docker Template:** Choose **Blank** (our `Dockerfile` is already configured).
   - **Space Hardware:** The free CPU basic tier works, but for faster heavy rendering, a GPU tier is recommended.
   - **Visibility:** Public or Private.
     - *Note:* If public, anyone can view the space, but we have built-in API security to prevent unauthorized rendering.
4. Click **Create Space**.

---

## 🔑 Step 2: Configure Space Secrets (Environment Variables)

Hugging Face Spaces hide your API keys securely. You need to configure them in the Space settings:

1. In your newly created Space page, click on the **Settings** tab.
2. Scroll down to the **Variables and secrets** section.
3. Click **New secret** for each of the following keys:
   - `ELEVENLABS_API_KEY`: *(Your ElevenLabs API key)*
   - `ELEVENLABS_VOICE_ID`: *(Voice ID to use by default, e.g., `pNInz6obpgDQGcFmaJgB`)*
   - `GROQ_API_KEY`: *(Your Groq Cloud API key)*
   - `OPENAI_API_KEY`: *(Your OpenAI API key - optional fallback)*
   - `TELEGRAM_BOT_TOKEN`: *(Your Telegram Bot token)*
   - `TELEGRAM_CHAT_ID`: *(Your Telegram Chat/Group ID)*
   - `COOKIES_TXT_CONTENT`: *(Optional: The raw text content of your `cookies.txt` to bypass YouTube scraper blocks)*
   - `API_SECRET_KEY`: *(Optional but highly recommended: Choose a custom password to prevent anyone else from calling your renderer. Example: `MySuperSecretPassword123`)*

---

## 📤 Step 3: Deploy the Code

You can deploy the code directly using Git:

1. In your local terminal, navigate to your project folder:
   ```bash
   cd c:\Users\PC\Documents\Ai-video-automation-editing
   ```
2. Add your Hugging Face Space repository as a Git remote:
   ```bash
   git remote add hf https://huggingface.co/spaces/YOUR_HF_USERNAME/YOUR_SPACE_NAME
   ```
   *(Replace `YOUR_HF_USERNAME` and `YOUR_SPACE_NAME` with your actual Hugging Face details)*
3. Push your files to Hugging Face:
   ```bash
   git push -f hf main
   ```
   *Note: If prompted for credentials, use your Hugging Face username and your **User Access Token** (created in Hugging Face settings -> Access Tokens) as the password.*

4. Hugging Face will automatically detect the `Dockerfile`, build the container, and run it. The deployment status will change to **Running** when it is ready.

---

## ⚙️ Step 4: Configure Your Local Desktop App

Once your Space is running, link your local desktop client to use it:

1. Open your local `.env` file in a text editor.
2. Set `CLOUD_API_URL` to your Hugging Face Space URL:
   ```env
   CLOUD_API_URL=https://YOUR_HF_USERNAME-YOUR_SPACE_NAME.hf.space
   ```
   *(Note: Hugging Face space URLs follow the `https://username-spacename.hf.space` pattern. Make sure there is no `/` at the end)*
3. If you configured `API_SECRET_KEY` on Hugging Face in Step 2, set the matching value locally in your `.env`:
   ```env
   CLOUD_API_SECRET_KEY=MySuperSecretPassword123
   ```
4. Save the `.env` file.

Now, when you run `Start_App.bat` and select **Rendering in the Cloud**, the desktop app will securely send rendering requests to your Hugging Face Space!

---

## 📱 Local Scrape to Cloud CLI Bridge

If you use the command-line bridge script `local_scrape_to_cloud.py`, you can run it like this:

```bash
python local_scrape_to_cloud.py "One State RP" --landing-url "https://example.com" --api-secret "MySuperSecretPassword123"
```
It will read `CLOUD_API_URL` automatically from your local `.env` and authenticate securely.
