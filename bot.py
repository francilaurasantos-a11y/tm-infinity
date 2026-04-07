import logging
import os
import re
import asyncio
import zipfile
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

# --- CONFIGURA\u00c7\u00d5ES ---
TOKEN = "8522636592:AAGGKm59cxMC5PYyjr3Dil1PZRG21C47a0g"

# Token do bot de divulga\u00e7\u00e3o (Node.js) \u2014 notificado automaticamente ap\u00f3s cada MP3
DIVULGACAO_TOKEN = "8362410901:AAGMZ24BVZNpv4ttJeRpZ1qLonoS9tORPUU"

# Diret\u00f3rio de downloads
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Quantidade de m\u00fasicas no download em massa por categoria
CATEGORIA_QUANTIDADE = 1000

# Limite de m\u00fasicas por ZIP (evita ultrapassar 2 GB do Telegram)
ZIP_PARTE_TAMANHO = 500

# Limite de tamanho por ZIP em bytes (1.8 GB = margem segura abaixo do limite do Telegram)
ZIP_TAMANHO_MAX_BYTES = int(1.8 * 1024 * 1024 * 1024)


# --- Fun\u00e7\u00f5es Auxiliares ---

def create_progress_bar(progress: float, bar_length: int = 20) -> str:
    filled_length = int(bar_length * progress)
    bar = '\u2588' * filled_length + '\u2591' * (bar_length - filled_length)
    return f"[{bar}] {progress:.1%}"


def notify_divulgacao(chat_id: int, file_id: str, song_name: str, file_size: int):
    """Avisa o bot de divulga\u00e7\u00e3o via webhook local (porta 3333)."""
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
        logger.info(f"[DIVULGA\u00c7\u00c3O] Notificado via webhook: {song_name}")
    except Exception as e:
        logger.warning(f"[DIVULGA\u00c7\u00c3O] Falha ao notificar: {e}")


def criar_zip(file_paths: list, zip_name: str) -> str:
    """Cria um arquivo ZIP com os arquivos fornecidos e retorna o caminho do ZIP."""
    zip_path = os.path.join(DOWNLOAD_DIR, zip_name)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in file_paths:
            if os.path.exists(file_path):
                zipf.write(file_path, os.path.basename(file_path))
    return zip_path


def dividir_em_partes(file_paths: list) -> list:
    """
    Divide a lista de arquivos em sublistas respeitando:
    - M\u00e1ximo de ZIP_PARTE_TAMANHO m\u00fasicas por parte
    - Tamanho acumulado n\u00e3o ultrapassa ZIP_TAMANHO_MAX_BYTES
    """
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
    """
    Divide os arquivos em partes, cria um ZIP por parte e envia cada um.
    Cuida da limpeza de todos os arquivos ao final.
    """
    partes = dividir_em_partes(downloaded_files)
    total_partes = len(partes)

    if total_partes == 0:
        await status_msg.edit_text("\u274c Nenhum arquivo v\u00e1lido para compactar.")
        return

    await status_msg.edit_text(
        f"\ud83d\udce6 {total_partes} ZIP(s) ser\u00e3o criados e enviados...\n"
        f"\ud83c\udfb5 {len(downloaded_files)} m\u00fasicas no total"
    )

    zips_criados = []

    for i, parte in enumerate(partes, start=1):
        parte_label = f"_parte{i}de{total_partes}" if total_partes > 1 else ""
        zip_name = f"{base_nome}{parte_label}.zip"

        try:
            await status_msg.edit_text(
                f"\ud83d\udce6 Compactando parte {i}/{total_partes}...\n"
                f"\ud83c\udfb5 {len(parte)} m\u00fasicas nesta parte"
            )
        except Exception:
            pass

        zip_path = await loop.run_in_executor(None, lambda p=parte, n=zip_name: criar_zip(p, n))
        zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
        zips_criados.append(zip_path)

        try:
            await status_msg.edit_text(
                f"\ud83d\udce4 Enviando ZIP {i}/{total_partes} ({zip_size_mb:.1f} MB)..."
            )
        except Exception:
            pass

        if total_partes > 1:
            caption = (
                f"\ud83d\udce6 **{titulo}** \u2014 Parte {i} de {total_partes}\n"
                f"\ud83c\udfb5 {len(parte)} m\u00fasicas\n"
                f"{'\u26a0\ufe0f ' + str(erros) + ' erros ignorados' if (erros and i == total_partes) else ''}"
            )
        else:
            caption = (
                f"\ud83d\udce6 **{titulo} \u2014 Pacote Completo**\n"
                f"\ud83c\udfb5 {len(parte)} m\u00fasicas\n"
                f"{'\u26a0\ufe0f ' + str(erros) + ' erros ignorados' if erros else '\u2705 Todos os downloads OK'}"
            )

        with open(zip_path, 'rb') as zf:
            await message.reply_document(
                document=zf,
                filename=zip_name,
                caption=caption,
                parse_mode='Markdown'
            )

    if total_partes > 1:
        await message.reply_text(
            f"\u2705 **Conclu\u00eddo!**\n"
            f"\ud83d\udce6 {total_partes} ZIPs enviados\n"
            f"\ud83c\udfb5 {len(downloaded_files)} m\u00fasicas no total\n"
            f"{'\u26a0\ufe0f ' + str(erros) + ' erros ignorados' if erros else ''}",
            parse_mode='Markdown'
        )

    try:
        await status_msg.delete()
    except Exception:
        pass

    # Limpeza de MP3s
    for fp in downloaded_files:
        try:
            os.remove(fp)
            base = os.path.splitext(fp)[0]
            for ext in ['.jpg', '.webp', '.png', '.temp']:
                if os.path.exists(base + ext):
                    os.remove(base + ext)
        except Exception:
            pass

    # Limpeza dos ZIPs
    for zp in zips_criados:
        try:
            os.remove(zp)
        except Exception:
            pass


