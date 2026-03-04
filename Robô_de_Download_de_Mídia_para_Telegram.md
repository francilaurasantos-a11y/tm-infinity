# Robô de Download de Mídia para Telegram

Este robô do Telegram permite baixar vídeos e músicas de diversas plataformas (YouTube, Instagram, TikTok, SoundCloud, Spotify, etc.) usando um link direto ou pesquisando pelo nome. Ele é projetado para ser executado em ambientes como BedHosting e Termux.

## Funcionalidades

- Download de vídeos por URL.
- Download de músicas por URL.
- Busca e download de vídeos por nome.
- Busca e download de músicas por nome (extrai o áudio).
- Suporte a diversas plataformas via `yt-dlp`.

## Pré-requisitos

- Uma conta no Telegram e um bot token (já configurado no `bot.py`).
- Python 3.8 ou superior.
- `pip` para instalação de pacotes Python.
- `ffmpeg` para processamento de áudio/vídeo (necessário para extrair áudio).

## Instalação e Configuração

O token do seu bot já foi configurado diretamente no arquivo `bot.py`. Não é necessário definir a variável de ambiente `TELEGRAM_BOT_TOKEN` a menos que você queira sobrescrever o token hardcoded (não recomendado para este setup).

### 1. Preparação dos Arquivos para o GitHub

Certifique-se de ter os seguintes arquivos no mesmo diretório localmente:
- `bot.py` (o código principal do bot)
- `requirements.txt` (dependências Python)
- `setup.sh` (o script de instalação universal)
- `README.md` (este arquivo)
- `.gitignore` (para ignorar arquivos desnecessários)

### 2. Publicar no GitHub

1. **Crie um novo repositório no GitHub**: Acesse [github.com](https://github.com/), faça login e clique em "New repository". Dê um nome (ex: `telegram-media-downloader-bot`), uma descrição e escolha se será público ou privado. Não inicialize com README, .gitignore ou licença, pois você já tem esses arquivos.
2. **Inicialize o repositório localmente e faça o primeiro commit**:
   Abra o terminal no diretório onde estão seus arquivos e execute:
   ```bash
   git init
   git add .
   git commit -m "Primeiro commit do bot de download de mídia"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git # Substitua SEU_USUARIO e SEU_REPOSITORIO
   git push -u origin main
   ```
   Se você já tem um repositório, apenas adicione os arquivos e faça `git push`.

### 3. Instalação Automática (via GitHub)

Este script `setup.sh` detectará automaticamente se você está no Termux (Android) ou em um servidor Linux (BedHosting - Ubuntu/Debian) e instalará todas as dependências necessárias, além de configurar o bot para rodar.

#### No BedHosting (Servidor Linux - Ubuntu/Debian)

1. Conecte-se ao seu servidor via SSH.
2. Clone o seu repositório do GitHub:
   ```bash
   git clone https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
   cd SEU_REPOSITORIO # Navegue para o diretório do bot
   ```
3. Dê permissão de execução ao script de instalação:
   ```bash
   chmod +x setup.sh
   ```
4. Execute o script de instalação:
   ```bash
   ./setup.sh
   ```
   Este script irá:
   - Atualizar os pacotes do sistema.
   - Instalar Python, pip, ffmpeg e git.
   - Instalar as dependências Python do `requirements.txt`.
   - Configurar e iniciar o bot como um serviço `systemd`, garantindo que ele rode em segundo plano e reinicie automaticamente em caso de falha.

   Para verificar o status do bot, use:
   ```bash
   sudo systemctl status telegram_downloader
   ```
   Para ver os logs:
   ```bash
   journalctl -u telegram_downloader -f
   ```

#### No Termux (Android)

1. Instale o Termux na Play Store ou F-Droid.
2. Abra o Termux.
3. Clone o seu repositório do GitHub:
   ```bash
   git clone https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
   cd SEU_REPOSITORIO # Navegue para o diretório do bot
   ```
4. Dê permissão de execução ao script de instalação:
   ```bash
   chmod +x setup.sh
   ```
5. Execute o script de instalação:
   ```bash
   ./setup.sh
   ```
   Este script irá:
   - Atualizar os pacotes do sistema Termux.
   - Instalar Python, ffmpeg e git.
   - Instalar as dependências Python do `requirements.txt`.

   Após a instalação, para iniciar o bot, execute:
   ```bash
   python bot.py
   ```
   Para rodar o bot em segundo plano e mantê-lo ativo mesmo se você fechar o Termux, use `tmux`:
   ```bash
   tmux new -s bot_session
   python bot.py
   # Pressione Ctrl+b e depois d para sair da sessão tmux
   ```
   Para reentrar na sessão:
   ```bash
   tmux attach -t bot_session
   ```

## Uso

Após iniciar o bot, envie um link de vídeo/música ou o nome do conteúdo que deseja baixar para o bot no Telegram. Ele processará a solicitação e enviará o arquivo de volta para você.

**Exemplos:**
- `https://www.youtube.com/watch?v=dQw4w9WgXcQ` (para baixar um vídeo)
- `música despacito` (para buscar e baixar a música em MP3)
- `vídeo gatos engraçados` (para buscar e baixar um vídeo)

## Observações

- O bot utiliza `yt-dlp` para os downloads, que suporta uma vasta gama de sites. No entanto, a funcionalidade de busca por nome pode ser mais eficaz para plataformas como YouTube.
- O download de músicas por nome tentará extrair o áudio e convertê-lo para MP3.
- O tamanho máximo de arquivo que o Telegram permite enviar é de 2 GB. Arquivos maiores podem falhar.

## Licença

Este projeto está sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes. (Se aplicável)
