import logging
import os
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from yt_dlp import YoutubeDL

# Configurar logging (CORRIGIDO: sem barras invertidas)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Token do bot (configurado pelo usuário)
TOKEN = "8522636592:AAGGKm59cxMC5PYyjr3Dil1PZRG21C47a0g"

# Diretório para downloads temporários (CORRIGIDO: pasta local para evitar erro de permissão)
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Função para iniciar o bot
async def start(update: Update, context) -> None:
    await update.message.reply_text("Olá! Eu sou o bot TM-Infinity. Envie-me um link de vídeo/música ou o nome para baixar.")

# Função auxiliar para enviar mensagens de progresso
async def send_progress_message(update: Update, text: str):
    await update.message.reply_text(text)

# Função para baixar mídia
async def download_media(update: Update, context) -> None:
    user_input = update.message.text
    chat_id = update.message.chat_id

    await send_progress_message(update, f"Recebido: {user_input}. Processando...")

    is_url = re.match(r"https?://[^\s]+\.\S+", user_input)

    # Configurações do yt-dlp (CORRIGIDO: outtmpl usando pasta local)
    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
        "noplaylist": True,
        "progress_hooks": [lambda d: download_progress_hook(d, update)],
        "restrictfilenames": True,
        "merge_output_format": "mp4",
    }

    # Se for busca por música (contém a palavra music ou música), extrair áudio
    if not is_url and ("music" in user_input.lower() or "música" in user_input.lower()):
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    try:
        with YoutubeDL(ydl_opts) as ydl:
            if is_url:
                info = ydl.extract_info(user_input, download=True)
            else:
                # Pesquisar pelo nome e baixar o primeiro resultado
                await send_progress_message(update, f"Buscando por: {user_input}...")
                search_query = f"ytsearch1:{user_input}"
                search_results = ydl.extract_info(search_query, download=False)
                
                if not search_results or "entries" not in search_results or not search_results["entries"]:
                    await send_progress_message(update, "Nenhum resultado encontrado para sua busca.")
                    return
                
                # Pega o primeiro resultado da busca
                first_result = search_results["entries"][0]
                await send_progress_message(update, f"Encontrado: {first_result['title']}. Baixando...")
                info = ydl.extract_info(first_result["webpage_url"], download=True)

            # Preparar o caminho do arquivo final
            file_path = ydl.prepare_filename(info)
            
            # Se foi convertido para mp3, o yt-dlp muda a extensão no disco mas não necessariamente no info
            if not file_path.endswith(".mp3") and os.path.exists(file_path.rsplit(".", 1)[0] + ".mp3"):
                file_path = file_path.rsplit(".", 1)[0] + ".mp3"

            await send_progress_message(update, "Download concluído, enviando...")
            
            # Enviar o arquivo para o Telegram
            with open(file_path, "rb") as document:
                await update.message.reply_document(document=document)
            
            # Remover o arquivo após o envio para economizar espaço
            os.remove(file_path)
            logger.info(f"Arquivo {file_path} enviado e removido com sucesso.")

    except Exception as e:
        logger.error(f"Erro ao baixar mídia: {e}", exc_info=True)
        await send_progress_message(update, f"Ocorreu um erro ao baixar a mídia: {e}")

def download_progress_hook(d, update: Update):
    if d["status"] == "finished":
        # logger.info("Download concluído no disco.")
        pass

def main() -> None:
    # Iniciar a aplicação do bot
    application = Application.builder().token(TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_media))

    # Rodar o bot
    logger.info("Bot TM-Infinity iniciado...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
