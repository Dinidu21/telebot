import logging
import os
import re
from dotenv import load_dotenv
import pandas as pd
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import asyncio
import httpx

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Constants for paths
CURRENT_DIR = "D:/Tools/TeleBot"
COOKIES_FILE_PATH = 'cookies.txt'

# Function to log user activity
def log_user_activity(username, youtube_link, success=True):
    """
    Logs user activity to a CSV file.

    Args:
        username (str): The username of the user.
        youtube_link (str): The YouTube link provided by the user.
        success (bool): Whether the download was successful or not.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status = 'Success' if success else 'Failure'
    data = {
        'Username': [username],
        'YouTube Link': [youtube_link],
        'Timestamp': [timestamp],
        'Status': [status]
    }
    log_csv_path = os.path.join(CURRENT_DIR, "downloads_log.csv")

    try:
        df = pd.DataFrame(data)
        df.to_csv(log_csv_path, mode='a', index=False, header=not os.path.exists(log_csv_path))
        logging.info("User activity logged successfully.")
    except Exception as e:
        logging.error(f"Error writing to log file: {e}")

# Function to download audio
async def download_audio(youtube_url, update):
    """
    Downloads the audio from the specified YouTube URL.

    Args:
        youtube_url (str): The URL of the YouTube video.
        update (Update): The update object containing the message.

    Returns:
        str: The path to the downloaded audio file.
    """
    temp_audio_file_path = os.path.join(CURRENT_DIR, "audio_temp.m4a")
    final_audio_file_path = os.path.join(CURRENT_DIR, "audio.mp3")

    async def progress_hook(d):
        await update_progress(d, update)

    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/best',
        'extractaudio': True,
        'audioformat': 'mp3',
        'outtmpl': temp_audio_file_path,
        'noplaylist': True,
        'cookiefile': COOKIES_FILE_PATH,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
        'progress_hooks': [progress_hook],
        'keepvideo': True  # Keep the original file
    }

    logging.info(f"Starting download for: {youtube_url}")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            await update.message.reply_text("Download started. Please wait...")
            ydl.download([youtube_url])
            logging.info("Audio download complete.")

        if os.path.exists(temp_audio_file_path):
            if os.path.exists(final_audio_file_path):
                os.remove(final_audio_file_path)
            os.rename(temp_audio_file_path, final_audio_file_path)
            logging.info(f"Renamed temporary file to {final_audio_file_path}.")
            return final_audio_file_path
        else:
            logging.error("Temporary audio file not found.")
            return None
    except Exception as e:
        logging.error(f"An error occurred during download: {str(e)}")
        await update.message.reply_text("Error: Unable to download the audio.")
        return None

async def update_progress(d, update):
    """
    Updates the progress of the download.

    Args:
        d (dict): The download progress dictionary.
        update (Update): The update object containing the message.
    """
    if d['status'] == 'downloading':
        percent = d['downloaded_bytes'] / d['total_bytes'] * 100
        await update.message.reply_text(f"Download progress: {percent:.2f}%")

# Function to handle incoming messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles incoming messages from users.

    Args:
        update (Update): The update object containing the message.
        context (ContextTypes.DEFAULT_TYPE): The context object.
    """
    youtube_link = update.message.text
    username = update.message.from_user.username or update .message.from_user.first_name

    # Validate YouTube link
    if not re.match(r'^(https?:\/\/)?(www\.youtube\.com|youtu\.?be)\/.+$', youtube_link):
        await update.message.reply_text("Error: Please send a valid YouTube link.")
        return

    # Download audio
    audio_file_path = await download_audio(youtube_link, update)
    if audio_file_path:
        await update.message.reply_text("Download complete. Sending audio file...")
        await context.bot.send_audio(chat_id=update.effective_chat.id, audio=open(audio_file_path, 'rb'))
        log_user_activity(username, youtube_link)
    else:
        log_user_activity(username, youtube_link, success=False)

# Main function
def main():
    # Load environment variables
    load_dotenv()

    # Create the application
    application = ApplicationBuilder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()

    # Add handlers
    application.add_handler(CommandHandler('start', lambda update, context: update.message.reply_text("Welcome! Send a YouTube link to download the audio.")))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the application
    application.run_polling()

if __name__ == "__main__":
    main()