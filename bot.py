import logging
import os
import re
import asyncio
import zipfile
import shutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from yt_dlp import YoutubeDL
import requests

# Configurar logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIGURAÇÕES ---
TOKEN = "8522636592:AAGGKm59cxMC5PYyjr3Dil1PZRG21C47a0g"

# Token do bot de divulgação (Node.js) — notificado automaticamente após cada MP3
DIVULGACAO_TOKEN = "8362410901:AAGMZ24BVZNpv4ttJeRpZ1qLonoS9tORPUU"

# Diretório de downloads
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- Funções Auxiliares ---

def create_progress_bar(progress: float, bar_length: int = 20) -> str:
    filled_length = int(bar_length * progress)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    return f"[{bar}] {progress:.1%}"


def notify_divulgacao(chat_id: int, file_id: str, song_name: str, file_size: int):
    """Avisa o bot de divulgação via webhook local (porta 3333)."""
    try:
        requests.post(
            "http://localhost:3333/nova-musica",
            json={
                "chat_id": chat_id,
                "file_id": file_id,
                "song_name": song_name,
            },
            timeout=10
        )
        logger.info(f"[DIVULGAÇÃO] Notificado via webhook: {song_name}")
    except Exception as e:
        logger.warning(f"[DIVULGAÇÃO] Falha ao notificar: {e}")

# --- Handlers do Telegram ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Olá! Eu sou o bot TM-Infinity. 🎵🎥🎬\n\n"
        "Envie-me o **nome da música**, um **link** ou uma **categoria** para baixar!\n\n"
        "✅ **Suporte para:**\n"
        "- YouTube (Música, Vídeo e Playlists)\n"
        "- Instagram (Reels e Vídeos)\n"
        "- TikTok (Vídeos)\n"
        "- **Categorias:** Digite o nome de um gênero (ex: Sertanejo) para baixar 200 músicas em .zip!\n\n"
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
        # Se for um link de playlist do YouTube
        if "list=" in user_input.lower() or "playlist" in user_input.lower():
            keyboard.append([InlineKeyboardButton("Baixar Playlist (Áudio)", callback_data="download_playlist_audio")])
            keyboard.append([InlineKeyboardButton("Baixar Playlist (Vídeo)", callback_data="download_playlist_video")])
        else:
            keyboard.append([InlineKeyboardButton("Baixar como Música (MP3)", callback_data="download_audio")])
            keyboard.append([InlineKeyboardButton("Baixar como Vídeo (MP4)", callback_data="download_video")])
            # Adicionar opção de baixar 200 músicas por categoria
            keyboard.append([InlineKeyboardButton(f"Baixar 200 músicas de '{user_input}' (.zip)", callback_data="download_category_zip")])
        
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
    if download_type == "download_category_zip":
        await process_category_zip(query, user_input, context)
    elif download_type.startswith("download_playlist"):
        media_type = "download_audio" if "audio" in download_type else "download_video"
        await process_playlist(query, user_input, media_type, context)
    else:
        await process_single_item(query, user_input, download_type, context)

async def process_category_zip(query, category, context):
    status_msg = await query.message.reply_text(f"🔍 Buscando 200 músicas da categoria: {category}...")
    
    # Criar pasta temporária para a categoria
    category_dir = os.path.join(DOWNLOAD_DIR, f"category_{query.from_user.id}_{int(asyncio.get_event_loop().time())}")
    if not os.path.exists(category_dir):
        os.makedirs(category_dir)
    
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(category_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
        "ignoreerrors": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}, # Qualidade menor para o zip não ficar gigante
            {"key": "FFmpegMetadata"}
        ],
    }

    try:
        loop = asyncio.get_running_loop()
        search_query = f"ytsearch200:{category}"
        
        with YoutubeDL(ydl_opts) as ydl:
            await status_msg.edit_text(f"⏳ Baixando 200 músicas de '{category}'... Isso pode demorar um pouco.")
            await loop.run_in_executor(None, lambda: ydl.download([search_query]))
        
        # Criar o arquivo ZIP
        zip_filename = f"{category.replace(' ', '_')}_200_musicas.zip"
        zip_path = os.path.join(DOWNLOAD_DIR, zip_filename)
        
        await status_msg.edit_text(f"📦 Compactando músicas em {zip_filename}...")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(category_dir):
                for file in files:
                    if file.endswith(".mp3"):
                        zipf.write(os.path.join(root, file), file)
        
        # Enviar o arquivo ZIP
        await status_msg.edit_text(f"📤 Enviando arquivo ZIP...")
        with open(zip_path, "rb") as f:
            await query.message.reply_document(document=f, filename=zip_filename, caption=f"✅ Aqui estão as 200 músicas de: {category}")
        
        # Limpeza
        await status_msg.delete()
        os.remove(zip_path)
        shutil.rmtree(category_dir)
        
    except Exception as e:
        logger.error(f"Erro ao processar categoria: {e}")
        await query.message.reply_text(f"Erro ao baixar categoria: {str(e)[:100]}")
        if os.path.exists(category_dir):
            shutil.rmtree(category_dir)

