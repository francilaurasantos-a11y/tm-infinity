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
        "Olá! Eu sou o bot TM-Infinity. 🎵🎥🎬\n\n"
        "Envie-me o **nome da música** ou um **link** para baixar!\n\n"
        "✅ **Suporte para:**\n"
        "- YouTube (Música e Vídeo)\n"
        "- Instagram (Reels e Vídeos)\n"
        "- TikTok (Vídeos)\n\n"
        "As músicas vêm com a capa do álbum e nome correto!",
        parse_mode='Markdown'
    )

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_input = update.message.text
    context.user_data["user_input"] = user_input
    
    # Detectar se é link do Instagram ou TikTok
    is_social = any(x in user_input.lower() for x in ["instagram.com", "tiktok.com"])
    
    keyboard = []
    if is_social:
        keyboard.append([InlineKeyboardButton("Baixar Vídeo", callback_data="download_video")])
    else:
        keyboard.append([InlineKeyboardButton("Baixar como Música (MP3)", callback_data="download_audio")])
        keyboard.append([InlineKeyboardButton("Baixar como Vídeo (MP4)", callback_data="download_video")])
        
        # Se for um link de playlist do YouTube
        if "list=" in user_input.lower() or "playlist" in user_input.lower():
            keyboard.append([InlineKeyboardButton("Baixar Playlist Completa", callback_data="download_playlist_audio")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"O que você deseja baixar?", reply_markup=reply_markup)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_input = context.user_data.get("user_input")
    
    if not user_input:
        await query.edit_message_text("Erro ao recuperar a solicitação. Envie o nome ou link novamente.")
        return

    await query.edit_message_text(f"Iniciando processamento...")
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
            await initial_msg.edit_text("Não foi possível encontrar músicas nesta playlist.")
            return
        
        await initial_msg.edit_text(f"Encontradas {len(entries)} músicas. Baixando...")
        for i, entry in enumerate(entries):
            if entry:
                url = entry.get('url') or entry.get('webpage_url')
                if url:
                    await process_single_item(query, url, "download_audio", context, is_playlist=True, index=i+1, total=len(entries))
    except Exception as e:
        await initial_msg.edit_text(f"Erro na playlist: {e}")

async def process_single_item(query, input_data, download_type, context, is_playlist=False, index=0, total=0):
    loop = asyncio.get_running_loop()
    is_url = re.match(r"https?://", input_data)
    
    # Opções base do yt-dlp
    ydl_opts = {
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
        "retries": 10,
        "socket_timeout": 30,
    }

    # Se for busca por nome (YouTube)
    if not is_url:
        search_query = f"ytsearch1:{input_data}"
    else:
        search_query = input_data

    # Configurações específicas por tipo
    if download_type == "download_audio":
        ydl_opts.update({
            "format": "bestaudio/best",
            "writethumbnail": True,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"}
            ],
        })
    else:
        # Para Instagram/TikTok, o formato mp4 geralmente é o padrão direto
        ydl_opts.update({
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
        })
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(search_query, download=True))
            
            # Se for busca, pega o primeiro resultado
            if 'entries' in info:
                info = info['entries'][0]
            
            file_path = ydl.prepare_filename(info)
            if download_type == "download_audio":
                file_path = os.path.splitext(file_path)[0] + ".mp3"
            
            # Para alguns casos onde o mp4 já é o final
            if not os.path.exists(file_path) and os.path.exists(file_path.replace(".mp3", ".mp4")):
                file_path = file_path.replace(".mp3", ".mp4")

            if os.path.exists(file_path):
                caption = f"Faixa {index}/{total}" if is_playlist else f"Aqui está: {info.get('title', 'Vídeo')}"
                with open(file_path, "rb") as f:
                    if download_type == "download_audio" and file_path.endswith(".mp3"):
                        await query.message.reply_audio(audio=f, title=info.get('title'), caption=caption)
                    else:
                        await query.message.reply_video(video=f, caption=caption)
                os.remove(file_path)
            else:
                await query.message.reply_text(f"Erro ao processar o arquivo.")

    except Exception as e:
        logger.error(f"Erro no item: {e}")
        if not is_playlist:
            await query.message.reply_text(f"Desculpe, não consegui baixar. Verifique o link ou tente novamente.")

def main() -> None:
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    logger.info("Bot TM-Infinity com suporte Instagram/TikTok iniciado...")
    application.run_polling()

if __name__ == "__main__":
    main()
