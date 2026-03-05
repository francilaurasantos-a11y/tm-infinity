import logging
import os
import re
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from yt_dlp import YoutubeDL
from bs4 import BeautifulSoup # Importar BeautifulSoup

# Configurar logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Token do bot (configurado pelo usuário)
TOKEN = "8522636592:AAGGKm59cxMC5PYyjr3Dil1PZRG21C47a0g"

# Diretório para downloads temporários
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Dicionário para armazenar o ID da mensagem de progresso para cada chat
progress_messages = {}

# Função para gerar a barra de progresso
def create_progress_bar(progress: float, bar_length: int = 20) -> str:
    filled_length = int(bar_length * progress)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    return f"[{bar}] {progress:.1%}"

# Função para iniciar o bot
async def start(update: Update, context) -> None:
    await update.message.reply_text("Olá! Eu sou o bot TM-Infinity. Envie-me um link de vídeo/música ou o nome para baixar.")

# Função auxiliar para enviar/editar mensagens de progresso
async def send_or_edit_progress_message(chat_id: int, message_object, text: str):
    if chat_id in progress_messages:
        try:
            await message_object.edit_text(text)
        except Exception:
            # Se a mensagem não puder ser editada (ex: muito antiga), envia uma nova
            new_message = await message_object.reply_text(text)
            progress_messages[chat_id] = new_message.message_id
    else:
        new_message = await message_object.reply_text(text)
        progress_messages[chat_id] = new_message.message_id

# Função para extrair link direto de MediaFire (mantida, mas não usada para APKs)
async def get_mediafire_direct_link(url: str) -> str | None:
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        download_button = soup.find('a', class_='download_link')
        if download_button and download_button.has_attr('href'):
            return download_button['href']
    except Exception as e:
        logger.error(f"Erro ao extrair link do MediaFire: {e}", exc_info=True)
    return None