async def process_playlist(query, playlist_url, media_type, context):
    initial_msg = await query.message.reply_text("Extraindo itens da playlist...")
    ydl_opts = {"quiet": True, "extract_flat": True}
    try:
        loop = asyncio.get_running_loop()
        with YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(playlist_url, download=False))
        
        entries = info.get('entries', [])
        if not entries:
            await initial_msg.edit_text("Não foi possível encontrar itens nesta playlist.")
            return
        
        total = len(entries)
        await initial_msg.edit_text(f"Encontrados {total} itens. Iniciando downloads...")
        
        for i, entry in enumerate(entries):
            if entry:
                url = entry.get('url') or entry.get('webpage_url')
                if not url and entry.get('id'):
                    url = f"https://www.youtube.com/watch?v={entry.get('id')}"
                
                if url:
                    await process_single_item(query, url, media_type, context, is_playlist=True, index=i+1, total=total)
        
        await query.message.reply_text(f"✅ Download da playlist finalizado!")
    except Exception as e:
        logger.error(f"Erro na playlist: {e}")
        await initial_msg.edit_text(f"Erro ao processar playlist: {str(e)[:100]}...")

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
        "ignoreerrors": True,
    }

    if not is_url:
        search_query = f"ytsearch1:{input_data}"
    else:
        search_query = input_data

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
        ydl_opts.update({
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
        })
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            # Extrair informações primeiro para obter o título e garantir que existe resultado
            info_dict = await loop.run_in_executor(None, lambda: ydl.extract_info(search_query, download=False))
            
            if not info_dict:
                raise Exception("Nenhum resultado encontrado.")

            # Se for busca, o resultado está em 'entries'
            if 'entries' in info_dict:
                if not info_dict['entries']:
                    raise Exception("Busca não retornou resultados.")
                info = info_dict['entries'][0]
            else:
                info = info_dict

            # Agora faz o download real
            await loop.run_in_executor(None, lambda: ydl.download([info['webpage_url'] if 'webpage_url' in info else search_query]))
            
            file_path = ydl.prepare_filename(info)
            if download_type == "download_audio":
                base, _ = os.path.splitext(file_path)
                file_path = base + ".mp3"
            
            # Verificação de segurança para extensões variadas
            if not os.path.exists(file_path):
                base, _ = os.path.splitext(file_path)
                for ext in ['.mp3', '.mp4', '.mkv', '.webm', '.m4a']:
                    if os.path.exists(base + ext):
                        file_path = base + ext
                        break

            if os.path.exists(file_path):
                title = info.get('title', 'Arquivo')
                caption = f"📦 Item {index}/{total}\n🎵 {title}" if is_playlist else f"✅ Aqui está: {title}"
                
                with open(file_path, "rb") as f:
                    if download_type == "download_audio" and file_path.endswith(".mp3"):
                        sent = await query.message.reply_audio(audio=f, title=title, caption=caption)
                        # Notifica o bot de divulgação automaticamente
                        notify_divulgacao(
                            chat_id=query.message.chat_id,
                            file_id=sent.audio.file_id,
                            song_name=title,
                            file_size=sent.audio.file_size or 0
                        )
                    else:
                        await query.message.reply_video(video=f, caption=caption)
                
                try:
                    os.remove(file_path)
                    base_path = os.path.splitext(file_path)[0]
                    for ext in ['.jpg', '.webp', '.png', '.temp']:
                        if os.path.exists(base_path + ext): os.remove(base_path + ext)
                except:
                    pass
            else:
                if not is_playlist:
                    await query.message.reply_text(f"Erro: O arquivo não foi gerado corretamente.")

    except Exception as e:
        logger.error(f"Erro no item: {e}")
        if not is_playlist:
            await query.message.reply_text(f"Desculpe, ocorreu um erro: {str(e)[:100]}")

def main() -> None:
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    logger.info("Bot TM-Infinity iniciado...")
    application.run_polling()

if __name__ == "__main__":
    main()
