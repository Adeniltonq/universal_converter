"""Conversão a partir da linha de comando (sem abrir a interface).

Permite automatizar bibliotecas grandes e serve de base para integrações.

Exemplos:
    python -m universal_converter.cli listar formatos
    python -m universal_converter.cli listar perfis
    python -m universal_converter.cli analisar musica.flac
    python -m universal_converter.cli converter Musica/ -o Saida/ -c opus --bitrate 96
    python -m universal_converter.cli converter video.mp4 -c m4a --extrair
    python -m universal_converter.cli converter Musica/ -o Saida/ --perfil music_hq -j 4 -t 8
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from .core.logger import setup_logging
from .core.util import fmt_bitrate, fmt_duration, fmt_size
from .filesystem.scanner import ScanOptions, scan_folder
from .media.codecs import (
    AUDIO_CONTAINER_KEYS, CODEC_NONE, CONTAINERS, INPUT_CODEC_LABEL, VIDEO_CONTAINER_KEYS,
)
from .media.ffmpeg import FFmpegInfo, probe_file
from .media.models import (
    AudioSettings, ConversionConfig, VideoSettings, media_info_from_probe,
)
from .media.catalog import CodecCatalog
from .naming.engine import NamingTemplate
from .profiles.store import ProfileStore
from .queue.manager import BatchSettings, QueueManager
from .queue.store import JobStore


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="universal-converter", description="Conversor de áudio e vídeo em lote")
    parser.add_argument("--ffmpeg-dir", default="", help="pasta do ffmpeg/ffprobe")
    parser.add_argument("--banco", default="", help="arquivo SQLite da fila (padrão: "
                                                    "uma fila temporária)")
    sub = parser.add_subparsers(dest="comando", required=True)

    listing = sub.add_parser("listar", help="lista formatos, codecs ou perfis")
    listing.add_argument("tipo", choices=["formatos", "perfis", "encoders"],
                         nargs="?", default="formatos")

    analyze = sub.add_parser("analisar", help="mostra a análise de um arquivo")
    analyze.add_argument("arquivo")

    convert = sub.add_parser("converter", help="converte arquivos ou pastas")
    convert.add_argument("entradas", nargs="+", help="arquivos e/ou pastas")
    convert.add_argument("-o", "--saida", default="", help="pasta de destino")
    convert.add_argument("--ao-lado", action="store_true",
                         help="salvar ao lado dos originais")
    convert.add_argument("-c", "--formato", default="mp3",
                         help="contêiner de saída (mp3, flac, m4a, ogg, opus, wav, "
                              "aiff, wma, m4a, mp4, mkv, webm…) ou 'copy'")
    convert.add_argument("--codec", default="", help="encoder de áudio (ex.: libopus)")
    convert.add_argument("--codec-video", default="copy",
                         help="encoder de vídeo (padrão: copiar sem recodificar)")
    convert.add_argument("--bitrate", default="", help="bitrate de áudio (ex.: 192k)")
    convert.add_argument("--vbr", action="store_true", help="qualidade VBR (ver --qualidade)")
    convert.add_argument("--qualidade", type=int, default=None,
                         help="qualidade do encoder (VBR ou CRF no vídeo)")
    convert.add_argument("--canais", default="keep",
                         help="keep, 1, 2, 6… (padrão: manter — 5.1 não virou estéreo)")
    convert.add_argument("--sample-rate", default="keep", help="taxa de amostragem")
    convert.add_argument("--ganho", type=float, default=0.0, help="ganho em dB")
    convert.add_argument("--normalizar", choices=["off", "ebu", "peak"], default="off")
    convert.add_argument("--extrair", action="store_true",
                         help="copiar a faixa de áudio sem recodificar (contêiner automático)")
    convert.add_argument("--faixa", default="auto", help="faixa de áudio (índice) ou 'all'")
    convert.add_argument("--resolucao", default="keep", help="ex.: 1920x1080")
    convert.add_argument("--fps", default="keep")
    convert.add_argument("--nome", default="{name}",
                         help="modelo de nome, ex.: '{name}_{tag}'")
    convert.add_argument("--tag", default="", help="palavra usada em {tag}")
    convert.add_argument("--perfil", default="", help="perfil pronto (ver 'listar perfis')")
    convert.add_argument("-t", "--threads", type=int, default=0,
                         help="orçamento global de threads (0 = automático)")
    convert.add_argument("-j", "--paralelo", type=int, default=0,
                         help="arquivos simultâneos (0 = automático)")
    convert.add_argument("--nao-recursivo", action="store_true")
    convert.add_argument("--ext", default="", help="extensões aceitas (ex.: mp3,flac)")
    convert.add_argument("--excluir", default="", help="padrões glob separados por vírgula")
    convert.add_argument("--sobrescrever", action="store_true")
    convert.add_argument("--simular", action="store_true",
                         help="mostra os nomes de saída sem converter")
    convert.add_argument("--progresso", default="barra", choices=["barra", "linha", "nenhum"])
    return parser


def cmd_listar(args, catalog: CodecCatalog, profiles: ProfileStore) -> int:
    if args.tipo == "encoders":
        print("Encoders de áudio disponíveis:")
        encoders = sorted(catalog.audio_encoders())
        for name in encoders:
            print("  " + name)
        print(f"\nTotal: {len(encoders)}")
        return 0
    if args.tipo == "perfis":
        for profile in profiles.all():
            kind = "áudio" if profile.kind == "audio" else "vídeo"
            print(f"{profile.id:16s} {profile.name} ({kind}) — {profile.description}")
        return 0
    print("Contêineres de áudio:")
    for key in AUDIO_CONTAINER_KEYS:
        if not catalog.container_available(key):
            continue
        codecs = ", ".join(o.id for o in catalog.audio_options(key) if not o.is_copy)
        print(f"  {key:6s} {CONTAINERS[key].label:28s} codecs: {codecs}")
    print("\nContêineres de vídeo:")
    for key in VIDEO_CONTAINER_KEYS:
        if not catalog.container_available(key):
            continue
        codecs = ", ".join(o.id for o in catalog.video_options(key)
                           if not o.is_copy and o.id != CODEC_NONE)
        print(f"  {key:6s} {CONTAINERS[key].label:28s} codecs: {codecs or '(nenhum instalado)'}")
    return 0


def cmd_analisar(args, ff: FFmpegInfo) -> int:
    info = media_info_from_probe(args.arquivo, probe_file(ff.ffprobe, args.arquivo))
    print(f"Arquivo: {info.path}")
    print(f"Contêiner: {info.format_label()} · duração {fmt_duration(info.duration)} · "
          f"{fmt_size(info.size)} · bitrate {fmt_bitrate(info.bitrate)}")
    for stream in info.streams:
        prefix = "  "
        if stream.type == "audio":
            print(f"{prefix}áudio #{stream.index}: {INPUT_CODEC_LABEL.get(stream.codec, stream.codec)} "
                  f"{stream.channels}ch {stream.sample_rate}Hz "
                  f"{fmt_bitrate(stream.bitrate) if stream.bitrate else ''} "
                  f"[{stream.language or 'und'}]")
        elif stream.type == "video":
            kind = "capa" if stream.is_cover else "vídeo"
            print(f"{prefix}{kind} #{stream.index}: {INPUT_CODEC_LABEL.get(stream.codec, stream.codec)} "
                  f"{stream.width}x{stream.height} {stream.fps:.3f}fps {stream.pix_fmt}")
        else:
            print(f"{prefix}{stream.type} #{stream.index}: {stream.codec} [{stream.language}]")
    if info.tags:
        print("Metadados:")
        for key, value in sorted(info.tags.items()):
            print(f"  {key}: {value}")
    return 0


def cmd_converter(args, ff: FFmpegInfo, catalog: CodecCatalog,
                  profiles: ProfileStore) -> int:
    audio = AudioSettings()
    video = VideoSettings(codec=args.codec_video)
    container = args.formato
    kind = "audio"
    if args.perfil:
        profile = profiles.find(args.perfil)
        if profile is None:
            print(f"Perfil desconhecido: {args.perfil}", file=sys.stderr)
            return 2
        config = profile.config()
        audio, video = config.audio, config.video
        container = config.container
        kind = config.kind
    if args.extrair:
        container = "copy"
        audio.codec = "copy"
    elif args.codec:
        audio.codec = args.codec
    elif not args.perfil and not args.extrair:
        # escolhe o encoder "óbvio" para o contêiner pedido
        audio.codec = catalog.default_audio_codec(container)
    if args.bitrate:
        audio.bitrate = args.bitrate if args.bitrate.endswith("k") else f"{args.bitrate}k"
    if args.vbr:
        audio.mode = "vbr"
    if args.qualidade is not None:
        audio.quality = args.qualidade
        video.quality = args.qualidade
    audio.channels = args.canais
    audio.sample_rate = args.sample_rate
    audio.gain_db = args.ganho
    audio.normalize = args.normalizar
    audio.stream = args.faixa
    video.resolution = args.resolucao
    video.fps = args.fps
    if args.codec_video != "copy":
        kind = "video"
    config = ConversionConfig(kind=kind, container=container, audio=audio, video=video)

    files: list[str] = []
    root = ""
    extensions = None
    if args.ext:
        extensions = {e.strip().lstrip(".").lower() for e in args.ext.split(",") if e.strip()}
    for entry in args.entradas:
        if os.path.isdir(entry):
            if not root:
                root = os.path.abspath(entry)
            options = ScanOptions(
                recursive=not args.nao_recursivo,
                extensions=extensions or ScanOptions().extensions,
                exclude_patterns=[p.strip() for p in args.excluir.split(",") if p.strip()],
                output_dir=args.saida)
            result = scan_folder(entry, options)
            files.extend(result.files)
        elif os.path.isfile(entry):
            files.append(os.path.abspath(entry))
            if not root:
                root = os.path.dirname(os.path.abspath(entry))
        else:
            print(f"Ignorado (não existe): {entry}", file=sys.stderr)
    if not files:
        print("Nenhum arquivo de mídia encontrado.", file=sys.stderr)
        return 2

    db_path = args.banco or os.path.join(
        os.environ.get("TMPDIR", "/tmp"), f"umc-cli-{os.getpid()}.db")
    store = JobStore(db_path)
    manager = QueueManager(ff, store, catalog)
    manager.add_files(files, config)
    manager.load_cached_infos([job.id for job in manager.jobs])
    if args.nome or args.tag:
        manager.settings.naming = NamingTemplate(template=args.nome, separator="_")
        manager.settings.tag = args.tag
    manager.settings = BatchSettings(
        threads=args.threads, concurrent=args.paralelo,
        overwrite=args.sobrescrever,
        output_mode="beside" if args.ao_lado else "folder",
        output_dir=os.path.abspath(args.saida) if args.saida else "",
        source_root=root,
        naming=NamingTemplate(template=args.nome, separator="_"),
        tag=args.tag,
    )
    if args.simular:
        for index, (job, path, warning) in enumerate(manager.plan_paths(), start=1):
            print(f"{index:>4}. {path}" + (f"   [{warning}]" if warning else ""))
        store.close()
        try:
            os.remove(db_path)
        except OSError:
            pass
        return 0

    started = time.time()
    if not manager.start():
        store.close()
        return 1
    last_line = 0.0
    try:
        while manager.is_running:
            for event in manager.poll():
                kind_event = event["type"]
                if kind_event == "job_finished":
                    job = event["job"]
                    size = os.path.getsize(job.output_path) if job.output_path and \
                        os.path.isfile(job.output_path) else 0
                    status = "OK " if job.status == "done" else "ERRO"
                    print(f"[{status}] {os.path.basename(job.file)} → "
                          f"{os.path.basename(job.output_path) or '-'} "
                          f"({fmt_size(size)})" + (f" — {job.message}" if
                                                   job.status != "done" else ""))
                elif kind_event == "job_warning":
                    print(f"  aviso: {event.get('message')}")
                elif kind_event == "error":
                    print(event.get("message"), file=sys.stderr)
            now = time.time()
            if args.progresso == "barra" and now - last_line > 0.5:
                last_line = now
                running = [job for job in manager.jobs if job.status == "running"]
                done = sum(1 for job in manager.jobs if job.status in ("done", "error",
                                                                       "cancelled"))
                progress = sum(job.progress for job in running) / max(1, len(running))
                print(f"\r  {done}/{len(manager.jobs)} · {progress * 100:5.1f}% "
                      f"· {len(running)} ativo(s)", end="", flush=True)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nCancelando…")
        manager.cancel_all()
        manager.wait_idle(timeout=30)
    if args.progresso == "barra":
        print()
    stats = manager.stats
    elapsed = time.time() - started
    print(f"Concluído: {stats.done} ok, {stats.errors} erro(s), "
          f"{stats.cancelled} cancelada(s) em {fmt_duration(elapsed)}.")
    store.close()
    if not args.banco:
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(db_path + suffix)
            except OSError:
                pass
    return 0 if stats.errors == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    setup_logging()
    ff = FFmpegInfo.locate(args.ffmpeg_dir or None)
    ff.ensure_loaded()
    if ff.error:
        print(ff.error, file=sys.stderr)
        return 1
    catalog = CodecCatalog(ff)
    profiles = ProfileStore()
    if args.comando == "listar":
        return cmd_listar(args, catalog, profiles)
    if args.comando == "analisar":
        return cmd_analisar(args, ff)
    if args.comando == "converter":
        return cmd_converter(args, ff, catalog, profiles)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