# Função para lidar com a entrada do usuário (link ou nome)
async def handle_user_input(update: Update, context) -> None:
    user_input = update.message.text
    context.user_data["user_input"] = user_input # Armazenar a entrada do usuário
    context.user_data["original_message"] = update.message # Armazenar a mensagem original para referência

    keyboard = [
        [InlineKeyboardButton("Baixar como Vídeo (MP4)", callback_data="download_video")],
        [InlineKeyboardButton("Baixar como Música (MP3)", callback_data="download_audio")],
    ]
    
    # Adicionar botão para baixar playlist APENAS se for uma URL
    if re.match(r"https?://[^\s]+\.\S+", user_input):
        # Verificar se a URL pode ser uma playlist (ex: youtube.com/playlist, spotify.com/playlist)
        if "playlist" in user_input.lower() or "list=" in user_input.lower():
            keyboard.append([InlineKeyboardButton("Baixar Playlist de Música", callback_data="download_playlist_audio")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("O que você gostaria de baixar?", reply_markup=reply_markup)

# Função para lidar com a escolha do botão (callback)
async def button_callback_handler(update: Update, context) -> None:
    query = update.callback_query
    await query.answer() # Responder ao callback para remover o estado de \'carregando\' do botão

    original_user_input = context.user_data.get("user_input") # Usar a entrada original para exibição
    original_message = context.user_data.get("original_message")

    if not original_user_input or not original_message:
        await query.edit_message_text("Desculpe, não consegui recuperar sua última solicitação. Por favor, envie novamente.")
        return

    download_type = query.data

    await query.edit_message_text(f"Recebido: {original_user_input}. Processando como {download_type.replace("download_", "").replace("_", " ").upper()}...")

    is_url = re.match(r"https?://[^\s]+\.\S+", original_user_input)

    # Lógica para download de playlist
    if download_type == "download_playlist_audio":
        if not is_url:
            await send_progress_message(query.message, "Para baixar uma playlist, por favor, forneça um link de playlist.")
            return
        
        await send_progress_message(query.message, f"Iniciando download da playlist: {original_user_input}...")
        
        ydl_opts_playlist = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(DOWNLOAD_DIR, "%(playlist_index)s - %(title)s.%(ext)s"),
            "noplaylist": False, # Permitir playlists
            "extract_flat": False, # Extrair informações completas de cada item
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "restrictfilenames": True,
            "merge_output_format": "mp3",
        }

        try:
            with YoutubeDL(ydl_opts_playlist) as ydl:
                info_dict = ydl.extract_info(original_user_input, download=False) # Apenas extrair info da playlist
                
                if "entries" not in info_dict:
                    await send_progress_message(query.message, "Não foi possível encontrar itens na playlist ou a URL não é de uma playlist válida.")
                    return
                
                total_tracks = len(info_dict["entries"])
                await send_progress_message(query.message, f"Encontradas {total_tracks} músicas na playlist. Iniciando downloads...")

                for i, entry in enumerate(info_dict["entries"]):
                    if entry:
                        try:
                            current_track_message = f"Baixando {i+1} de {total_tracks}: {entry["title"]}...\n{create_progress_bar(0)}"
                            progress_msg = await query.message.reply_text(current_track_message)
                            
                            # Baixar e processar cada item individualmente
                            single_track_ydl_opts = ydl_opts_playlist.copy()
                            single_track_ydl_opts["progress_hooks"] = [lambda d, msg=progress_msg: download_progress_hook(d, msg)]
                            
                            single_track_ydl = YoutubeDL(single_track_ydl_opts)
                            single_track_info = single_track_ydl.extract_info(entry["url"], download=True)
                            file_path = single_track_ydl.prepare_filename(single_track_info)
                            
                            # Garantir que o arquivo é .mp3
                            mp3_path = os.path.splitext(file_path)[0] + ".mp3"
                            if os.path.exists(mp3_path):
                                file_path = mp3_path
                            
                            await progress_msg.edit_text(f"Enviando {i+1} de {total_tracks}: {entry["title"]}...")
                            with open(file_path, "rb") as document:
                                await query.message.reply_document(document=document)
                            
                            os.remove(file_path) # Apagar do armazenamento após enviar
                            logger.info(f"Música {file_path} da playlist enviada e removida com sucesso.")

                        except Exception as e_track:
                            logger.error(f"Erro ao baixar ou enviar música da playlist {entry.get("title", "")}: {e_track}", exc_info=True)
                            await query.message.reply_text(f"Erro ao baixar {entry.get("title", "")}: {e_track}")
                
                await send_progress_message(query.message, "Download da playlist concluído!")

        except Exception as e:
            logger.error(f"Erro ao processar playlist: {e}", exc_info=True)
            await send_progress_message(query.message, f"Ocorreu um erro ao processar a playlist: {e}")
        return # Finaliza a função para download de playlist

    # Lógica existente para vídeo e áudio (yt-dlp)
    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
        "noplaylist": True,
        "progress_hooks": [lambda d: download_progress_hook(d, query.message)],
        "restrictfilenames": True,
        "merge_output_format": "mp4",
    }

    if download_type == "download_audio":
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    try:
        with YoutubeDL(ydl_opts) as ydl:
            if is_url:
                info = ydl.extract_info(original_user_input, download=True)
            else:
                search_term = original_user_input
                
                await send_progress_message(query.message, f"Buscando por: {original_user_input}...")
                
                search_results = ydl.extract_info(f"ytsearch1:{search_term}", download=False)
                
                if not search_results or "entries" not in search_results or not search_results["entries"]:
                    await send_progress_message(query.message, "Nenhum resultado encontrado para sua busca.")
                    return
                
                first_result = search_results["entries"][0]
                await send_progress_message(query.message, f"Encontrado: {first_result["title"]}. Baixando...")
                info = ydl.extract_info(first_result["webpage_url"], download=True)

            file_path = ydl.prepare_filename(info)
            
            if download_type == "download_audio" and not file_path.endswith(".mp3"):
                mp3_path = os.path.splitext(file_path)[0] + ".mp3"
                if os.path.exists(mp3_path):
                    file_path = mp3_path

            await send_progress_message(query.message, "Download concluído, enviando...")
            
            with open(file_path, "rb") as document:
                await query.message.reply_document(document=document)
            
            os.remove(file_path)
            logger.info(f"Arquivo {file_path} enviado e removido com sucesso.")

    except Exception as e:
        logger.error(f"Erro ao baixar mídia: {e}", exc_info=True)
        await send_progress_message(query.message, f"Ocorreu um erro ao baixar a mídia: {e}")

# A função download_progress_hook agora recebe o objeto message correto
async def download_progress_hook(d, message_object):
    if d["status"] == "downloading":
        total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
        downloaded_bytes = d.get("downloaded_bytes", 0)
        if total_bytes:
            progress = downloaded_bytes / total_bytes
            speed = d.get("speed")
            eta = d.get("eta")

            progress_bar = create_progress_bar(progress)
            status_text = f"Baixando: {progress_bar}"
            if speed: status_text += f" | Velocidade: {speed / 1024:.2f} KiB/s"
            if eta: status_text += f" | ETA: {eta}s"
            
            try:
                await message_object.edit_text(status_text)
            except Exception as e:
                logger.debug(f"Erro ao editar mensagem de progresso: {e}")
    elif d["status"] == "finished":
        await message_object.edit_text("Download concluído. Processando...")

def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    logger.info("Bot TM-Infinity iniciado...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
