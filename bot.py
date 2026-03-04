import logging
import os
import re
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
# Agora aceita um objeto message diretamente para maior flexibilidade
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
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("O que você gostaria de baixar?", reply_markup=reply_markup)

# Função para lidar com a escolha do botão (callback)
async def button_callback_handler(update: Update, context) -> None:
    query = update.callback_query
    await query.answer() # Responder ao callback para remover o estado de 'carregando' do botão

    user_input = context.user_data.get("user_input")
    original_message = context.user_data.get("original_message")

    if not user_input or not original_message:
        await query.edit_message_text("Desculpe, não consegui recuperar sua última solicitação. Por favor, envie novamente.")
        return

    download_as_audio = query.data == "download_audio"

    # Usar query.message para responder ao usuário após a escolha do botão
    await query.edit_message_text(f"Recebido: {user_input}. Processando como {"Música" if download_as_audio else "Vídeo"}...")

    is_url = re.match(r"https?://[^\s]+\.\S+", user_input)

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
        "noplaylist": True,
        "progress_hooks": [lambda d: download_progress_hook(d, query.message)], # Passar query.message
        "restrictfilenames": True,
        "merge_output_format": "mp4",
    }

    if download_as_audio:
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
        if not is_url:
            user_input = f"ytsearch1:{user_input} audio"

    try:
        with YoutubeDL(ydl_opts) as ydl:
            if is_url:
                info = ydl.extract_info(user_input, download=True)
            else:
                await send_progress_message(query.message, f"Buscando por: {user_input}...")
                search_query = f"ytsearch1:{user_input}"
                search_results = ydl.extract_info(search_query, download=False)
                
                if not search_results or "entries" not in search_results or not search_results["entries"]:
                    await send_progress_message(query.message, "Nenhum resultado encontrado para sua busca.")
                    return
                
                first_result = search_results["entries"][0]
                await send_progress_message(query.message, f"Encontrado: {first_result["title"]}. Baixando...")
                info = ydl.extract_info(first_result["webpage_url"], download=True)

            file_path = ydl.prepare_filename(info)
            
            if download_as_audio and not file_path.endswith(".mp3") and os.path.exists(file_path.rsplit(".", 1)[0] + ".mp3"):
                file_path = file_path.rsplit(".", 1)[0] + ".mp3"

            await send_progress_message(query.message, "Download concluído, enviando...")
            
            with open(file_path, "rb") as document:
                await query.message.reply_document(document=document) # Usar query.message para enviar o documento
            
            os.remove(file_path)
            logger.info(f"Arquivo {file_path} enviado e removido com sucesso.")

    except Exception as e:
        logger.error(f"Erro ao baixar mídia: {e}", exc_info=True)
        await send_progress_message(query.message, f"Ocorreu um erro ao baixar a mídia: {e}")

# A função download_progress_hook agora recebe o objeto message correto
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
