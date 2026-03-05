import logging
import os
import re
import requests # Importar a biblioteca requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from yt_dlp import YoutubeDL

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

# Função para iniciar o bot
async def start(update: Update, context) -> None:
    await update.message.reply_text("Olá! Eu sou o bot TM-Infinity. Envie-me um link de vídeo/música ou o nome para baixar.")

# Função auxiliar para enviar mensagens de progresso
async def send_progress_message(message_object, text: str):
    await message_object.reply_text(text)

# Função para lidar com a entrada do usuário (link ou nome)
async def handle_user_input(update: Update, context) -> None:
    user_input = update.message.text
    context.user_data["user_input"] = user_input # Armazenar a entrada do usuário
    context.user_data["original_message"] = update.message # Armazenar a mensagem original para referência

    keyboard = [
        [InlineKeyboardButton("Baixar como Vídeo (MP4)", callback_data="download_video")],
        [InlineKeyboardButton("Baixar como Música (MP3)", callback_data="download_audio")],
    ]
    
    # Adicionar botão para baixar arquivo genérico APENAS se for uma URL
    if re.match(r"https?://[^\s]+\.\S+", user_input):
        keyboard.append([InlineKeyboardButton("Baixar como Arquivo/APK", callback_data="download_file")])

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

    if download_type == "download_file":
        if not is_url:
            await send_progress_message(query.message, "Para baixar como arquivo, por favor, forneça um link direto.")
            return
        
        try:
            await send_progress_message(query.message, f"Baixando arquivo de: {original_user_input}...")
            response = requests.get(original_user_input, stream=True)
            response.raise_for_status() # Levanta um erro para códigos de status HTTP ruins

            # Tentar obter o nome do arquivo do cabeçalho Content-Disposition ou da URL
            filename = None
            if "Content-Disposition" in response.headers:
                fname_match = re.findall(r"filename=\"?([^\"]+)\"?", response.headers["Content-Disposition"])
                if fname_match: filename = fname_match[0]
            
            if not filename:
                filename = os.path.basename(original_user_input.split("?")[0])
                if not filename or len(filename.split(".")) < 2: # Se não tiver nome ou extensão, usar um padrão
                    filename = "downloaded_file.bin"

            file_path = os.path.join(DOWNLOAD_DIR, filename)

            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            await send_progress_message(query.message, "Download concluído, enviando...")
            
            with open(file_path, "rb") as document:
                await query.message.reply_document(document=document)
            
            os.remove(file_path)
            logger.info(f"Arquivo {file_path} enviado e removido com sucesso.")

        except Exception as e:
            logger.error(f"Erro ao baixar arquivo: {e}", exc_info=True)
            await send_progress_message(query.message, f"Ocorreu um erro ao baixar o arquivo: {e}")
        return # Finaliza a função para download de arquivo

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
                # CORREÇÃO: Apenas passa o termo de busca original para yt-dlp
                search_term = original_user_input
                
                await send_progress_message(query.message, f"Buscando por: {original_user_input}...")
                
                # yt-dlp é inteligente o suficiente para encontrar o melhor resultado e os postprocessors cuidam da extração de áudio
                search_results = ydl.extract_info(f"ytsearch1:{search_term}", download=False)
                
                if not search_results or "entries" not in search_results or not search_results["entries"]:
                    await send_progress_message(query.message, "Nenhum resultado encontrado para sua busca.")
                    return
                
                first_result = search_results["entries"][0]
                await send_progress_message(query.message, f"Encontrado: {first_result["title"]}. Baixando...")
                info = ydl.extract_info(first_result["webpage_url"], download=True)

            file_path = ydl.prepare_filename(info)
            
            # Ajustar o caminho do arquivo se for áudio e a extensão não for .mp3
            if download_type == "download_audio" and not file_path.endswith(".mp3"):
                # Verificar se o arquivo .mp3 foi criado pelo postprocessor
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

def download_progress_hook(d, message_object):
    if d["status"] == "finished":
        pass

def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    logger.info("Bot TM-Infinity iniciado...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
