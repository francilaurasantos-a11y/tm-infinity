#!/bin/bash

# Script de instalação universal para o bot de download de mídia do Telegram
# Compatível com Termux (Android) e BedHosting (Ubuntu/Debian)

# Função para detectar o ambiente
detect_environment() {
    if [ -d "/data/data/com.termux" ]; then
        echo "termux"
    elif [ -f "/etc/os-release" ]; then
        . /etc/os-release
        if [[ "$ID" == "ubuntu" || "$ID" == "debian" ]]; then
            echo "linux_debian"
        else
            echo "unknown_linux"
        fi
    else
        echo "unknown"
    fi
}

ENVIRONMENT=$(detect_environment)

echo "Ambiente detectado: $ENVIRONMENT"

# Instalar dependências do sistema
if [ "$ENVIRONMENT" == "termux" ]; then
    echo "Instalando dependências para Termux..."
    pkg update && pkg upgrade -y
    pkg install python ffmpeg git -y
elif [ "$ENVIRONMENT" == "linux_debian" ]; then
    echo "Instalando dependências para BedHosting (Ubuntu/Debian)..."
    sudo apt update && sudo apt upgrade -y
    sudo apt install -y python3 python3-pip ffmpeg git
else
    echo "Ambiente não suportado ou não detectado. Por favor, instale Python, pip, ffmpeg e git manualmente."
    exit 1
fi

# Instalar dependências Python
echo "Instalando dependências Python..."
if [ "$ENVIRONMENT" == "termux" ]; then
    pip install -r requirements.txt
elif [ "$ENVIRONMENT" == "linux_debian" ]; then
    pip3 install -r requirements.txt
fi

# Configurar e iniciar o bot
if [ "$ENVIRONMENT" == "termux" ]; then
    echo "Instalação para Termux concluída!"
    echo "Para iniciar o bot, execute: python bot.py"
    echo "Para rodar em segundo plano, use tmux:"
    echo "  tmux new -s bot_session"
    echo "  python bot.py"
    echo "  (Pressione Ctrl+b e depois d para sair da sessão tmux)"
    echo "Para reentrar na sessão: tmux attach -t bot_session"
elif [ "$ENVIRONMENT" == "linux_debian" ]; then
    echo "Configurando o serviço systemd para o bot..."

    SERVICE_FILE="/etc/systemd/system/telegram_downloader.service"
    BOT_DIR=$(pwd)

    sudo bash -c "cat > $SERVICE_FILE <<EOF
[Unit]
Description=Telegram Media Downloader Bot
After=network.target

[Service]
User=$(whoami)
WorkingDirectory=$BOT_DIR
ExecStart=/usr/bin/python3 $BOT_DIR/bot.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF"

    sudo systemctl daemon-reload
    sudo systemctl start telegram_downloader
    sudo systemctl enable telegram_downloader

    echo "Verificando o status do serviço..."
    sudo systemctl status telegram_downloader

    echo "Instalação para BedHosting concluída! O bot deve estar rodando em segundo plano."
    echo "Para verificar os logs, use: journalctl -u telegram_downloader -f"
fi

echo "Processo de instalação finalizado."
