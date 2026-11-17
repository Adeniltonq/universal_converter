"""Tabelas de conhecimento sobre codecs, contêineres, extensões e combinações.

Tudo aqui descreve o que o programa *sabe* fazer. A disponibilidade real
depende da instalação do FFmpeg e é verificada em `ffmpeg.py` (FFmpegInfo) e
`catalog.py` (CodecCatalog).
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Canais de áudio
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChannelInfo:
    name: str
    label: str
    layout: str


CHANNELS: dict[str, ChannelInfo] = {
    "keep": ChannelInfo("keep", "Manter original", ""),
    "1": ChannelInfo("1", "Mono (1.0)", "mono"),
    "2": ChannelInfo("2", "Estéreo (2.0)", "stereo"),
    "3": ChannelInfo("3", "2.1", "2.1"),
    "4": ChannelInfo("4", "Quadrifônico (4.0)", "quad"),
    "6": ChannelInfo("6", "5.1", "5.1"),
    "8": ChannelInfo("8", "7.1", "7.1"),
}

# Bitrate mínimo coerente com o número de canais (evita 5.1 em 64 kbps).
MIN_BITRATE_PER_CHANNEL = 32000


def min_bitrate(channels: str | int, codec_id: str) -> int:
    try:
        count = int(channels)
    except (TypeError, ValueError):
        count = 2
    per_channel = {"opus": 16000, "vorbis": 24000, "mp3": 24000, "aac": 24000,
                   "wmav2": 24000, "ac3": 32000}.get(codec_id, MIN_BITRATE_PER_CHANNEL)
    return max(count, 1) * per_channel


# ---------------------------------------------------------------------------
# Codecs de áudio
# ---------------------------------------------------------------------------

AUDIO_CODEC_ORDER = [
    "libmp3lame", "aac", "libfdk_aac", "libopus", "libvorbis", "flac", "alac",
    "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "pcm_s16be", "pcm_s24be",
    "pcm_f32be", "pcm_s32be", "wmav2", "ac3", "eac3", "dca", "libopencore_amrnb",
    "libopencore_amrwb", "libvo_amrwbenc",
]


@dataclass(frozen=True)
class AudioCodec:
    id: str
    label: str
    alias: str                     # família (mp3, aac, flac...) para comparações
    lossless: bool = False
    vbr: bool = False              # aceita -q:a (qualidade VBR)
    compression: bool = False      # aceita -compression_level
    bitrate: bool = True           # aceita -b:a
    bitrates: tuple[int, ...] = (64, 96, 128, 160, 192, 224, 256, 320)
    default_quality: int = 3
    quality_range: tuple[int, int] = (0, 10)
    max_channels: int = 8
    max_sample_rate: int = 192000
    max_bitrate: int = 640_000
    big_endian: bool = False


AUDIO_CODECS: dict[str, AudioCodec] = {
    "libmp3lame": AudioCodec(
        "libmp3lame", "MP3 (LAME)", "mp3", vbr=True,
        bitrates=(64, 96, 112, 128, 160, 192, 224, 256, 320), default_quality=2,
        quality_range=(0, 9), max_channels=2),
    "aac": AudioCodec(
        "aac", "AAC (nativo)", "aac", vbr=True,
        bitrates=(64, 96, 128, 160, 192, 224, 256, 320), default_quality=2,
        quality_range=(1, 5)),
    "libfdk_aac": AudioCodec(
        "libfdk_aac", "AAC (Fraunhofer FDK)", "aac", vbr=True,
        bitrates=(64, 96, 128, 160, 192, 224, 256, 320), default_quality=3,
        quality_range=(1, 5)),
    "libopus": AudioCodec(
        "libopus", "Opus", "opus", bitrates=(48, 64, 96, 128, 160, 192, 256, 320),
        max_sample_rate=48000, max_bitrate=510_000),
    "libvorbis": AudioCodec(
        "libvorbis", "Vorbis", "vorbis", vbr=True,
        bitrates=(64, 96, 128, 160, 192, 224, 256, 320), default_quality=5,
        quality_range=(0, 10)),
    "flac": AudioCodec(
        "flac", "FLAC (sem perdas)", "flac", lossless=True, compression=True),
    "alac": AudioCodec("alac", "ALAC (sem perdas, Apple)", "alac", lossless=True),
    "pcm_s16le": AudioCodec("pcm_s16le", "PCM 16 bits", "pcm_s16le", lossless=True),
    "pcm_s24le": AudioCodec("pcm_s24le", "PCM 24 bits", "pcm_s24le", lossless=True),
    "pcm_s32le": AudioCodec("pcm_s32le", "PCM 32 bits", "pcm_s32le", lossless=True),
    "pcm_f32le": AudioCodec("pcm_f32le", "PCM float 32 bits", "pcm_f32le",
                            lossless=True),
    # big-endian (AIFF/CAF)
    "pcm_s16be": AudioCodec("pcm_s16be", "PCM 16 bits (BE)", "pcm_s16be",
                            lossless=True, big_endian=True),
    "pcm_s24be": AudioCodec("pcm_s24be", "PCM 24 bits (BE)", "pcm_s24be",
                            lossless=True, big_endian=True),
    "pcm_f32be": AudioCodec("pcm_f32be", "PCM float 32 bits (BE)", "pcm_f32be",
                            lossless=True, big_endian=True),
    "pcm_s32be": AudioCodec("pcm_s32be", "PCM 32 bits (BE)", "pcm_s32be",
                            lossless=True, big_endian=True),
    "wmav2": AudioCodec(
        "wmav2", "WMA v2", "wma", bitrates=(64, 96, 128, 160, 192, 256, 320),
        max_channels=2),
    "ac3": AudioCodec(
        "ac3", "AC-3 (Dolby Digital)", "ac3",
        bitrates=(96, 128, 192, 224, 256, 320, 384, 448, 640), max_channels=6),
    "eac3": AudioCodec(
        "eac3", "E-AC-3 (Dolby Digital Plus)", "eac3",
        bitrates=(128, 192, 256, 384, 448, 640, 768), max_channels=8),
    "dca": AudioCodec(
        "dca", "DTS", "dts", bitrates=(384, 768, 1152, 1536), max_channels=6),
    "libopencore_amrnb": AudioCodec(
        "libopencore_amrnb", "AMR-NB", "amr_nb", bitrate=False, max_channels=1,
        max_sample_rate=8000),
    "libopencore_amrwb": AudioCodec(
        "libopencore_amrwb", "AMR-WB", "amr_wb", bitrate=False, max_channels=1,
        max_sample_rate=16000),
    "libvo_amrwbenc": AudioCodec(
        "libvo_amrwbenc", "AMR-WB (VisualOn)", "amr_wb", bitrate=False,
        max_channels=1, max_sample_rate=16000),
}

CODEC_COPY = "copy"
CODEC_NONE = "none"

# Encoder -> família lógica (para detectar "mesmo codec do original")
ENCODER_TO_CODEC: dict[str, str] = {
    "libmp3lame": "mp3", "libshine": "mp3", "mp3": "mp3",
    "aac": "aac", "libfdk_aac": "aac", "libfaac": "aac",
    "libopus": "opus", "opus": "opus",
    "libvorbis": "vorbis", "vorbis": "vorbis",
    "flac": "flac", "alac": "alac",
    "ac3": "ac3", "eac3": "eac3", "dca": "dts",
    "wmav1": "wma", "wmav2": "wma",
    "libopencore_amrnb": "amr_nb", "libopencore_amrwb": "amr_wb",
    "libvo_amrwbenc": "amr_wb", "amr_nb": "amr_nb",
    "pcm_s16le": "pcm_s16le", "pcm_s24le": "pcm_s24le",
    "pcm_s32le": "pcm_s32le", "pcm_s16be": "pcm_s16be",
    "pcm_s24be": "pcm_s24be", "pcm_f32le": "pcm_f32le", "pcm_f32be": "pcm_f32le",
    "mp2": "mp2", "mp2fixed": "mp2", "twolame": "mp2",
}

# ---------------------------------------------------------------------------
# Codecs de vídeo
# ---------------------------------------------------------------------------

VIDEO_CODEC_ORDER = [
    "libx264", "libx265", "libsvtav1", "libaom-av1", "libvpx-vp9", "libvpx",
    "libopenh264", "mpeg4", "mpeg2video", "libxvid", "wmv2", "h263", "h263p",
    "h264_nvenc", "hevc_nvenc", "av1_nvenc", "h264_qsv", "hevc_qsv", "av1_qsv",
    "h264_amf", "hevc_amf", "av1_amf", "h264_videotoolbox", "hevc_videotoolbox",
    "ffv1", "prores", "mjpeg", "huffyuv", "utvideo", "theora", "flv1", "wmv1",
]


@dataclass(frozen=True)
class VideoCodec:
    id: str
    label: str
    family: str
    quality_mode: str = "crf"           # crf | bitrate
    quality_args: tuple[str, ...] = ("-crf", "{v}")
    quality_range: tuple[float, float] = (0, 51)
    quality_default: float = 23
    presets: tuple[str, ...] = ()
    default_preset: str = ""
    hwaccel: str = ""                   # nvenc | qsv | amf | videotoolbox
    profile_args: bool = True


_MPEG_PRESETS = ("ultrafast", "superfast", "veryfast", "faster", "fast",
                 "medium", "slow", "slower", "veryslow")
_X26X_PRESETS = ("ultrafast", "superfast", "veryfast", "faster", "fast",
                 "medium", "slow", "slower", "veryslow", "placebo")
_SVT_PRESETS = ("0", "2", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13")
NVENC_PRESETS = ("p1", "p2", "p3", "p4", "p5", "p6", "p7")

VIDEO_CODECS: dict[str, VideoCodec] = {
    "libx264": VideoCodec("libx264", "H.264 / AVC (x264)", "h264", "crf",
                          ("-crf", "{v}"), (0, 51), 23, _X26X_PRESETS, "medium"),
    "libx265": VideoCodec("libx265", "H.265 / HEVC (x265)", "hevc", "crf",
                          ("-crf", "{v}"), (0, 51), 28, _X26X_PRESETS, "medium"),
    "libsvtav1": VideoCodec("libsvtav1", "AV1 (SVT-AV1)", "av1", "crf",
                            ("-crf", "{v}"), (0, 63), 35, _SVT_PRESETS, "8"),
    "libaom-av1": VideoCodec("libaom-av1", "AV1 (libaom)", "av1", "crf",
                             ("-crf", "{v}"), (0, 63), 32,
                             ("realtime", "good", "best"), "good"),
    "libvpx-vp9": VideoCodec("libvpx-vp9", "VP9 (libvpx)", "vp9", "crf",
                             ("-crf", "{v}"), (0, 63), 31,
                             ("realtime", "good", "best"), "good"),
    "libvpx": VideoCodec("libvpx", "VP8 (libvpx)", "vp8", "crf",
                         ("-crf", "{v}"), (4, 63), 10,
                         ("realtime", "good", "best"), "good"),
    "libopenh264": VideoCodec("libopenh264", "H.264 (OpenH264)", "h264", "bitrate",
                              (), (0, 51), 23, _MPEG_PRESETS, "medium",
                              profile_args=False),
    "mpeg4": VideoCodec("mpeg4", "MPEG-4 Part 2", "mpeg4", "crf", ("-q:v", "{v}"),
                        (2, 31), 5),
    "mpeg2video": VideoCodec("mpeg2video", "MPEG-2", "mpeg2", "crf", ("-q:v", "{v}"),
                             (2, 31), 5),
    "libxvid": VideoCodec("libxvid", "MPEG-4 (Xvid)", "mpeg4", "crf", ("-q:v", "{v}"),
                          (2, 31), 5),
    "wmv2": VideoCodec("wmv2", "WMV2", "wmv", "crf", ("-q:v", "{v}"), (2, 31), 5),
    "h263": VideoCodec("h263", "H.263", "h263", "bitrate", (), (0, 51), 23),
    "h263p": VideoCodec("h263p", "H.263+", "h263", "bitrate", (), (0, 51), 23),
    # hardware ----------------------------------------------------------
    "h264_nvenc": VideoCodec("h264_nvenc", "H.264 (NVENC)", "h264", "crf",
                             ("-rc", "vbr", "-cq", "{v}"), (0, 51), 23,
                             NVENC_PRESETS, "p4", "nvenc"),
    "hevc_nvenc": VideoCodec("hevc_nvenc", "H.265 (NVENC)", "hevc", "crf",
                             ("-rc", "vbr", "-cq", "{v}"), (0, 51), 28,
                             NVENC_PRESETS, "p4", "nvenc"),
    "av1_nvenc": VideoCodec("av1_nvenc", "AV1 (NVENC)", "av1", "crf",
                            ("-rc", "vbr", "-cq", "{v}"), (0, 63), 30,
                            NVENC_PRESETS, "p4", "nvenc"),
    "h264_qsv": VideoCodec("h264_qsv", "H.264 (Quick Sync)", "h264", "crf",
                           ("-global_quality", "{v}"), (1, 51), 23, _MPEG_PRESETS,
                           "medium", "qsv"),
    "hevc_qsv": VideoCodec("hevc_qsv", "H.265 (Quick Sync)", "hevc", "crf",
                           ("-global_quality", "{v}"), (1, 51), 26, _MPEG_PRESETS,
                           "medium", "qsv"),
    "av1_qsv": VideoCodec("av1_qsv", "AV1 (Quick Sync)", "av1", "crf",
                          ("-global_quality", "{v}"), (1, 63), 30,
                          ("veryfast", "medium", "slow"), "medium", "qsv"),
    "h264_amf": VideoCodec("h264_amf", "H.264 (AMF)", "h264", "crf",
                           ("-rc", "cqp", "-qp_i", "{v}", "-qp_p", "{v}"),
                           (0, 51), 22, ("speed", "balanced", "quality"), "balanced",
                           "amf"),
    "hevc_amf": VideoCodec("hevc_amf", "H.265 (AMF)", "hevc", "crf",
                           ("-rc", "cqp", "-qp_i", "{v}", "-qp_p", "{v}"),
                           (0, 51), 26, ("speed", "balanced", "quality"), "balanced",
                           "amf"),
    "av1_amf": VideoCodec("av1_amf", "AV1 (AMF)", "av1", "crf",
                          ("-rc", "cqp", "-qp_i", "{v}", "-qp_p", "{v}"),
                          (0, 63), 28, ("speed", "balanced", "quality"), "balanced",
                          "amf"),
    "h264_videotoolbox": VideoCodec("h264_videotoolbox", "H.264 (VideoToolbox)",
                                    "h264", "bitrate", (), (0, 51), 23, (), "",
                                    "videotoolbox", False),
    "hevc_videotoolbox": VideoCodec("hevc_videotoolbox", "H.265 (VideoToolbox)",
                                    "hevc", "bitrate", (), (0, 51), 25, (), "",
                                    "videotoolbox", False),
}

VIDEO_EXTRA_ARGS: dict[str, tuple[str, ...]] = {
    "libx264": ("-preset", "{preset}"),
    "libx265": ("-preset", "{preset}", "-x265-params", "log-level=error"),
    "libsvtav1": ("-preset", "{preset}"),
    "libaom-av1": ("-cpu-used", "6", "-row-mt", "1"),
    "libvpx-vp9": ("-row-mt", "1"),
    "libvpx": ("-deadline", "good", "-cpu-used", "2"),
    "libopenh264": ("-preset", "{preset}"),
    "mpeg4": ("-qmin", "2"),
    # hardware ----------------------------------------------------------
    "h264_nvenc": ("-preset", "{preset}"),
    "hevc_nvenc": ("-preset", "{preset}"),
    "av1_nvenc": ("-preset", "{preset}"),
    "h264_qsv": ("-preset", "{preset}"),
    "hevc_qsv": ("-preset", "{preset}"),
    "av1_qsv": ("-preset", "{preset}"),
    "h264_amf": ("-quality", "{preset}"),
    "hevc_amf": ("-quality", "{preset}"),
    "av1_amf": ("-quality", "{preset}"),
}

FAMILY_LABEL = {
    "h264": "H.264 / AVC", "hevc": "H.265 / HEVC", "av1": "AV1", "vp9": "VP9",
    "vp8": "VP8", "mpeg4": "MPEG-4 Part 2", "mpeg2": "MPEG-2", "wmv": "WMV",
    "h263": "H.263",
}

VIDEO_PROFILES: dict[str, tuple[str, ...]] = {
    "h264": ("baseline", "main", "high", "high10", "high422", "high444"),
    "hevc": ("main", "main10", "mainstillpicture"),
    "av1": (),
    "vp9": ("0", "1", "2", "3"),
    "vp8": (),
    "mpeg4": (),
    "mpeg2": ("main", "high"),
    "wmv": (),
    "h263": (),
}

VIDEO_PRESETS = {
    "Equilibrado (padrão)": {"codec": None, "mode": "crf"},
    "Qualidade (arquivo grande)": {"codec": None, "mode": "crf", "quality": 18},
    "Arquivo pequeno": {"codec": None, "mode": "crf", "quality": 30},
    "Streaming — bitrate fixo": {"codec": None, "mode": "abr", "bitrate": "4M"},
    "Cópia rápida (sem recodificar)": {"codec": "copy", "mode": "crf"},
}

VIDEO_LEVELS: dict[str, tuple[str, ...]] = {
    "h264": ("3.0", "3.1", "3.2", "4.0", "4.1", "4.2", "5.0", "5.1", "5.2", "6.0"),
    "hevc": ("3.0", "3.1", "4.0", "4.1", "5.0", "5.1", "5.2", "6.0", "6.1", "6.2"),
    "mpeg2": ("low", "main", "high"),
}

PIXEL_FORMATS = ("manter", "yuv420p", "yuv422p", "yuv444p", "yuv420p10le",
                 "yuv422p10le", "yuv444p10le", "nv12", "gray")

# ---------------------------------------------------------------------------
# Contêineres
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Container:
    id: str
    label: str
    muxer: str | None             # None = muxer escolhido pela extensão
    audio_exts: tuple[str, ...]
    video_exts: tuple[str, ...]
    audio_codecs: tuple[str, ...] = ()   # ids de ENCODERS de áudio aceitos
    video_codecs: tuple[str, ...] = ()
    kind: str = "both"            # audio | video | both | video_only | copy
    cover: bool = True            # suporta capa embutida
    id3: bool = False
    requires_native_aac: bool = False
    notes: str = ""


VIDEO_CODEC_IDS = tuple(VIDEO_CODECS) + ("copy",)

CONTAINERS: dict[str, Container] = {
    # -------- somente áudio -------------------------------------------
    "mp3": Container("mp3", "MP3", "mp3", ("mp3",), (),
                     audio_codecs=("libmp3lame", "libshine"), kind="audio", id3=True),
    "m4a": Container("m4a", "M4A / MP4 (áudio)", "ipod", ("m4a",), (),
                     audio_codecs=("aac", "libfdk_aac", "alac"), kind="audio"),
    "adts": Container("adts", "AAC — ADTS (.aac)", "adts", ("aac",), (),
                      audio_codecs=("aac", "libfdk_aac"), kind="audio", cover=False,
                      requires_native_aac=True,
                      notes="AAC bruto (ADTS): sem contêiner, metadados ou capa."),
    "flac": Container("flac", "FLAC", "flac", ("flac",), (),
                      audio_codecs=("flac",), kind="audio"),
    "ogg": Container("ogg", "OGG", "ogg", ("ogg",), (),
                     audio_codecs=("libvorbis", "libopus", "flac"), kind="audio"),
    "opus": Container("opus", "Opus (.opus)", "opus", ("opus",), (),
                      audio_codecs=("libopus",), kind="audio", cover=False),
    "wav": Container("wav", "WAV", "wav", ("wav",), (),
                     audio_codecs=("pcm_s16le", "pcm_s24le", "pcm_s32le",
                                   "pcm_f32le"), kind="audio", cover=False),
    "aiff": Container("aiff", "AIFF", "aiff", ("aiff", "aif"), (),
                      audio_codecs=("pcm_s16be", "pcm_s24be", "pcm_s32be", "pcm_f32be"),
                      kind="audio", cover=False),
    "caf": Container("caf", "CAF (Apple)", "caf", ("caf",), (),
                     audio_codecs=("pcm_s16le", "pcm_s24le", "alac"), kind="audio"),
    "wma": Container("wma", "WMA", "asf", ("wma",), (),
                     audio_codecs=("wmav2", "wmav1"), kind="audio"),
    "mka": Container("mka", "MKA (Matroska áudio)", "matroska", ("mka",), (),
                     audio_codecs=tuple(AUDIO_CODECS), kind="audio"),
    "ac3": Container("ac3", "AC-3", "ac3", ("ac3",), (),
                     audio_codecs=("ac3",), kind="audio", cover=False),
    "eac3": Container("eac3", "E-AC-3", "eac3", ("eac3",), (),
                      audio_codecs=("eac3",), kind="audio", cover=False),
    "dts": Container("dts", "DTS", "dca", ("dts",), (),
                     audio_codecs=("dca",), kind="audio", cover=False),
    "amr": Container("amr", "AMR", "amr", ("amr",), (),
                     audio_codecs=("libopencore_amrnb", "libvo_amrwbenc"),
                     kind="audio", cover=False),
    # -------- vídeo -----------------------------------------------------
    "mp4": Container(
        "mp4", "MP4", None, ("m4a",), ("mp4",),
        audio_codecs=("aac", "libfdk_aac", "mp3", "libmp3lame", "ac3", "eac3",
                      "alac", "opus", "libopus"),
        video_codecs=tuple(c for c in VIDEO_CODECS
                           if c in ("libx264", "libx265", "libsvtav1", "libaom-av1",
                                    "libvpx-vp9", "libvpx", "libopenh264", "mpeg4",
                                    "h264_nvenc", "hevc_nvenc", "av1_nvenc", "h264_qsv",
                                    "hevc_qsv", "av1_qsv", "h264_amf", "hevc_amf",
                                    "av1_amf", "h264_videotoolbox",
                                    "hevc_videotoolbox")) + ("copy",)),
    "mkv": Container("mkv", "MKV (Matroska)", "matroska", ("mka",), ("mkv",),
                     audio_codecs=tuple(AUDIO_CODECS),
                     video_codecs=VIDEO_CODEC_IDS + ("ffv1", "prores", "mjpeg",
                                                     "huffyuv", "utvideo")),
    "webm": Container("webm", "WebM", "webm", (), ("webm",),
                      audio_codecs=("libopus", "libvorbis"),
                      video_codecs=("libvpx-vp9", "libvpx", "libsvtav1",
                                    "libaom-av1", "copy"),
                      kind="video", cover=False,
                      notes="Formato aberto para web; não carrega capa."),
    "mov": Container("mov", "MOV (QuickTime)", "mov", ("m4a",), ("mov",),
                     audio_codecs=("aac", "libfdk_aac", "alac", "pcm_s16le",
                                   "pcm_s24le", "mp3", "libmp3lame"),
                     video_codecs=("libx264", "libx265", "libsvtav1", "mpeg4",
                                   "libopenh264", "prores", "h264_videotoolbox",
                                   "hevc_videotoolbox", "h264_nvenc", "hevc_nvenc",
                                   "copy")),
    "avi": Container("avi", "AVI", "avi", (), ("avi",),
                     audio_codecs=("libmp3lame", "mp3", "ac3", "wmav2", "pcm_s16le"),
                     video_codecs=("mpeg4", "libxvid", "libx264", "libx265",
                                   "mpeg2video", "wmv2", "ffv1", "mjpeg", "copy"),
                     cover=False),
    "mpeg": Container("mpeg", "MPEG (program stream)", "mpeg", (), ("mpg", "mpeg"),
                      audio_codecs=("mp2", "ac3", "mp3", "libmp3lame"),
                      video_codecs=("mpeg2video", "mpeg4", "copy"), cover=False),
    "ts": Container("ts", "MPEG-TS", "mpegts", (), ("ts", "mts", "m2ts"),
                    audio_codecs=("aac", "libfdk_aac", "ac3", "eac3", "mp2",
                                  "libmp3lame", "mp3", "libopus"),
                    video_codecs=("libx264", "libx265", "mpeg2video", "libsvtav1",
                                  "copy"), cover=False),
    "flv": Container("flv", "FLV", "flv", (), ("flv",),
                     audio_codecs=("aac", "libfdk_aac", "libmp3lame", "mp3"),
                     video_codecs=("libx264", "libopenh264", "flv1", "copy"),
                     cover=False),
    "wmv": Container("wmv", "WMV (ASF)", "asf", (), ("wmv",),
                     audio_codecs=("wmav2", "wmav1"),
                     video_codecs=("wmv2", "wmv1", "mpeg4", "copy"), cover=False),
    "3gp": Container("3gp", "3GP", "3gp", (), ("3gp",),
                     audio_codecs=("aac", "libfdk_aac", "libopencore_amrnb",
                                   "libvo_amrwbenc", "amr_nb"),
                     video_codecs=("libx264", "h263", "mpeg4", "copy"), cover=False),
    "ogv": Container("ogv", "OGV (Ogg vídeo)", "ogg", (), ("ogv",),
                     audio_codecs=("libvorbis", "libopus"),
                     video_codecs=("libtheora", "copy"), kind="video", cover=False),
    # -------- especial --------------------------------------------------
    "copy": Container("copy", "Manter contêiner original", None, (), (), kind="copy",
                      cover=False),
}

AUDIO_CONTAINER_KEYS = [k for k, c in CONTAINERS.items() if c.kind == "audio"]
VIDEO_CONTAINER_KEYS = [k for k, c in CONTAINERS.items()
                        if c.kind in ("video", "both")]

CONTAINER_DEFAULT_EXT = {
    "mp3": "mp3", "m4a": "m4a", "adts": "aac", "flac": "flac", "ogg": "ogg",
    "opus": "opus", "wav": "wav", "aiff": "aiff", "caf": "caf", "wma": "wma",
    "mka": "mka", "ac3": "ac3", "eac3": "eac3", "dts": "dts", "amr": "amr",
    "mp4": "mp4", "mkv": "mkv", "webm": "webm", "mov": "mov", "avi": "avi",
    "mpeg": "mpg", "ts": "ts", "flv": "flv", "wmv": "wmv", "3gp": "3gp",
    "ogv": "ogv",
}

# Etiquetas curtas de contêiner usadas em filtros e agrupamentos
CONTAINER_FAMILY = {
    "mp3": "MP3", "m4a": "MPEG-4", "adts": "AAC", "flac": "FLAC", "ogg": "Ogg",
    "opus": "Ogg", "wav": "WAV", "aiff": "AIFF", "caf": "CAF", "wma": "ASF",
    "mka": "Matroska", "ac3": "AC-3", "eac3": "E-AC-3", "dts": "DTS",
    "amr": "AMR", "mp4": "MPEG-4", "mkv": "Matroska", "webm": "WebM",
    "mov": "QuickTime", "avi": "AVI", "mpeg": "MPEG-PS", "ts": "MPEG-TS",
    "flv": "FLV", "wmv": "ASF", "3gp": "3GPP", "ogv": "Ogg",
}

# Extensão -> contêiner de entrada (para indicar o formato de origem)
EXT_TO_CONTAINER: dict[str, str] = {}
for _key, _container in CONTAINERS.items():
    if _container.kind == "copy":
        continue
    for _ext in _container.audio_exts:
        if _container.kind == "audio":
            EXT_TO_CONTAINER.setdefault(_ext, _key)
for _ext, _key in (("ogg", "ogg"), ("oga", "ogg"), ("opus", "opus"),
                   ("aac", "adts"), ("m4a", "m4a"), ("m4b", "m4a"),
                   ("aif", "aiff"), ("aifc", "aiff"), ("wav", "wav"),
                   ("flac", "flac"), ("mp3", "mp3"), ("wma", "wma")):
    EXT_TO_CONTAINER.setdefault(_ext, _key)

# Tipos de arquivo de ENTRADA aceitos
INPUT_AUDIO_EXT = {
    "mp3", "mp2", "m4a", "m4b", "m4r", "aac", "flac", "ogg", "oga", "opus", "wav",
    "aiff", "aif", "aifc", "alac", "wma", "ac3", "eac3", "dts", "amr", "caf",
    "mka", "ape", "wv", "tta", "spx", "mpc", "au", "snd", "ra", "w64", "asf",
    "dsf", "dff", "aax", "oma", "aa", "thd",
}
INPUT_VIDEO_EXT = {
    "mp4", "mkv", "mov", "avi", "webm", "mpg", "mpeg", "m2v", "ts", "mts",
    "m2ts", "flv", "wmv", "3gp", "3g2", "ogv", "vob", "m4v", "f4v", "divx",
    "rm", "rmvb", "mxf", "wtv", "dav", "mod", "tod", "m2p", "mpv",
}
INPUT_EXT = INPUT_AUDIO_EXT | INPUT_VIDEO_EXT

INPUT_CODEC_LABEL = {
    "aac": "AAC", "mp3": "MP3", "ac3": "AC-3", "eac3": "E-AC-3", "flac": "FLAC",
    "alac": "ALAC", "opus": "Opus", "vorbis": "Vorbis", "pcm_s16le": "PCM 16-bit",
    "pcm_s24le": "PCM 24-bit", "pcm_s32le": "PCM 32-bit", "pcm_f32le": "PCM float",
    "pcm_s16be": "PCM 16-bit BE", "pcm_s24be": "PCM 24-bit BE",
    "pcm_alaw": "A-law", "pcm_mulaw": "µ-law", "dts": "DTS", "wma": "WMA",
    "wmav1": "WMA v1", "wmav2": "WMA v2", "mp2": "MP2", "amr_nb": "AMR-NB",
    "amr_wb": "AMR-WB", "h264": "H.264", "hevc": "H.265", "av1": "AV1",
    "vp9": "VP9", "vp8": "VP8", "mpeg4": "MPEG-4", "mpeg2video": "MPEG-2",
    "mjpeg": "JPEG", "prores": "ProRes", "ffv1": "FFV1", "theora": "Theora",
    "wmv2": "WMV2", "h263": "H.263", "png": "PNG", "flv1": "Sorenson",
    "dnxhd": "DNxHD", "rawvideo": "RAW",
}

LOSSY_INPUT = {"aac", "mp3", "ac3", "eac3", "opus", "vorbis", "dts", "wma",
               "wmav1", "wmav2", "mp2", "amr_nb", "amr_wb"}

# ---------------------------------------------------------------------------
# Perfis prontos
# ---------------------------------------------------------------------------


def builtin_profiles() -> list[dict]:
    """Perfis de fábrica (somente leitura; podem ser duplicados e editados)."""

    def prof(pid: str, name: str, kind: str, container: str, description: str,
             audio: dict | None = None, video: dict | None = None,
             container_auto: bool = False) -> dict:
        return {
            "id": pid, "name": name, "kind": kind, "container": container,
            "description": description, "builtin": True,
            "audio": audio or {}, "video": video or {},
            "container_auto": container_auto,
        }

    return [
        prof("music_light", "Música leve", "audio", "mp3",
             "MP3 CBR 192 kbps — compatível com praticamente tudo",
             audio={"codec": "libmp3lame", "mode": "cbr", "bitrate": "192k"}),
        prof("music_hq", "Música alta qualidade", "audio", "m4a",
             "AAC VBR q3 em M4A (~190-230 kbps)",
             audio={"codec": "aac", "mode": "vbr", "quality": 3}),
        prof("music_lossless", "Música sem perdas", "audio", "flac",
             "FLAC — evita novas perdas; não recupera áudio já comprimido",
             audio={"codec": "flac", "mode": "cbr", "compression_level": 5}),
        prof("compact", "Arquivo compacto", "audio", "opus",
             "Opus 96 kbps — ótima relação qualidade/tamanho",
             audio={"codec": "libopus", "mode": "cbr", "bitrate": "96k"}),
        prof("apple", "Compatibilidade Apple", "audio", "m4a",
             "M4A + AAC 256 kbps",
             audio={"codec": "aac", "mode": "cbr", "bitrate": "256k"}),
        prof("video_fhd", "Vídeo Full HD", "video", "mp4",
             "H.264 CRF 23, até 1080p, AAC 192 kbps",
             video={"codec": "libx264", "mode": "crf", "quality": 23,
                    "preset": "medium", "resolution": "1920x1080"},
             audio={"codec": "aac", "mode": "cbr", "bitrate": "192k"}),
        prof("video_economy", "Vídeo econômico", "video", "mp4",
             "H.265 CRF 28, até 1080p, AAC 128 kbps",
             video={"codec": "libx265", "mode": "crf", "quality": 28,
                    "preset": "medium", "resolution": "1920x1080"},
             audio={"codec": "aac", "mode": "cbr", "bitrate": "128k"}),
        prof("video_modern", "Vídeo moderno", "video", "mkv",
             "AV1 (SVT) CRF 35, até 1080p, Opus 128 kbps",
             video={"codec": "libsvtav1", "mode": "crf", "quality": 35,
                    "preset": "8", "resolution": "1920x1080"},
             audio={"codec": "libopus", "mode": "cbr", "bitrate": "128k"}),
        prof("archive", "Arquivamento", "video", "mkv",
             "MKV com vídeo/áudio sem perdas (FFV1 + FLAC quando disponíveis)",
             video={"codec": "ffv1", "mode": "crf", "quality": 5},
             audio={"codec": "flac", "mode": "cbr"}),
        prof("extract_audio", "Extrair áudio original", "audio", "copy",
             "Copia a faixa de áudio sem recodificar em um contêiner compatível",
             audio={"codec": "copy", "mode": "cbr"}, container_auto=True),
    ]
