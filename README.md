<div align="center">

<img src="resources/icon.png" width="120" alt="Universal Converter">

# Universal Converter

**Conversor de áudio e vídeo em lote — com prioridade em áudio.**

Python 3.9+ · Tkinter · FFmpeg · zero dependências externas de Python

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tkinter](https://img.shields.io/badge/Interface-Tkinter-3ea6ff)](https://docs.python.org/3/library/tkinter.html)
[![FFmpeg](https://img.shields.io/badge/Motor-FFmpeg-007808?logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![Plataformas](https://img.shields.io/badge/Linux%20·%20Windows%20·%20macOS-suportado-3fb950)](#-instalação)
[![Licença](https://img.shields.io/badge/Licença-MIT-yellow)](LICENSE)

</div>

---

## ✨ O que ele faz

Um **conversor em lote** que analisa cada arquivo de verdade (streams, codecs,
bitrates, canais, resolução…), mostra tudo antes de converter e processa
milhares de arquivos com fila paralela, nomes configuráveis e retomada de
sessão. O foco é áudio (≈70%); vídeo tem ferramentas sólidas (≈30%).

| Áudio (foco principal) | Vídeo (secundário) |
| --- | --- |
| MP3, AAC, M4A, ALAC, FLAC, OGG/Vorbis, Opus, WAV, AIFF, CAF, WMA, AC-3, E-AC-3, DTS, AMR, MKA | MP4, MKV, MOV, AVI, WebM, MPEG, TS/MTS, FLV, WMV, 3GP, OGV |
| CBR/VBR, bitrate, qualidade, sample rate, canais, ganho, normalização, compressão FLAC | H.264, H.265, AV1, VP9, VP8, MPEG-4, MPEG-2, FFV1 (+ NVENC/QSV/AMF/VideoToolbox quando realmente funcionam) |
| Extração sem recodificar, multi-faixas, 5.1 com escolha explícita | Remux sem recodificação, resolução/FPS, legendas, CRF/bitrate |

- 🔍 **Análise real:** contêiner, codec, perfil, nível, bitrate, canais, layout, sample rate, resolução, FPS, pixel format, HDR, capa, legendas, capítulos.
- 🧩 **Codec ≠ contêiner:** você escolhe os dois separadamente (AAC em `.m4a` ou `.aac` ADTS; ALAC em M4A/CAF…). A interface só oferece combinações compatíveis **com o seu FFmpeg**.
- ⚡ **Paralelismo consciente:** orçamento global de threads dividido entre arquivos simultâneos e threads por encoder — nunca 16 arquivos × 16 threads.
- 🏷️ **Nomenclatura inteligente:** `{name}`, `{artist}`, `{album}`, `{title}`, `{date}`, `{year}`, `{codec}`, `{format}`, `{resolution}`, `{bitrate}`, `{index}`, `{parent}`, `{tag}`, `{ext}`, com pré-visualização ao vivo.
- 📁 **Pastas:** varredura recursiva, filtros, exclusões, hierarquia preservada e proteção contra reprocessar a pasta de destino.
- 🗂️ **Fila em SQLite:** milhares de tarefas, pausa **real** (SIGSTOP/NtSuspendProcess), cancelamento seguro e retomada após fechar o programa.
- 🖼️ **Capa e metadados:** preserva ou permite trocar a imagem de capa; tags são copiadas quando o destino suporta.
- 🛡️ **Integridade:** conversão em arquivo temporário na pasta de destino; só renomeia quando termina com sucesso.
- 💻 **Independente da interface:** o motor também roda por linha de comando (para automação).

---

## 🖼️ Capturas

> Adicione suas capturas em `docs/screenshots/` e referencie aqui:

| Arquivos | Conversão |
| --- | --- |
| ![Arquivos](docs/screenshots/arquivos.png) | ![Conversão](docs/screenshots/conversao.png) |

| Nomenclatura | Desempenho |
| --- | --- |
| ![Nomenclatura](docs/screenshots/nomenclatura.png) | ![Desempenho](docs/screenshots/desempenho.png) |

---

## 🚀 Instalação

### Pré-requisitos

| Item | Versão | Observação |
| --- | --- | --- |
| Python | 3.9+ | Tkinter incluído nas versões oficiais de [python.org](https://www.python.org/downloads/) |
| Tkinter | — | Linux pode exigir o pacote do sistema (veja abaixo) |
| FFmpeg + FFprobe | 4.x+ recomendado (testado no 8.1) | Instalado na máquina, encontrado no `PATH` |

> **Não é preciso `pip install` nada.** O programa usa só a biblioteca padrão.
> O FFmpeg **não** é baixado nem incluído: o programa usa o que já existe na máquina.

---

### 🐧 Linux

**1. Instale o FFmpeg e o Tkinter**

```bash
# Debian / Ubuntu / Mint
sudo apt install ffmpeg python3-tk

# Fedora
sudo dnf install ffmpeg python3-tkinter

# Arch / Manjaro
sudo pacman -S ffmpeg tk

# openSUSE
sudo zypper install ffmpeg python3-tk
```

**2. Baixe o projeto**

```bash
git clone https://github.com/Adeniltonq/universal_converter.git
cd universal_converter
```

**3. Instale (cria launcher e atalho no menu de aplicativos)**

```bash
chmod +x install-linux.sh
./install-linux.sh
```

Depois é só abrir **“Universal Converter”** no menu de aplicativos, ou rodar:

```bash
universal-converter
```

> Sem instalar nada? Também funciona direto:
> ```bash
> python3 universal_converter_launcher.py
> ```
> ou `python3 -m universal_converter`

---

### 🪟 Windows

**1. Instale o Python** em [python.org/downloads/windows](https://www.python.org/downloads/windows/)
e marque **“Add python.exe to PATH”**. (A versão oficial já inclui o Tkinter.)

**2. Instale o FFmpeg** — escolha uma opção:

```powershell
# Opção A — winget
winget install Gyan.FFmpeg

# Opção B — colocar os binários junto ao programa
# Baixe em https://www.gyan.dev/ffmpeg/builds/ (release "essentials"),
# extraia e copie ffmpeg.exe e ffprobe.exe para a pasta bin\ do projeto.
```

**3. Baixe o projeto**

```powershell
git clone https://github.com/Adeniltonq/universal_converter.git
cd universal_converter
```

**4. Instale os atalhos** (Área de Trabalho + Menu Iniciar):

```powershell
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
```

Ou simplesmente **dê duplo clique em `UniversalConverter.bat`**.

---

### 🍎 macOS

**1. Instale o Python (com Tkinter) e o FFmpeg**

```bash
# Recomendado: versão oficial do python.org (já traz Tkinter)
# https://www.python.org/downloads/macos/

# Ou via Homebrew:
brew install python-tk ffmpeg
```

**2. Baixe e abra**

```bash
git clone https://github.com/Adeniltonq/universal_converter.git
cd universal_converter
chmod +x UniversalConverter.command
./UniversalConverter.command          # ou duplo clique no Finder
```

> Se o Finder bloquear o arquivo: clique com o botão direito → **Abrir** → **Abrir mesmo assim**.

---

### 📦 Gerar um executável (opcional)

O FFmpeg continua sendo o da máquina (ou o que estiver em `bin/`). O build usa
PyInstaller (instalado à parte, apenas para empacotar):

```bash
pip install pyinstaller

python build.py                    # arquivo único
python build.py --onedir           # pasta dist/UniversalConverter/

# Incluir um FFmpeg específico dentro do pacote:
python build.py --ffmpeg /usr/bin/ffmpeg --ffprobe /usr/bin/ffprobe
```

> No Windows, `python build.py --ffmpeg C:\ffmpeg\bin\ffmpeg.exe --ffprobe C:\ffmpeg\bin\ffprobe.exe`
> gera `dist\UniversalConverter.exe` com o FFmpeg em `bin\`.

---

## 🖱️ Como usar (pela interface)

1. **Arquivos** → `+ Arquivos…` ou `+ Pasta…` (com opção de subpastas, filtros e exclusões).
   A análise de cada arquivo ocorre em segundo plano; duplo clique mostra **todas** as propriedades.
2. **Conversão** → escolha o contêiner e o codec (só aparecem os suportados), ajuste
   bitrate ou qualidade, canais, sample rate, normalização, capa. Para vídeo, ajuste
   codec/resolução/FPS/preset. `Aplicar configuração aos selecionados` aplica só à seleção.
3. **Nomenclatura** → monte o modelo (ex.: `{name}{separator}{tag}` ou
   `{album}/{index} - {title}`) e veja o nome final na pré-visualização.
4. **Desempenho** → threads, arquivos simultâneos, pasta de destino, preservar estrutura
   e ações da fila (repetir erros, recolocar tudo).
5. **Iniciar** na barra inferior → acompanhe progresso, velocidade, CPU e RAM.
   Use **Pausar** para suspender de verdade e **Cancelar** para interromper com segurança.

### Atalhos

| Atalho | Ação |
| --- | --- |
| `Ctrl+O` | Adicionar arquivos |
| `Ctrl+Shift+O` | Adicionar pasta |
| `Ctrl+Enter` | Iniciar a conversão |
| `Ctrl+A` | Selecionar tudo na fila |
| `Del` | Remover selecionados |
| `Enter` / duplo clique | Propriedades do arquivo |
| `F5` | Atualizar a lista |

---

## 💻 Linha de comando

O motor é independente da interface — ideal para automatizar bibliotecas grandes.

```bash
# O que o seu FFmpeg suporta
python3 -m universal_converter.cli listar formatos
python3 -m universal_converter.cli listar perfis

# Análise completa de um arquivo
python3 -m universal_converter.cli analisar "Isolation.flac"

# Converte uma pasta inteira para Opus 96 kbps, com nomes "Nome_Sepultura"
python3 -m universal_converter.cli converter Musica/ -o Saida/ \
    -c opus --bitrate 96 --nome "{name}_{tag}" --tag Sepultura -t 8

# Extrai o áudio de um vídeo sem recodificar (contêiner escolhido automaticamente)
python3 -m universal_converter.cli converter Show.mkv -o Extraidas/ --extrair

# Usa um perfil pronto; simula antes de converter
python3 -m universal_converter.cli converter Musica/ -o Saida/ --perfil music_hq --simular
python3 -m universal_converter.cli converter Musica/ -o Saida/ --perfil music_hq
```

| Opção | Descrição |
| --- | --- |
| `-o/--saida` · `--ao-lado` | pasta de destino · salvar ao lado do original |
| `-c/--formato` | contêiner (`mp3`, `flac`, `m4a`, `ogg`, `opus`, `wav`, `mp4`, `mkv`, `webm`, `copy`…) |
| `--codec` · `--bitrate` · `--vbr` · `--qualidade` | encoder, bitrate-alvo, VBR/qualidade |
| `--canais` · `--sample-rate` · `--ganho` · `--normalizar` | formato do áudio (padrão mantém o original) |
| `--extrair` · `--faixa` | cópia sem recodificação · faixa de áudio (`auto`, índice, `all`) |
| `--codec-video` · `--resolucao` · `--fps` | opções de vídeo |
| `--nome` · `--tag` · `--perfil` | nomenclatura e perfis |
| `-t/--threads` · `-j/--paralelo` | orçamento de threads e arquivos simultâneos |
| `--simular` | mostra os nomes de saída sem converter |

Diagnóstico rápido:

```bash
python3 -m universal_converter --diagnostico
```

---

## 🏷️ Variáveis de nomenclatura

| Variável | Resultado |
| --- | --- |
| `{name}` | Nome original (sem extensão) |
| `{artist}` | Artista |
| `{album}` | Álbum |
| `{title}` | Título da faixa |
| `{date}` / `{year}` | Data completa / ano |
| `{codec}` | Codec de saída |
| `{format}` | Formato/contêiner de saída |
| `{resolution}` | Resolução (vídeo) |
| `{bitrate}` | Bitrate do áudio de saída |
| `{index}` | Número sequencial |
| `{parent}` | Pasta de origem |
| `{tag}` | Palavra adicional |
| `{ext}` / `{separator}` | Extensão / separador |

Exemplos:

```
{name}{separator}{tag}          →  Isolation_Sepultura.ogg
{artist} - {title}              →  Sepultura - Isolation.ogg
{album}/{index} - {title}       →  Roots/03 - Isolation.ogg
{name}_converted_{codec}        →  Isolation_converted_mp3.ogg
{name} ({resolution})           →  Show (1920x1080).mp4
```

---

## ⚙️ Como funciona por dentro

```
universal_converter/
├── core/          utilitários, configurações (JSON), logs
├── media/         modelos · tabelas de codecs · catálogo (FFmpeg local)
│                  análise (FFprobe) · construção de comandos · execução
├── queue/         escalonador (orçamento de threads) · orquestrador · SQLite
├── filesystem/    varredura de pastas · resolução de destino/estrutura
├── naming/        motor de nomenclatura
├── profiles/      perfis prontos e personalizados
├── ui/            Tkinter: abas, diálogos, tema, monitor
└── cli.py         linha de comando
```

**Decisões importantes**

- **Nada de “converter extensões”:** cada arquivo é analisado com `ffprobe` e as
  combinações oferecidas vêm dos encoders/muxers **reais** da instalação.
- **Camada própria** (`MediaInfo`, `ConversionConfig`, `AudioSettings`, `VideoSettings`,
  `CommandBuilder`) — a interface nunca monta comandos.
- **Threads:** `simultâneos × threads_por_tarefa ≤ orçamento global`, com rebalanceamento
  conforme o custo de cada tarefa (vídeo pesa mais que áudio).
- **Pausa de verdade:** o processo do FFmpeg é suspenso (`SIGSTOP`/`NtSuspendProcess`)
  e retomado, sem perder o trabalho feito.
- **Integridade:** grava em `.nome.umc-XXXX.ext` na pasta final e só renomeia no fim.
- **Memória:** a tabela é virtualizada e a análise fica em cache limitado (ou no banco).
- **Hardware:** encoders de hardware só aparecem se **inicializarem de fato** na máquina.

---

## 🧪 Testes

```bash
python3 -m unittest discover -s tests -v
```

Os testes de integração geram arquivos curtos com o FFmpeg local (e são ignorados
automaticamente se ele não estiver disponível).

---

## 📋 Notas técnicas e limites (importante)

- **Sem perdas de verdade:** converter MP3 → FLAC **não** recupera o que foi perdido;
  apenas evita novas perdas. A interface avisa isso.
- **Bitrates distintos:** áudio, vídeo e total do contêiner são mostrados separadamente.
- **Resolução:** personalizada mantém a proporção com `force_original_aspect_ratio`
  (nunca deforma); `1280xauto` preserva o lado maior.
- **Áudio multicanal:** 5.1/7.1 é preservado por padrão; virar estéreo exige escolha explícita.
- **Cópias não compatíveis:** se o codec original não cabe no contêiner pedido, o
  programa ajusta o codec e avisa (ex.: AAC de MP4 → `.m4a`/`.aac`; ou MKA como fallback).
- **Campos não aplicáveis:** profundidade de bits só vale em codecs sem perdas;
  alguns contêineres (`.aac` ADTS, WAV, AIFF) não guardam tags nem capa.
- **Licenciamento do FFmpeg:** você é responsável pela instalação que usa. Com
  `--enable-gpl` (x264/x265), um pacote redistribuído com esse binário deve respeitar a GPL.
  Distribuir o programa separadamente da instalação do FFmpeg é o caminho mais simples.
  O diagnóstico mostra a configuração da sua instalação.

---

## 🗺️ Roadmap

- [ ] Capítulos editáveis por arquivo
- [ ] ReplayGain/medição loudness em 2 passadas no lote
- [ ] Exportar/importar presets completos pela interface
- [ ] Fila separada por perfil (vários grupos na mesma sessão)
- [ ] Menu de contexto na tabela com “converter esta faixa para…”

---

## 🤝 Contribuindo

```bash
git clone https://github.com/Adeniltonq/universal_converter.git
cd universal_converter
python3 -m unittest discover -s tests        # tudo verde antes de abrir PR
python3 universal_converter_launcher.py      # teste a interface
```

Padrões usados: PEP 8, tipos claros, nenhuma dependência externa no núcleo,
mensagens de erro amigáveis (nada de stack trace para o usuário final).

---

## 📄 Licença

Código deste projeto: **MIT** — veja [LICENSE](LICENSE).
FFmpeg e codecs: licenças próprias (LGPL/GPL) da sua instalação.

<div align="center">

**Feito para transformar bibliotecas grandes em formatos melhores — sem sustos.**

</div>
