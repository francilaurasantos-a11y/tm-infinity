import logging
import os
import re
import asyncio
import zipfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from yt_dlp import YoutubeDL
import requests

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = "8522636592:AAGGKm59cxMC5PYyjr3Dil1PZRG21C47a0g"
DIVULGACAO_TOKEN = "8362410901:AAGMZ24BVZNpv4ttJeRpZ1qLonoS9tORPUU"

DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

CATEGORIA_QUANTIDADE = 200
ZIP_PARTE_TAMANHO = 500
ZIP_TAMANHO_MAX_BYTES = int(1.8 * 1024 * 1024 * 1024)


def create_progress_bar(progress, bar_length=20):
    filled_length = int(bar_length * progress)
    bar = '\u2588' * filled_length + '\u2591' * (bar_length - filled_length)
    return "[{}] {:.1%}".format(bar, progress)


def notify_divulgacao(chat_id, file_id, song_name, file_size):
    try:
        requests.post(
            "http://localhost:3333/nova-musica",
            json={"chat_id": chat_id, "file_id": file_id, "song_name": song_name},
            timeout=10
        )
        logger.info("[DIVULGACAO] Notificado: {}".format(song_name))
    except Exception as e:
        logger.warning("[DIVULGACAO] Falha: {}".format(e))


def criar_zip(file_paths, zip_name):
    zip_path = os.path.join(DOWNLOAD_DIR, zip_name)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in file_paths:
            if os.path.exists(file_path):
                zipf.write(file_path, os.path.basename(file_path))
    return zip_path


def dividir_em_partes(file_paths):
    partes = []
    parte_atual = []
    tamanho_atual = 0
    for fp in file_paths:
        if not os.path.exists(fp):
            continue
        tamanho_arquivo = os.path.getsize(fp)
        excede_quantidade = len(parte_atual) >= ZIP_PARTE_TAMANHO
        excede_tamanho = (tamanho_atual + tamanho_arquivo) > ZIP_TAMANHO_MAX_BYTES
        if parte_atual and (excede_quantidade or excede_tamanho):
            partes.append(parte_atual)
            parte_atual = []
            tamanho_atual = 0
        parte_atual.append(fp)
        tamanho_atual += tamanho_arquivo
    if parte_atual:
        partes.append(parte_atual)
    return partes


async def enviar_zips_divididos(message, status_msg, downloaded_files, base_nome, titulo, erros, loop):
    partes = dividir_em_partes(downloaded_files)
    total_partes = len(partes)

    if total_partes == 0:
        await status_msg.edit_text("\u274c Nenhum arquivo valido para compactar.")
        return

    await status_msg.edit_text(
        "\U0001f4e6 {} ZIP(s) serao criados e enviados...\n\U0001f3b5 {} musicas no total".format(
            total_partes, len(downloaded_files)
        )
    )

    zips_criados = []

    for i, parte in enumerate(partes, start=1):
        if total_partes > 1:
            parte_label = "_parte{}de{}".format(i, total_partes)
        else:
            parte_label = ""
        zip_name = "{}{}.zip".format(base_nome, parte_label)

        try:
            await status_msg.edit_text(
                "\U0001f4e6 Compactando parte {}/{}...\n\U0001f3b5 {} musicas nesta parte".format(
                    i, total_partes, len(parte)
                )
            )
        except Exception:
            pass

        zip_path = await loop.run_in_executor(None, lambda p=parte, n=zip_name: criar_zip(p, n))
        zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
        zips_criados.append(zip_path)

        try:
            await status_msg.edit_text(
                "\U0001f4e4 Enviando ZIP {}/{} ({:.1f} MB)...".format(i, total_partes, zip_size_mb)
            )
        except Exception:
            pass

        if total_partes > 1:
            erros_txt = "\u26a0\ufe0f {} erros ignorados".format(erros) if (erros and i == total_partes) else ""
            caption = "\U0001f4e6 **{}** \u2014 Parte {} de {}\n\U0001f3b5 {} musicas\n{}".format(
                titulo, i, total_partes, len(parte), erros_txt
            )
        else:
            if erros:
                ok_txt = "\u26a0\ufe0f {} erros ignorados".format(erros)
            else:
                ok_txt = "\u2705 Todos os downloads OK"
            caption = "\U0001f4e6 **{} \u2014 Pacote Completo**\n\U0001f3b5 {} musicas\n{}".format(
                titulo, len(parte), ok_txt
            )

        zip_size_bytes = os.path.getsize(zip_path)
        zip_size_mb = zip_size_bytes / (1024 * 1024)

        if zip_size_bytes > 50 * 1024 * 1024:
            aviso = "ZIP {} ({:.1f} MB) maior que 50 MB. Telegram nao aceita. Reduza ZIP_PARTE_TAMANHO.".format(zip_name, zip_size_mb)
            await message.reply_text(aviso)
            zips_criados.append(zip_path)
            continue

        try:
            with open(zip_path, 'rb') as zf:
                await message.reply_document(
                    document=zf,
                    filename=zip_name,
                    caption=caption,
                    parse_mode='Markdown',
                    read_timeout=300,
                    write_timeout=300,
                    connect_timeout=60
                )
        except Exception as zip_err:
            logger.error("Erro ao enviar ZIP: {}".format(zip_err))
            await message.reply_text(
                "❌ Falha ao enviar {}: {}".format(zip_name, str(zip_err)[:100])
            )

    if total_partes > 1:
        erros_txt = "\u26a0\ufe0f {} erros ignorados".format(erros) if erros else ""
        await message.reply_text(
            "\u2705 **Concluido!**\n\U0001f4e6 {} ZIPs enviados\n\U0001f3b5 {} musicas no total\n{}".format(
                total_partes, len(downloaded_files), erros_txt
            ),
            parse_mode='Markdown'
        )

    try:
        await status_msg.delete()
    except Exception:
        pass

    for fp in downloaded_files:
        try:
            os.remove(fp)
            base = os.path.splitext(fp)[0]
            for ext in ['.jpg', '.webp', '.png', '.temp']:
                if os.path.exists(base + ext):
                    os.remove(base + ext)
        except Exception:
            pass

    for zp in zips_criados:
        try:
            os.remove(zp)
        except Exception:
            pass


