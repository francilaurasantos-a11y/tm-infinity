import logging
import os
import re
import asyncio
import time
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
    """Cria uma barra de progresso visual"""
    filled_length = int(bar_length * progress)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    return f"[{bar}] {progress:.1%}"

def format_bytes(bytes_value):
    """Converte bytes para formato legível (KB, MB, GB)"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f}{unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f}TB"

def format_time(seconds):
    """Converte segundos para formato HH:MM:SS"""
    if seconds is None or seconds == 0:
        return "00:00:00"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

# --- Handlers do Telegram ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Olá! Eu sou o bot TM-Infinity. 🎵🎥🎬\n\n"
        "Envie-me o **nome da música** ou um **link** para baixar!\n\n"
        "✅ **Suporte para:**\n"
        "- YouTube (Música MP3)\n"
        "- Instagram (Vídeos)\n"
        "- TikTok (Vídeos)\n\n"
        "As músicas vêm com a capa do álbum e nome correto!\n\n"
        "📱 Desenvolvido por: **Thiago Santos**",
        parse_mode='Markdown'
    )

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_input = update.message.text
    context.user_data["user_input"] = user_input
    context.user_data["original_message"] = update.message
    
    # Detectar se é link do Instagram ou TikTok
    is_instagram = "instagram.com" in user_input.lower()
    is_tiktok = "tiktok.com" in user_input.lower()
    is_social = is_instagram or is_tiktok
    
    if is_social:
        # Para Instagram/TikTok, baixa vídeo automaticamente
        status_msg = await update.message.reply_text("⏳ Iniciando download do vídeo...")
        context.user_data["status_msg"] = status_msg
        asyncio.create_task(run_download(status_msg, user_input, "download_video", context))
    else:
        # Se for um link de playlist do YouTube
        if "list=" in user_input.lower() or "playlist" in user_input.lower():
            keyboard = [
                [InlineKeyboardButton("Baixar Playlist (Áudio MP3)", callback_data="download_playlist_audio")],
                [InlineKeyboardButton("Baixar Playlist (Vídeo MP4)", callback_data="download_playlist_video")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f"Como deseja baixar a playlist?", reply_markup=reply_markup)
        else:
            # Para buscas e links individuais do YouTube, baixa MP3 automaticamente
            status_msg = await update.message.reply_text("⏳ Iniciando download da música em MP3...")
            context.user_data["status_msg"] = status_msg
            asyncio.create_task(run_download(status_msg, user_input, "download_audio", context))

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_input = context.user_data.get("user_input")
    
    if not user_input:
        await query.edit_message_text("Erro ao recuperar a solicitação. Envie o nome ou link novamente.")
        return

    status_msg = await query.edit_message_text(f"⏳ Processando...")
    context.user_data["status_msg"] = status_msg
    context.user_data["original_message"] = query.message
    asyncio.create_task(run_download(status_msg, user_input, data, context))

# --- Lógica de Download ---

async def run_download(status_msg, user_input, download_type, context):
    if download_type.startswith("download_playlist"):
        media_type = "download_audio" if "audio" in download_type else "download_video"
        await process_playlist(status_msg, user_input, media_type, context)
    else:
        await process_single_item(status_msg, user_input, download_type, context)

async def process_playlist(status_msg, playlist_url, media_type, context):
    try:
        await status_msg.edit_text("📋 Extraindo itens da playlist...")
        ydl_opts = {"quiet": True, "extract_flat": True}
        loop = asyncio.get_running_loop()
        
        with YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(playlist_url, download=False))
        
        entries = info.get('entries', [])
        if not entries:
            await status_msg.edit_text("❌ Não foi possível encontrar itens nesta playlist.")
            return
        
        total = len(entries)
        await status_msg.edit_text(f"📦 Encontrados {total} itens. Iniciando downloads...")
        
        for i, entry in enumerate(entries):
            if entry:
                url = entry.get('url') or entry.get('webpage_url')
                if not url and entry.get('id'):
                    url = f"https://www.youtube.com/watch?v={entry.get('id')}"
                
                if url:
                    await process_single_item(status_msg, url, media_type, context, is_playlist=True, index=i+1, total=total)
        
        await status_msg.edit_text(f"✅ Download da playlist finalizado!")
    except Exception as e:
        logger.error(f"Erro na playlist: {e}")
        await status_msg.edit_text(f"❌ Erro ao processar playlist: {str(e)[:100]}...")

async def process_single_item(status_msg, input_data, download_type, context, is_playlist=False, index=0, total=0):
    loop = asyncio.get_running_loop()
    is_url = re.match(r"https?://", input_data)
    
    ydl_opts = {
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
        "retries": 10,
        "socket_timeout": 30,
        "ignoreerrors": True,
    }

    if not is_url:
        search_query = f"ytsearch1:{input_data}"
    else:
        search_query = input_data

    # Variáveis para rastrear progresso
    progress_data = {
        "last_update": time.time(),
        "status_msg": status_msg,
        "is_playlist": is_playlist,
        "index": index,
        "total": total,
        "loop": loop
    }

    def progress_hook(d):
        """Hook para atualizar o progresso do download"""
        if d['status'] == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total_bytes = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
            speed = d.get('speed', 0)
            eta = d.get('eta', 0)
            
            current_time = time.time()
            if current_time - progress_data["last_update"] >= 2 and total_bytes > 0:
                progress_data["last_update"] = current_time
                progress = downloaded / total_bytes
                bar = create_progress_bar(progress, 15)
                
                progress_text = (
                    f"⬇️ Baixando...\n\n"
                    f"{bar}\n"
                    f"{format_bytes(downloaded)} / {format_bytes(total_bytes)}\n"
                    f"🚀 Velocidade: {format_bytes(speed)}/s\n"
                    f"⏱️ Tempo restante: {format_time(eta)}"
                )
                
                if progress_data["is_playlist"]:
                    progress_text = f"📦 Item {progress_data['index']}/{progress_data['total']}\n\n" + progress_text
                
                try:
                    asyncio.run_coroutine_threadsafe(
                        status_msg.edit_text(progress_text),
                        progress_data["loop"]
                    )
                except Exception as e:
                    logger.error(f"Erro ao atualizar progresso: {e}")
        
        elif d['status'] == 'finished':
            try:
                asyncio.run_coroutine_threadsafe(
                    status_msg.edit_text("✅ Download concluído! Processando arquivo..."),
                    progress_data["loop"]
                )
            except Exception as e:
                logger.error(f"Erro ao finalizar progresso: {e}")

    if download_type == "download_audio":
        ydl_opts.update({
            "format": "bestaudio/best",
            "writethumbnail": True,
            "progress_hooks": [progress_hook],
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"}
            ],
        })
    else:
        ydl_opts.update({
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook],
        })
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = await loop.run_in_executor(None, lambda: ydl.extract_info(search_query, download=False))
            
            if not info_dict:
                raise Exception("Nenhum resultado encontrado.")

            if 'entries' in info_dict:
                if not info_dict['entries']:
                    raise Exception("Busca não retornou resultados.")
                info = info_dict['entries'][0]
            else:
                info = info_dict

            await loop.run_in_executor(None, lambda: ydl.download([info['webpage_url'] if 'webpage_url' in info else search_query]))
            
            file_path = ydl.prepare_filename(info)
            if download_type == "download_audio":
                base, _ = os.path.splitext(file_path)
                file_path = base + ".mp3"
            
            if not os.path.exists(file_path):
                base, _ = os.path.splitext(file_path)
                for ext in ['.mp3', '.mp4', '.mkv', '.webm', '.m4a']:
                    if os.path.exists(base + ext):
                        file_path = base + ext
                        break

            if os.path.exists(file_path):
                title = info.get('title', 'Arquivo')
                file_size = os.path.getsize(file_path)
                caption = f"📦 Item {index}/{total}\n🎵 {title}\n📊 Tamanho: {format_bytes(file_size)}" if is_playlist else f"✅ Aqui está: {title}\n📊 Tamanho: {format_bytes(file_size)}"
                
                await status_msg.edit_text(f"📤 Enviando arquivo para o Telegram...")
                
                # Usar a mensagem original do usuário para responder
                original_msg = context.user_data.get("original_message")
                if original_msg is None:
                    original_msg = status_msg.reply_to_message
                
                with open(file_path, "rb") as f:
                    if download_type == "download_audio" and file_path.endswith(".mp3"):
                        await original_msg.reply_audio(audio=f, title=title, caption=caption)
                    else:
                        await original_msg.reply_video(video=f, caption=caption)
                
                await status_msg.edit_text(f"✅ Arquivo enviado com sucesso!")
                
                try:
                    os.remove(file_path)
                    base_path = os.path.splitext(file_path)[0]
                    for ext in ['.jpg', '.webp', '.png', '.temp']:
                        if os.path.exists(base_path + ext): os.remove(base_path + ext)
                except:
                    pass
            else:
                if not is_playlist:
                    await status_msg.edit_text(f"❌ Erro: O arquivo não foi gerado corretamente.")

    except Exception as e:
        logger.error(f"Erro no item: {e}")
        if not is_playlist:
            await status_msg.edit_text(f"❌ Desculpe, ocorreu um erro: {str(e)[:100]}")

def main() -> None:
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    logger.info("Bot TM-Infinity iniciado...")
    application.run_polling()

if __name__ == "__main__":
    main()
