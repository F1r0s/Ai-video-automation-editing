import os
import requests
from dotenv import load_dotenv

def test_telegram():
    # Load variables from .env
    load_dotenv()

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    print(f"Testing Telegram...")
    print(f"Bot Token found: {'Yes' if bot_token else 'No'}")
    print(f"Chat ID found: {'Yes' if chat_id else 'No'}")

    if not bot_token or not chat_id:
        print("❌ Error: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing from your .env file.")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "✅ Hello! This is a test message from your AI Video Automation app. Your Telegram connection is working perfectly!"
    }
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("\n✅ Success! Check your Telegram app. You should have just received a test message!")
        else:
            print(f"\n❌ Failed to send message. Telegram said: {r.text}")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")

if __name__ == "__main__":
    test_telegram()