async def start(update, context):
    await update.message.reply_text(
        "Ola! Eu sou o bot TM-Infinity. \U0001f3b5\U0001f3a5\U0001f3ac\n\n"
        "Envie-me o **nome da musica** ou um **link** para baixar!\n\n"
        "\u2705 **Suporte para:**\n"
        "- YouTube (Musica, Video e Playlists)\n"
        "- Instagram (Reels e Videos)\n"
        "- TikTok (Videos)\n\n"
        "\U0001f4e6 **Download em Massa por Categoria:**\n"
        "Use `/categoria <genero>` para baixar musicas e receber ZIPs automaticos!\n"
        "Exemplo: `/categoria funk`, `/categoria sertanejo`, `/categoria pagode`\n\n"
        "\U0001f500 ZIPs grandes sao divididos automaticamente em partes de 500 musicas.\n\n"
        "As musicas vem com a capa do album e nome correto!",
        parse_mode='Markdown'
    )


async def handle_user_input(update, context):
    user_input = update.message.text
    context.user_data["user_input"] = user_input

    is_social = any(x in user_input.lower() for x in ["instagram.com", "tiktok.com"])

    keyboard = []
    if is_social:
        keyboard.append([InlineKeyboardButton("Baixar Video", callback_data="download_video")])
    else:
        if "list=" in user_input.lower() or "playlist" in user_input.lower():
            keyboard.append([InlineKeyboardButton("Baixar Playlist (Audio)", callback_data="download_playlist_audio")])
            keyboard.append([InlineKeyboardButton("Baixar Playlist (Video)", callback_data="download_playlist_video")])
            keyboard.append([InlineKeyboardButton("\U0001f4e6 Baixar Playlist como ZIP", callback_data="download_playlist_zip")])
        else:
            keyboard.append([InlineKeyboardButton("Baixar como Musica (MP3)", callback_data="download_audio")])
            keyboard.append([InlineKeyboardButton("Baixar como Video (MP4)", callback_data="download_video")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("O que voce deseja baixar?", reply_markup=reply_markup)


async def button_callback_handler(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_input = context.user_data.get("user_input")

    if not user_input:
        await query.edit_message_text("Erro ao recuperar a solicitacao. Envie o nome ou link novamente.")
        return

    await query.edit_message_text("Iniciando processamento...")
    asyncio.create_task(run_download(query, user_input, data, context))


async def run_download(query, user_input, download_type, context):
    if download_type == "download_playlist_zip":
        await process_playlist_zip(query, user_input, context)
    elif download_type.startswith("download_playlist"):
        media_type = "download_audio" if "audio" in download_type else "download_video"
        await process_playlist(query, user_input, media_type, context)
    else:
        await process_single_item(query, user_input, download_type, context)


async def cmd_categoria(update, context):
    if not context.args:
        await update.message.reply_text(
            "\u274c Informe o genero musical!\n\n"
            "Exemplo: `/categoria funk`\n"
            "Outros: sertanejo, pagode, rap, forro, rock, pop, gospel",
            parse_mode='Markdown'
        )
        return

    categoria = " ".join(context.args)
    await update.message.reply_text(
        "\U0001f3b6 Iniciando download em massa de **{}**...\n"
        "\U0001f3b5 Quantidade: {} musicas\n"
        "\U0001f4e6 ZIPs de ate {} musicas cada\n\n"
        "\u23f3 Isso pode levar bastante tempo - aguarde as partes chegando!".format(
            categoria.upper(), CATEGORIA_QUANTIDADE, ZIP_PARTE_TAMANHO
        ),
        parse_mode='Markdown'
    )
    asyncio.create_task(process_categoria_zip(update, categoria, context))


async def process_categoria_zip(update, categoria, context):
    loop = asyncio.get_running_loop()
    status_msg = await update.message.reply_text("\U0001f50d Buscando musicas de '{}'...".format(categoria))

    search_query = "ytsearch{}:{}".format(CATEGORIA_QUANTIDADE, categoria)
    ydl_search_opts = {"quiet": True, "extract_flat": True}

    try:
        with YoutubeDL(ydl_search_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(search_query, download=False))

        entries = info.get('entries', [])
        if not entries:
            await status_msg.edit_text("\u274c Nenhum resultado encontrado para essa categoria.")
            return

        total = len(entries)
        await status_msg.edit_text("\u2705 Encontradas {} musicas. Baixando... {}".format(total, create_progress_bar(0)))

        downloaded_files = []
        erros = 0

        for i, entry in enumerate(entries):
            if not entry:
                continue
            url = entry.get('url') or entry.get('webpage_url')
            if not url and entry.get('id'):
                url = "https://www.youtube.com/watch?v={}".format(entry.get('id'))
            if not url:
                continue

            try:
                await status_msg.edit_text(
                    "\u2b07\ufe0f Baixando {}/{}...\n{}\n\U0001f3b5 {}".format(
                        i + 1, total,
                        create_progress_bar((i + 1) / total),
                        str(entry.get('title', 'Desconhecido'))[:50]
                    )
                )
            except Exception:
                pass

            file_path = await download_audio_file(url, loop)
            if file_path:
                downloaded_files.append(file_path)
            else:
                erros += 1

        if not downloaded_files:
            await status_msg.edit_text("\u274c Nenhum arquivo foi baixado com sucesso.")
            return

        base_nome = categoria.replace(' ', '_')
        await enviar_zips_divididos(
            message=update.message,
            status_msg=status_msg,
            downloaded_files=downloaded_files,
            base_nome=base_nome,
            titulo=categoria.upper(),
            erros=erros,
            loop=loop
        )

    except Exception as e:
        logger.error("Erro no download por categoria: {}".format(e))
        await status_msg.edit_text("\u274c Erro ao processar categoria: {}".format(str(e)[:150]))


async def download_audio_file(url, loop):
    ydl_opts = {
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
        "retries": 5,
        "socket_timeout": 30,
        "ignoreerrors": True,
        "format": "bestaudio/best",
        "writethumbnail": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
            {"key": "EmbedThumbnail"},
            {"key": "FFmpegMetadata"}
        ],
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            if not info:
                return None
            if 'entries' in info:
                if not info['entries']:
                    return None
                info = info['entries'][0]
            file_path = ydl.prepare_filename(info)
            base, _ = os.path.splitext(file_path)
            mp3_path = base + ".mp3"
            if os.path.exists(mp3_path):
                return mp3_path
            for ext in ['.mp3', '.m4a', '.webm', '.opus']:
                if os.path.exists(base + ext):
                    return base + ext
        return None
    except Exception as e:
        logger.warning("Erro ao baixar {}: {}".format(url, e))
        return None


async def process_playlist_zip(query, playlist_url, context):
    loop = asyncio.get_running_loop()
    status_msg = await query.message.reply_text("\U0001f4cb Extraindo itens da playlist...")

    ydl_opts = {"quiet": True, "extract_flat": True}
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(playlist_url, download=False))

        entries = info.get('entries', [])
        if not entries:
            await status_msg.edit_text("\u274c Nao foi possivel encontrar itens nesta playlist.")
            return

        total = len(entries)
        playlist_title = info.get('title', 'playlist')
        await status_msg.edit_text("\u2705 {} musicas encontradas. Baixando...".format(total))

        downloaded_files = []
        erros = 0

        for i, entry in enumerate(entries):
            if not entry:
                continue
            url = entry.get('url') or entry.get('webpage_url')
            if not url and entry.get('id'):
                url = "https://www.youtube.com/watch?v={}".format(entry.get('id'))
            if not url:
                continue

            try:
                await status_msg.edit_text(
                    "\u2b07\ufe0f Baixando {}/{}...\n{}\n\U0001f3b5 {}".format(
                        i + 1, total,
                        create_progress_bar((i + 1) / total),
                        str(entry.get('title', ''))[:50]
                    )
                )
            except Exception:
                pass

            file_path = await download_audio_file(url, loop)
            if file_path:
                downloaded_files.append(file_path)
            else:
                erros += 1

        if not downloaded_files:
            await status_msg.edit_text("\u274c Nenhum arquivo foi baixado com sucesso.")
            return

        base_nome = re.sub(r'[^a-zA-Z0-9_]', '_', playlist_title)[:40]
        await enviar_zips_divididos(
            message=query.message,
            status_msg=status_msg,
            downloaded_files=downloaded_files,
            base_nome=base_nome,
            titulo=playlist_title,
            erros=erros,
            loop=loop
        )

    except Exception as e:
        logger.error("Erro na playlist ZIP: {}".format(e))
        await status_msg.edit_text("\u274c Erro ao processar playlist: {}".format(str(e)[:150]))


async def process_playlist(query, playlist_url, media_type, context):
    initial_msg = await query.message.reply_text("Extraindo itens da playlist...")
    ydl_opts = {"quiet": True, "extract_flat": True}
    try:
        loop = asyncio.get_running_loop()
        with YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(playlist_url, download=False))

        entries = info.get('entries', [])
        if not entries:
            await initial_msg.edit_text("Nao foi possivel encontrar itens nesta playlist.")
            return

        total = len(entries)
        await initial_msg.edit_text("Encontrados {} itens. Iniciando downloads...".format(total))

        for i, entry in enumerate(entries):
            if entry:
                url = entry.get('url') or entry.get('webpage_url')
                if not url and entry.get('id'):
                    url = "https://www.youtube.com/watch?v={}".format(entry.get('id'))
                if url:
                    await process_single_item(query, url, media_type, context, is_playlist=True, index=i+1, total=total)

        await query.message.reply_text("\u2705 Download da playlist finalizado!")
    except Exception as e:
        logger.error("Erro na playlist: {}".format(e))
        await initial_msg.edit_text("Erro ao processar playlist: {}...".format(str(e)[:100]))


async def process_single_item(query, input_data, download_type, context, is_playlist=False, index=0, total=0):
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

    search_query = input_data if is_url else "ytsearch1:{}".format(input_data)

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
            info_dict = await loop.run_in_executor(None, lambda: ydl.extract_info(search_query, download=False))
            if not info_dict:
                raise Exception("Nenhum resultado encontrado.")
            if 'entries' in info_dict:
                if not info_dict['entries']:
                    raise Exception("Busca nao retornou resultados.")
                info = info_dict['entries'][0]
            else:
                info = info_dict

            dl_url = info['webpage_url'] if 'webpage_url' in info else search_query
            await loop.run_in_executor(None, lambda: ydl.download([dl_url]))

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
                if is_playlist:
                    caption = "\U0001f4e6 Item {}/{}\n\U0001f3b5 {}".format(index, total, title)
                else:
                    caption = "\u2705 Aqui esta: {}".format(title)

                with open(file_path, "rb") as f:
                    if download_type == "download_audio" and file_path.endswith(".mp3"):
                        sent = await query.message.reply_audio(audio=f, title=title, caption=caption)
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
                        if os.path.exists(base_path + ext):
                            os.remove(base_path + ext)
                except Exception:
                    pass
            else:
                if not is_playlist:
                    await query.message.reply_text("Erro: O arquivo nao foi gerado corretamente.")

    except Exception as e:
        logger.error("Erro no item: {}".format(e))
        if not is_playlist:
            await query.message.reply_text("Desculpe, ocorreu um erro: {}".format(str(e)[:100]))


def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("categoria", cmd_categoria))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    logger.info("Bot TM-Infinity iniciado...")
    application.run_polling()


if __name__ == "__main__":
    main()

