from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import re
import asyncio
import logging
import os
import aiofiles
from datetime import datetime
from telegram import Update

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Constants for paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE_PATH = os.path.join(CURRENT_DIR, 'cookies.txt')


def validate_url(url: str) -> bool:
    """Validate YouTube URL."""
    youtube_regex = (
        r'^(https?:\/\/)?(www\.)?'
        r'(youtube|youtu|youtube-nocookie)\.(com|be)\/'
        r'(watch\?v=|embed\/|v\/|.+\?v=)?([^&=%\?]{11})'
        r'(&.*)?$'
    )
    clean_url = url.split('?')[0]  # Strip query parameters
    return re.fullmatch(youtube_regex, clean_url) is not None


async def log_user_activity(username: str, youtube_link: str, success: bool = True):
    """Logs user activity to a CSV file."""
    if not (username and youtube_link):
        logging.error("Invalid parameters for logging user activity.")
        return

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status = 'Success' if success else 'Failure'
    log_csv_path = os.path.join(CURRENT_DIR, "downloads_log.csv")
    header = "Username,YouTube Link,Timestamp,Status\n"
    row = f"{username},{youtube_link},{timestamp},{status}\n"

    try:
        async with aiofiles.open(log_csv_path, mode='a') as f:
            if not os.path.exists(log_csv_path):
                await f.write(header)
            await f.write(row)
        logging.info(f"User activity logged. Username: {username}, Link: {youtube_link}, Status: {status}")
    except Exception as e:
        logging.error(f"Error writing to log file: {e}")


async def update_progress(d: dict, update: Update):
    """Updates the progress of the download."""
    if not isinstance(d, dict) or 'status' not in d:
        logging.error("Invalid progress data received.")
        return

    if d['status'] == 'downloading' and d.get('total_bytes'):
        downloaded_bytes = d.get('downloaded_bytes', 0)
        total_bytes = d.get('total_bytes')

        if total_bytes == 0:
            logging.error("Total bytes is zero, cannot calculate progress.")
            return

        percent = downloaded_bytes / total_bytes * 100
        logging.info(f"Download progress: {percent:.2f}%")

        if update.message:
            try:
                await update.message.reply_text(f"Download progress: {percent:.2f}%")
            except Exception as e:
                logging.error(f"Error sending progress message: {str(e)}")


async def download_audio(youtube_url: str, update: Update, cookies_file_path: str) -> str:
    """Downloads the audio from the specified YouTube URL."""

    final_audio_file_path = os.path.join(CURRENT_DIR, f"downloaded_audio_{int(asyncio.get_event_loop().time())}")

    async def progress_hook(d):
        await update_progress(d, update)

    if not validate_url(youtube_url):
        if update.message:
            await update.message.reply_text("Error: Invalid YouTube URL.")
        return None

    ydl_opts = {
        'format': 'bestaudio/best',
        'extractaudio': True,
        'audioformat': 'mp3',
        'outtmpl': final_audio_file_path,
        'noplaylist': True,
        'cookiefile': cookies_file_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
        'progress_hooks': [progress_hook],
    }

    logging.info(f"Starting download for: {youtube_url}")

    try:
        if update.message:
            await update.message.reply_text("Download started. Please wait...")

        await asyncio.to_thread(lambda: yt_dlp.YoutubeDL(ydl_opts).download([youtube_url]))

        final_audio_file_path += '.mp3'

        if os.path.exists(final_audio_file_path):
            logging.info(f"Audio downloaded successfully to: {final_audio_file_path}")
            return final_audio_file_path
        else:
            logging.error("Audio file not found after download.")
            if update.message:
                await update.message.reply_text("Error: Audio file not found after download.")
            return None

    except Exception as e:
        logging.error(f"An error occurred during download: {str(e)}")
        if update.message:
            await update.message.reply_text("Error: Unable to download the audio.")
        return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming messages from users."""

    try:
        youtube_link = update.message.text.strip()
        username = update.message.from_user.username or update.message.from_user.first_name

        if not validate_url(youtube_link):
            await update.message.reply_text("Error: Please send a valid YouTube link.")
            await log_user_activity(username, youtube_link, success=False)
            return

        audio_file_path = await download_audio(youtube_link, update, COOKIES_FILE_PATH)

        if audio_file_path and os.path.isfile(audio_file_path):
            await update.message.reply_text("Download complete. Sending audio file...")

            try:
                async with aiofiles.open(audio_file_path, 'rb') as audio_file:
                    # Retry sending audio in case of timeout
                    for attempt in range(3):  # Retry up to 3 times
                        try:
                            await context.bot.send_audio(
                                chat_id=update.effective_chat.id,
                                audio=await audio_file.read(),
                                filename=os.path.basename(audio_file_path)
                            )
                            break  # Break on successful send
                        except Exception as e:
                            logging.error(f"Attempt {attempt + 1} failed to send audio file: {str(e)}")
                            if attempt == 2:  # Last attempt failed
                                await update.message.reply_text(
                                    "Error: Failed to send the audio file. Please try again later.")

                await log_user_activity(username, youtube_link)

            except Exception as e:
                logging.error(f"Error opening audio file for sending: {str(e)}")
                await update.message.reply_text("Error: Failed to send the audio file. Please try again later.")

        else:
            await update.message.reply_text(
                "Error: Failed to download the audio. The video might be unavailable or restricted."
            )
            await log_user_activity(username, youtube_link, success=False)

    except Exception as e:
        logging.error(f"An unexpected error occurred: {str(e)}")
        await update.message.reply_text("Error: An unexpected error occurred. Please try again later.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""

    try:
        username = update.message.from_user.username or update.message.from_user.first_name
        logging.info(f"/start command initiated by {username}")

        welcome_message = (
            "🎉 Welcome to the Audio Downloader Bot! 🎶\n"
            "Simply send me a YouTube link, and I'll help you download the audio in no time!\n\n"
            "💡 Here’s how to get started:\n"
            "1. Copy a YouTube link.\n"
            "2. Paste it here.\n"
            "3. Wait a moment for your audio file to be ready!\n\n"
            "If you have any questions or need assistance, feel free to ask!"
        )

        await update.message.reply_text(welcome_message)

    except Exception as e:
        logging.error(f"Error in /start command: {str(e)} | User: {username}")
        await update.message.reply_text(
            "❌ Oops! Something went wrong while processing your request. Please try again later."
        )


def main():
    """Main function to run the Telegram bot."""

    load_dotenv()

    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

    if not TELEGRAM_BOT_TOKEN:
        logging.error("Telegram bot token not found in environment variables.")
        raise ValueError("TELEGRAM_BOT_TOKEN must be set in the environment variables.")

    try:
        application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

        logging.info("Telegram bot application created successfully.")

        # Adding command and message handlers
        application.add_handler(CommandHandler('start', start_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logging.info("Command and message handlers added successfully.")

        logging.info("Starting polling for updates...")

        application.run_polling()

    except Exception as e:
        logging.error(f"Error starting the bot: {str(e)}")
        raise  # Optionally re-raise the exception to signal failure


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)  # Set up logging before calling main

    try:
        main()
    except Exception as e:
        logging.critical(f"Bot crashed: {str(e)}")
