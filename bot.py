import logging
import os
import re
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from yt_dlp import YoutubeDL

# Configurar logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIGURAÇÕES ---
TOKEN = "8522636592:AAGGKm59cxMC5PYyjr3Dil1PZRG21C47a0g"

# Diretório de downloads
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- Funções Auxiliares ---

def create_progress_bar(progress: float, bar_length: int = 20) -> str:
    filled_length = int(bar_length * progress)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    return f"[{bar}] {progress:.1%}"

# --- Handlers do Telegram ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Olá! Eu sou o bot TM-Infinity. 🎵🎥\n\n"
        "Envie-me um link do YouTube para baixar músicas ou vídeos.\n"
        "As músicas vêm com a capa do álbum e nome correto!",
        parse_mode='Markdown'
    )

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_input = update.message.text
    
    # Se for um link do YouTube
    if re.match(r"https?://(www\.)?(youtube\.com|youtu\.be)/", user_input):
        context.user_data["user_input"] = user_input
        keyboard = [
            [InlineKeyboardButton("Baixar como Vídeo (MP4)", callback_data="download_video")],
            [InlineKeyboardButton("Baixar como Música (MP3)", callback_data="download_audio")],
        ]
        if "list=" in user_input.lower():
            keyboard.append([InlineKeyboardButton("Baixar Playlist Completa", callback_data="download_playlist_audio")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("O que você gostaria de fazer com este link?", reply_markup=reply_markup)
    
    # Se for apenas texto (Apenas ignora ou avisa que precisa de link)
    else:
        await update.message.reply_text("Por favor, envie um link do YouTube para começar o download.")

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_input = context.user_data.get("user_input")
    
    if not user_input:
        await query.edit_message_text("Erro ao recuperar o link. Por favor, envie o link novamente.")
        return

    await query.edit_message_text(f"Processando download...")
    asyncio.create_task(run_download(query, user_input, data, context))

# --- Lógica de Download ---

async def run_download(query, user_input, download_type, context):
    if download_type == "download_playlist_audio":
        await process_playlist(query, user_input, context)
    else:
        await process_single_item(query, user_input, download_type, context)

async def process_playlist(query, playlist_url, context):
    initial_msg = await query.message.reply_text("Extraindo músicas da playlist...")
    ydl_opts = {"quiet": True, "extract_flat": True}
    try:
        loop = asyncio.get_running_loop()
        with YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(playlist_url, download=False))
        entries = info.get('entries', [])
        if not entries:
            await initial_msg.edit_text("Playlist vazia ou privada.")
            return
        
        await initial_msg.edit_text(f"Encontradas {len(entries)} músicas. Baixando...")
        for i, entry in enumerate(entries):
            if entry:
                await process_single_item(query, entry['url'], "download_audio", context, is_playlist=True, index=i+1, total=len(entries))
    except Exception as e:
        await initial_msg.edit_text(f"Erro na playlist: {e}")

async def process_single_item(query, url, download_type, context, is_playlist=False, index=0, total=0):
    loop = asyncio.get_running_loop()
    
    # Configurações para áudio com capa
    if download_type == "download_audio":
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
            "writethumbnail": True,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"}
            ],
            "quiet": True,
        }
    else:
        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
            "quiet": True,
        }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            file_path = ydl.prepare_filename(info)
            if download_type == "download_audio":
                file_path = os.path.splitext(file_path)[0] + ".mp3"
            
            with open(file_path, "rb") as f:
                caption = f"{index}/{total}" if is_playlist else None
                if download_type == "download_audio":
                    await query.message.reply_audio(audio=f, title=info.get('title'), caption=caption)
                else:
                    await query.message.reply_video(video=f, caption=caption)
            os.remove(file_path)
    except Exception as e:
        logger.error(f"Erro no item: {e}")

def main() -> None:
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    logger.info("Bot TM-Infinity focado em downloads iniciado...")
    application.run_polling()

if __name__ == "__main__":
    main()
