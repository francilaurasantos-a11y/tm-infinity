
import logging
import os
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from yt_dlp import YoutubeDL

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Token do bot (substituído pelo token fornecido pelo usuário)
TOKEN = '8522636592:AAGGKm59cxMC5PYyjr3Dil1PZRG21C47a0g'

# Função para iniciar o bot
async def start(update: Update, context) -> None:
    await update.message.reply_text('Olá! Eu sou um bot de download de mídia. Envie-me um link de vídeo/música ou o nome para baixar.')

# Função auxiliar para enviar mensagens de progresso
async def send_progress_message(update: Update, text: str):
    await update.message.reply_text(text)

# Função para baixar mídia
async def download_media(update: Update, context) -> None:
    user_input = update.message.text
    chat_id = update.message.chat_id

    await send_progress_message(update, f'Recebido: {user_input}. Processando...')

    is_url = re.match(r'https?://[^\s]+\.\S+', user_input)

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': f'/tmp/%(title)s.%(ext)s',
        'noplaylist': True,
        'progress_hooks': [lambda d: download_progress_hook(d, update)],
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }] if not is_url and 'music' in user_input.lower() else [], # Extrair áudio se for busca por música
        'restrictfilenames': True,
        'merge_output_format': 'mp4',
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            if is_url:
                info = ydl.extract_info(user_input, download=True)
            else:
                # Pesquisar pelo nome e baixar o primeiro resultado
                await send_progress_message(update, f'Buscando por: {user_input}...')
                search_results = ydl.extract_info(f'ytsearch1:{user_input}' if 'youtube' in user_input.lower() else f'ytsearch1:{user_input}' , download=False)
                if not search_results or 'entries' not in search_results or not search_results['entries']:
                    await send_progress_message(update, 'Nenhum resultado encontrado para sua busca.')
                    return
                
                # Pega o primeiro resultado da busca
                first_result = search_results['entries'][0]
                await send_progress_message(update, f'Encontrado: {first_result['title']}. Baixando...')
                info = ydl.extract_info(first_result['webpage_url'], download=True)

            file_path = ydl.prepare_filename(info)
            
            # Renomear para mp3 se for áudio
            if not is_url and 'music' in user_input.lower() and not file_path.endswith('.mp3'):
                new_file_path = os.path.splitext(file_path)[0] + '.mp3'
                os.rename(file_path, new_file_path)
                file_path = new_file_path

            await send_progress_message(update, 'Download concluído, enviando...')
            await update.message.reply_document(document=open(file_path, 'rb'))
            os.remove(file_path) # Remover o arquivo após o envio
            logger.info(f'Arquivo {file_path} enviado e removido.')

    except Exception as e:
        logger.error(f'Erro ao baixar mídia: {e}', exc_info=True)
        await send_progress_message(update, f'Ocorreu um erro ao baixar a mídia: {e}')

def download_progress_hook(d, update: Update):
    if d['status'] == 'downloading':
        # Isso pode ser muito verboso, considere atualizar a cada X% ou a cada Y segundos
        # update.message.reply_text(f"Baixando: {d['_percent_str']} de {d['_total_bytes_str']} em {d['_speed_str']}")
        pass
    elif d['status'] == 'finished':
        # update.message.reply_text("Download concluído, enviando...")
        pass

def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_media))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