# --- Handlers do Telegram ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Ol\u00e1! Eu sou o bot TM-Infinity. \ud83c\udfb5\ud83c\udfa5\ud83c\udfac\n\n"
        "Envie-me o **nome da m\u00fasica** ou um **link** para baixar!\n\n"
        "\u2705 **Suporte para:**\n"
        "- YouTube (M\u00fasica, V\u00eddeo e Playlists)\n"
        "- Instagram (Reels e V\u00eddeos)\n"
        "- TikTok (V\u00eddeos)\n\n"
        "\ud83d\udce6 **Download em Massa por Categoria:**\n"
        "Use `/categoria <g\u00eanero>` para baixar m\u00fasicas e receber ZIPs autom\u00e1ticos!\n"
        "Exemplo: `/categoria funk`, `/categoria sertanejo`, `/categoria pagode`\n\n"
        "\ud83d\udd00 ZIPs grandes s\u00e3o divididos automaticamente em partes de 500 m\u00fasicas.\n\n"
        "As m\u00fasicas v\u00eam com a capa do \u00e1lbum e nome correto!",
        parse_mode='Markdown'
    )


async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_input = update.message.text
    context.user_data["user_input"] = user_input

    is_social = any(x in user_input.lower() for x in ["instagram.com", "tiktok.com"])

    keyboard = []
    if is_social:
        keyboard.append([InlineKeyboardButton("Baixar V\u00eddeo", callback_data="download_video")])
    else:
        if "list=" in user_input.lower() or "playlist" in user_input.lower():
            keyboard.append([InlineKeyboardButton("Baixar Playlist (\u00c1udio)", callback_data="download_playlist_audio")])
            keyboard.append([InlineKeyboardButton("Baixar Playlist (V\u00eddeo)", callback_data="download_playlist_video")])
            keyboard.append([InlineKeyboardButton("\ud83d\udce6 Baixar Playlist como ZIP", callback_data="download_playlist_zip")])
        else:
            keyboard.append([InlineKeyboardButton("Baixar como M\u00fasica (MP3)", callback_data="download_audio")])
            keyboard.append([InlineKeyboardButton("Baixar como V\u00eddeo (MP4)", callback_data="download_video")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("O que voc\u00ea deseja baixar?", reply_markup=reply_markup)


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_input = context.user_data.get("user_input")

    if not user_input:
        await query.edit_message_text("Erro ao recuperar a solicita\u00e7\u00e3o. Envie o nome ou link novamente.")
        return

    await query.edit_message_text("Iniciando processamento...")
    asyncio.create_task(run_download(query, user_input, data, context))


# --- L\u00f3gica de Download ---

async def run_download(query, user_input, download_type, context):
    if download_type == "download_playlist_zip":
        await process_playlist_zip(query, user_input, context)
    elif download_type.startswith("download_playlist"):
        media_type = "download_audio" if "audio" in download_type else "download_video"
        await process_playlist(query, user_input, media_type, context)
    else:
        await process_single_item(query, user_input, download_type, context)


# --- Download em Massa por Categoria ---

async def cmd_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /categoria <g\u00eanero> \u2014 baixa m\u00fasicas da categoria e envia ZIPs divididos."""
    if not context.args:
        await update.message.reply_text(
            "\u274c Informe o g\u00eanero musical!\n\n"
            "Exemplo: `/categoria funk`\n"
            "Outros: sertanejo, pagode, rap, forr\u00f3, rock, pop, gospel",
            parse_mode='Markdown'
        )
        return

    categoria = " ".join(context.args)
    await update.message.reply_text(
        f"\ud83c\udfb6 Iniciando download em massa de **{categoria.upper()}**...\n"
        f"\ud83c\udfb5 Quantidade: {CATEGORIA_QUANTIDADE} m\u00fasicas\n"
        f"\ud83d\udce6 ZIPs de at\u00e9 {ZIP_PARTE_TAMANHO} m\u00fasicas cada\n\n"
        f"\u23f3 Isso pode levar bastante tempo \u2014 aguarde as partes chegando!",
        parse_mode='Markdown'
    )
    asyncio.create_task(process_categoria_zip(update, categoria, context))


async def process_categoria_zip(update: Update, categoria: str, context: ContextTypes.DEFAULT_TYPE):
    """Busca m\u00fasicas de uma categoria no YouTube, baixa e envia em ZIPs divididos."""
    loop = asyncio.get_running_loop()
    status_msg = await update.message.reply_text(f"\ud83d\udd0d Buscando m\u00fasicas de '{categoria}'...")

    search_query = f"ytsearch{CATEGORIA_QUANTIDADE}:{categoria}"
    ydl_search_opts
