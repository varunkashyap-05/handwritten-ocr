import os
import re
import tempfile
import asyncio
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ==========================================
# CONFIGURATION
# Set these in your environment variables or paste them here directly.
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Initialize Gemini AI
genai.configure(api_key=GEMINI_API_KEY)

# Use the latest multimodal model
MODEL_NAME = 'gemini-2.5-flash' 

# We lower safety blocks slightly so the bot doesn't refuse to analyze actual news 
# about sensitive/controversial topics, which are often the subjects of fake news.
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

SYSTEM_INSTRUCTION = """You are an expert fact-checker, journalist, and digital forensics analyst.
Analyze the provided content (which could be text, an article, an image, or a video) and determine if it is real, fake news, misleading, or satire.

Provide a response strictly in this format:
🚨 **Verdict:** [Real / Fake / Misleading / Satire / Unverified]

📝 **Explanation:** [Provide a detailed explanation. Point out any manipulated elements, logical fallacies, lack of sources, or known hoaxes.]

🔍 **Context & Facts:** [Provide the actual truth, background context, or correct information regarding the topic.]
"""

# ==========================================
# UTILITY FUNCTIONS
# ==========================================
def extract_text_from_url(url: str) -> str:
    """Scrapes paragraph text from a given URL."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        paragraphs = soup.find_all('p')
        text = ' '.join([p.get_text() for p in paragraphs])
        return text[:15000] # Limit to 15k characters to fit within prompt context
    except Exception as e:
        return f"[Failed to extract webpage content: {e}]"

# ==========================================
# TELEGRAM HANDLERS
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    welcome_message = (
        "👋 Welcome to the **AI Fact-Checker Bot**!\n\n"
        "I can help you identify fake news, deepfakes, and misleading posts. "
        "Here is what you can send me:\n"
        "🔗 **Links:** Send a news article or blog post URL.\n"
        "📝 **Text:** Forward suspicious messages or claims.\n"
        "📸 **Images:** Send photos (with or without captions) to check for manipulation.\n"
        "🎥 **Videos:** Send short video clips to analyze the context.\n\n"
        "Send me something to verify!"
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles plain text and URLs."""
    user_text = update.message.text
    status_msg = await update.message.reply_text("⏳ Analyzing text...")

    # Find all URLs in the message
    urls = re.findall(r'(https?://[^\s]+)', user_text)
    extracted_content = ""

    if urls:
        await status_msg.edit_text(f"🔗 Found {len(urls)} link(s). Extracting webpage content...")
        for url in urls:
            # Run blocking web scraper in a separate thread so the bot doesn't freeze
            content = await asyncio.to_thread(extract_text_from_url, url)
            extracted_content += f"\n\n--- Content from {url} ---\n{content}"

    prompt = f"{SYSTEM_INSTRUCTION}\n\nUser Message/Claim: {user_text}\n{extracted_content}"

    try:
        await status_msg.edit_text("🧠 Fact-checking with Gemini AI...")
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt, safety_settings=SAFETY_SETTINGS)
        
        # Try sending with Markdown, fallback to plain text if formatting is broken
        try:
            await status_msg.edit_text(response.text, parse_mode='Markdown')
        except:
            await status_msg.edit_text(response.text)
            
    except Exception as e:
        await status_msg.edit_text(f"❌ An error occurred during analysis: {e}")

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Photos and Videos."""
    message = update.message
    
    # Identify media type and check size limits
    if message.photo:
        file_obj = await message.photo[-1].get_file()
        media_type = 'photo'
    elif message.video:
        # Telegram Bot API limits standard downloads to 20MB
        if message.video.file_size > 20 * 1024 * 1024:
            await message.reply_text("❌ This video is too large. Telegram bots can only process files up to 20MB.")
            return
        file_obj = await message.video.get_file()
        media_type = 'video'
    else:
        return

    status_msg = await message.reply_text(f"📥 Downloading {media_type}...")

    # Download file to a temporary location
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4" if media_type == 'video' else ".jpg") as temp_file:
        await file_obj.download_to_drive(temp_file.name)
        temp_path = temp_file.name

    try:
        await status_msg.edit_text("☁️ Uploading media to Gemini AI for analysis...")
        gemini_file = genai.upload_file(path=temp_path)

        # Videos require processing time in Gemini's backend
        if media_type == 'video':
            await status_msg.edit_text("⚙️ Processing video frames and audio (this may take a few seconds)...")
            while gemini_file.state.name == 'PROCESSING':
                await asyncio.sleep(3)
                gemini_file = genai.get_file(gemini_file.name)
            
            if gemini_file.state.name == 'FAILED':
                raise Exception("Gemini failed to process the video.")

        await status_msg.edit_text("🧠 Analyzing media content for manipulation and context...")
        
        caption = message.caption or "No caption provided by the user."
        prompt = f"{SYSTEM_INSTRUCTION}\n\nHere is a {media_type} shared by the user. User's caption: '{caption}'. Please analyze the media and caption for authenticity."

        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content([gemini_file, prompt], safety_settings=SAFETY_SETTINGS)

        try:
            await status_msg.edit_text(response.text, parse_mode='Markdown')
        except:
            await status_msg.edit_text(response.text)
            
        # Clean up the uploaded file from Google's servers
        genai.delete_file(gemini_file.name)

    except Exception as e:
        await status_msg.edit_text(f"❌ An error occurred: {e}")
    finally:
        # Always clean up the local temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)

# ==========================================
# MAIN APPLICATION
# ==========================================
def main():
    if TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN" or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
        print("⚠️ ERROR: Please set your TELEGRAM_TOKEN and GEMINI_API_KEY inside the script or via Environment Variables.")
        return

    # Build the bot application
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", start_command))
    
    # Handle normal text and links
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Handle images and videos
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_media))

    print("✅ Fact-Checker Bot is running! Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()
