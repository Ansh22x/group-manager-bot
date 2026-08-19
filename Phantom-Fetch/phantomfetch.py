import os
import re
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, ConversationHandler

# Define conversation states
VIDEO_LINK, VIDEO_QUALITY = range(2)


# Function to sanitize filenames by removing or replacing invalid characters
def sanitize_filename(title):
    return re.sub(r'[<>:"/\\|?*]', '_', title)


# Function to handle video downloading and ask for quality option
async def download_video(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> int:
    link = update.message.text

    if not re.match(
            r'https?://(www\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)',
            link):
        await update.message.reply_text(
            'Invalid YouTube link. Please send a valid link.')
        return VIDEO_LINK

    try:
        ydl_opts = {
            'format': 'best',
            'outtmpl': 'downloaded_video.%(ext)s',
            'noplaylist': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(link, download=False)
            title = info_dict.get('title', None)
            sanitized_title = sanitize_filename(title)
            await update.message.reply_text(
                f'Video title: {title}\nChoose quality: 720p, 1080p, 4K (best) or type "audio" for audio download.'
            )

        context.user_data['video_link'] = link
        context.user_data['video_title'] = sanitized_title

    except Exception as e:
        await update.message.reply_text(
            f'Error: Unable to access video title. Please try again later.\nDetails: {str(e)}'
        )

    return VIDEO_QUALITY


# Function to handle quality selection and send video or audio
async def set_quality(update: Update,
                      context: ContextTypes.DEFAULT_TYPE) -> int:
    quality = update.message.text.lower()
    link = context.user_data.get('video_link')
    title = context.user_data.get('video_title')

    if link:
        try:
            if quality == 'audio':
                # Download audio in mp4 format (m4a is compatible with mp4 container)
                ydl_opts = {
                    'format':
                    'bestaudio[ext=m4a]',  # Download audio in m4a format
                    'outtmpl':
                    f'{title}.mp4',  # Save as mp4 file
                    'noplaylist':
                    True,
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp4',
                        'preferredquality':
                        '192',  # Set audio bitrate to 192 kbps
                    }],
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([link])

                # Check if file exists before sending
                if os.path.exists(f'{title}.mp4'):
                    with open(f'{title}.mp4', 'rb') as f:
                        await update.message.reply_audio(audio=f)
                    os.remove(f'{title}.mp4')
                else:
                    await update.message.reply_text(
                        'Error: File not found after download.')

            else:
                # Download video in mp4 format based on user-selected quality
                if quality == '720p':
                    format_selection = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
                elif quality == '1080p':
                    format_selection = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
                elif quality == '4k':
                    format_selection = 'bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
                else:
                    await update.message.reply_text(
                        'Invalid quality selection. Please choose from 720p, 1080p, or 4K.'
                    )
                    return VIDEO_QUALITY

                ydl_opts = {
                    'format':
                    format_selection,
                    'outtmpl':
                    f'{title}.mp4',  # Save as mp4 file
                    'noplaylist':
                    True,
                    'postprocessors': [{
                        'key': 'FFmpegVideoConvertor',
                        'preferedformat': 'mp4',
                    }],
                    # Optional: Limit video bitrate (for example, to 1500 kbps)
                    # This can help reduce file size significantly.
                    # Uncomment the following line to apply this setting.
                    # 'postprocessors_args': ['-b:v:0 1500k'],
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([link])

                # Check if file exists before sending
                if os.path.exists(f'{title}.mp4'):
                    with open(f'{title}.mp4', 'rb') as f:
                        await update.message.reply_video(video=f)
                    os.remove(f'{title}.mp4')
                else:
                    await update.message.reply_text(
                        'Error: File not found after download.')

        except Exception as e:
            await update.message.reply_text(f'Error: {str(e)}')

    return ConversationHandler.END


def main():
    application = ApplicationBuilder().token(
        os.getenv("TELEGRAM_TOKEN")).build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, download_video)
        ],
        states={
            VIDEO_LINK:
            [MessageHandler(filters.TEXT & ~filters.COMMAND, download_video)],
            VIDEO_QUALITY:
            [MessageHandler(filters.TEXT & ~filters.COMMAND, set_quality)],
        },
        fallbacks=[],
    )

    application.add_handler(conv_handler)

    application.run_polling()


if __name__ == '__main__':
    main()
