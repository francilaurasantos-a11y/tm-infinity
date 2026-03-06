import logging
import os
import re
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from yt_dlp import YoutubeDL

# Configurar logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Token do bot
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

async def start(update: Update, context) -> None:
    await update.message.reply_text("Olá! Eu sou o bot TM-Infinity. Envie-me um link de vídeo/música ou o nome para baixar.")

async def handle_user_input(update: Update, context) -> None:
    user_input = update.message.text
    context.user_data["user_input"] = user_input
    context.user_data["original_message"] = update.message

    keyboard = [
        [InlineKeyboardButton("Baixar como Vídeo (MP4)", callback_data="download_video")],
        [InlineKeyboardButton("Baixar como Música (MP3)", callback_data="download_audio")],
    ]

    if re.match(r"https?://[^\s]+\.\S+", user_input) and ("playlist" in user_input.lower() or "list=" in user_input.lower() or "album" in user_input.lower()):
        keyboard.append([InlineKeyboardButton("Baixar Playlist de Música", callback_data="download_playlist_audio")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("O que você gostaria de baixar?", reply_markup=reply_markup)

async def button_callback_handler(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()

    user_input = context.user_data.get("user_input")
    if not user_input:
        await query.edit_message_text("Desculpe, não consegui recuperar sua solicitação. Por favor, envie novamente.")
        return

    download_type = query.data
    await query.edit_message_text(f"Recebido: {user_input}. Processando como {download_type.replace('download_', '').replace('_', ' ').upper()}...")

    # Executa o download em uma nova tarefa para não bloquear o bot
    asyncio.create_task(run_download(query, user_input, download_type, context))

# --- Lógica de Download ---

async def run_download(query, user_input, download_type, context):
    if download_type == "download_playlist_audio":
        await process_playlist(query, user_input, context)
    else:
        await process_single_item(query, user_input, download_type, context)

async def process_playlist(query, playlist_url, context):
    initial_msg = await query.message.reply_text("Extraindo informações da playlist... Isso pode levar um tempo.")
    
    # Usar extract_flat=\'in_playlist\' para obter IDs e URLs básicas rapidamente
    # Isso é crucial para Spotify para evitar o bloqueio inicial
    ydl_opts_playlist_info = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": 'in_playlist', 
        "force_generic_extractor": True, # Forçar extrator genérico para Spotify
        "extractor_args": {
            "spotify": {
                "api_client_id": None, 
                "api_client_secret": None,
            }
        }
    }

    try:
        loop = asyncio.get_event_loop()
        info_dict = await loop.run_in_executor(None, lambda: YoutubeDL(ydl_opts_playlist_info).extract_info(playlist_url, download=False))

        entries = info_dict.get("entries", [])
        if not entries:
            await initial_msg.edit_text("Não foi possível encontrar músicas na playlist ou a URL não é de uma playlist válida.")
            return

        total_tracks = len(entries)
        await initial_msg.edit_text(f"Encontradas {total_tracks} músicas na playlist. Iniciando downloads...")

        for i, entry in enumerate(entries):
            if entry:
                try:
                    track_id = entry.get("id")
                    track_title = entry.get("title", f"Faixa {i+1}")
                    # Para Spotify, o \'url\' do entry pode ser um URI spotify:track:ID, precisamos converter
                    track_url = entry.get("url") or entry.get("webpage_url")

                    if "spotify" in playlist_url and track_id:
                        # Construir a URL HTTP para o yt-dlp para cada faixa do Spotify
                        track_url = f"https://open.spotify.com/track/{track_id}"
                    
                    if not track_url:
                        await query.message.reply_text(f"Não foi possível obter o link para a música {track_title}. Pulando.")
                        logger.warning(f"Não foi possível obter o link para a música {track_title}. Pulando.")
                        continue

                    current_track_message_text = f"Baixando {i+1} de {total_tracks}: {track_title}...\n{create_progress_bar(0)}"
                    progress_msg = await query.message.reply_text(current_track_message_text)
                    
                    single_track_ydl_opts = {
                        "format": "bestaudio/best",
                        "outtmpl": os.path.join(DOWNLOAD_DIR, f"{i+1} - %(title)s.%(ext)s"),
                        "noplaylist": True, 
                        "postprocessors": [{
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        }],
                        "restrictfilenames": True,
                        "merge_output_format": "mp3",
                        "progress_hooks": [lambda d, msg=progress_msg, loop=context.application.loop: download_progress_hook(d, msg, loop)],
                        "quiet": True,
                        "no_warnings": True,
                    }
                    
                    single_track_ydl = YoutubeDL(single_track_ydl_opts)
                    single_track_info = await loop.run_in_executor(None, lambda: single_track_ydl.extract_info(track_url, download=True))
                    file_path = single_track_ydl.prepare_filename(single_track_info)
                    
                    mp3_path = os.path.splitext(file_path)[0] + ".mp3"
                    if os.path.exists(mp3_path):
                        file_path = mp3_path

                    await progress_msg.edit_text(f"Enviando {i+1} de {total_tracks}: {track_title}...")
                    with open(file_path, "rb") as document:
                        await query.message.reply_document(document=document)
                    
                    os.remove(file_path) 
                    logger.info(f"Música {file_path} da playlist enviada e removida com sucesso.")

                except Exception as e_track:
                    logger.error(f"Erro ao baixar ou enviar música da playlist {track_title}: {e_track}", exc_info=True)
                    await query.message.reply_text(f"Erro ao baixar {track_title}: {e_track}")
            
        await query.message.reply_text("Download da playlist concluído!")

    except Exception as e:
        logger.error(f"Erro ao processar playlist: {e}", exc_info=True)
        await initial_msg.edit_text(f"Ocorreu um erro ao processar a playlist: {e}")

async def process_single_item(query, user_input, download_type, context):
    is_url = re.match(r"https?://[^\s]+\.\S+", user_input)
    progress_msg = await query.message.reply_text(f"Iniciando...\n{create_progress_bar(0)}")
    loop = asyncio.get_event_loop()

    ydl_opts = {
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
        "noplaylist": True,
        "restrictfilenames": True,
        "progress_hooks": [lambda d, msg=progress_msg, loop=loop: download_progress_hook(d, msg, loop)],
    }

    if download_type == "download_audio":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    else:
        ydl_opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        ydl_opts["merge_output_format"] = "mp4"

    try:
        with YoutubeDL(ydl_opts) as ydl:
            if not is_url:
                await progress_msg.edit_text(f"Buscando por: {user_input}...")
                search_results = await loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch1:{user_input}", download=False))
                if not search_results.get("entries"):
                    await progress_msg.edit_text("Nenhum resultado encontrado.")
                    return
                user_input = search_results["entries"][0]["webpage_url"]
                await progress_msg.edit_text(f"Encontrado: {search_results["entries"][0]["title"]}. Baixando...")

            info = await loop.run_in_executor(None, lambda: ydl.extract_info(user_input, download=True))
            file_path = ydl.prepare_filename(info)
            
            final_path = file_path
            if download_type == "download_audio":
                final_path = os.path.splitext(file_path)[0] + ".mp3"

            if os.path.exists(final_path):
                await progress_msg.edit_text("Enviando...")
                with open(final_path, "rb") as document:
                    await query.message.reply_document(document=document)
                os.remove(final_path)
            else:
                await progress_msg.edit_text("Falha ao encontrar o arquivo final.")

    except Exception as e:
        logger.error(f"Erro ao baixar item único: {e}")
        await progress_msg.edit_text(f"Ocorreu um erro: {e}")

def download_progress_hook(d, message_object, loop):
    if d["status"] == "downloading":
        total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
        if total_bytes:
            progress = d["downloaded_bytes"] / total_bytes
            status_text = f"Baixando: {create_progress_bar(progress)} | {d.get("_speed_str", "N/A")} | {d.get("_eta_str", "N/A")}"
            
            async def edit_message_async():
                try: await message_object.edit_text(status_text)
                except Exception: pass # Ignorar erros se a mensagem não puder ser editada
            
            asyncio.run_coroutine_threadsafe(edit_message_async(), loop)

    elif d["status"] == "finished":
        async def edit_message_async():
            try: await message_object.edit_text("Download concluído. Processando e convertendo...")
            except Exception: pass
        
        asyncio.run_coroutine_threadsafe(edit_message_async(), loop)

# --- Função Principal ---

def main() -> None:
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    logger.info("Bot TM-Infinity iniciado...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
