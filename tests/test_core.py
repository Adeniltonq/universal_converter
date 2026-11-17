"""Testes automatizados (biblioteca padrão ``unittest``; rode com
``python -m unittest discover -s tests``).

Os testes de mídia geram arquivos curtos com o FFmpeg local e são ignorados
automaticamente quando ele não está disponível.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from universal_converter.core.util import (  # noqa: E402
    fmt_bitrate, fmt_duration, fmt_size, is_subpath, sanitize_filename,
)
from universal_converter.filesystem.output import (  # noqa: E402
    OutputPolicy, OutputResolver,
)
from universal_converter.filesystem.scanner import ScanOptions, scan_folder  # noqa: E402
from universal_converter.media.command_builder import (  # noqa: E402
    parse_bitrate, parse_fps, parse_resolution,
)
from universal_converter.media.ffmpeg import FFmpegInfo  # noqa: E402
from universal_converter.media.analyzer import MediaAnalyzer  # noqa: E402
from universal_converter.media.catalog import CodecCatalog  # noqa: E402
from universal_converter.media.models import (  # noqa: E402
    AudioSettings, ConversionConfig, ConversionJob, MediaInfo, NamingTemplate,
    StreamInfo,
)
from universal_converter.naming.engine import (  # noqa: E402
    NamingContext, NamingEngine, validate_template,
)
from universal_converter.profiles.store import ProfileStore  # noqa: E402
from universal_converter.queue.store import JobStore  # noqa: E402


class UtilTests(unittest.TestCase):
    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename('a:b*c?.mp3'), "abc.mp3")
        self.assertEqual(sanitize_filename("CON.txt"), "CON_.txt")
        self.assertEqual(sanitize_filename("  espaço  .mp3 "), "espaço  .mp3")
        self.assertEqual(sanitize_filename(""), "arquivo")

    def test_formatting(self):
        self.assertEqual(fmt_duration(3725), "1:02:05")
        self.assertEqual(fmt_duration(59), "00:59")
        self.assertEqual(fmt_size(1536), "1.5 KB")
        self.assertEqual(fmt_bitrate(192000), "192 kbps")
        self.assertEqual(fmt_bitrate(None), "—")

    def test_is_subpath(self):
        with tempfile.TemporaryDirectory() as tmp:
            inner = os.path.join(tmp, "a", "b")
            os.makedirs(inner)
            self.assertTrue(is_subpath(inner, tmp))
            self.assertFalse(is_subpath(tmp, inner))


class ParsingTests(unittest.TestCase):
    def test_resolution(self):
        self.assertEqual(parse_resolution("1920x1080"), (1920, 1080))
        self.assertEqual(parse_resolution("1281x721"), (1280, 720))
        self.assertEqual(parse_resolution("1280xauto"), (1280, None))
        self.assertIsNone(parse_resolution("Manter original"))
        self.assertIsNone(parse_resolution("qualquer coisa"))

    def test_fps(self):
        self.assertEqual(parse_fps("23.976"), "24000/1001")
        self.assertEqual(parse_fps("30"), "30")
        self.assertIsNone(parse_fps("keep"))
        self.assertIsNone(parse_fps("-1"))

    def test_bitrate(self):
        self.assertEqual(parse_bitrate("192"), "192k")
        self.assertEqual(parse_bitrate("1.5M"), "1500k")
        self.assertEqual(parse_bitrate("96k"), "96k")
        self.assertIsNone(parse_bitrate("Automático"))


class NamingTests(unittest.TestCase):
    def setUp(self):
        info = MediaInfo(path="/midias/Sepultura/Isolation.mp3",
                         tags={"title": "Isolation", "artist": "Sepultura",
                               "album": "Roots", "date": "1996-02-20"})
        info.streams = [StreamInfo(index=0, type="audio", codec="mp3", channels=2)]
        config = ConversionConfig(kind="audio", container="ogg")
        self.context = NamingContext(path=info.path, info=info, config=config,
                                     index=3, tag="Sepultura", extension="ogg")
        self.engine = NamingEngine()

    def render(self, template: str, **kw) -> str:
        model = NamingTemplate(template=template, **kw)
        return self.engine.render(self.context, model)

    def test_documented_examples(self):
        self.assertEqual(self.render("{name}_{tag}", separator="_"),
                         "Isolation_Sepultura.ogg")
        self.assertEqual(self.render("{artist} - {title}"),
                         "Sepultura - Isolation.ogg")
        self.assertEqual(self.render("{album}/{index} - {title}"),
                         "Roots/3 - Isolation.ogg")
        self.assertEqual(self.render("{name}_converted_{codec}"),
                         "Isolation_converted_mp3.ogg")

    def test_tag_absent_does_not_leave_separator(self):
        self.assertEqual(self.render("{name}_{tag}", separator="_"),
                         "Isolation_Sepultura.ogg")
        other = NamingContext(path=self.context.path, info=self.context.info,
                              config=self.context.config, index=1, tag="",
                              extension="ogg")
        self.assertEqual(self.engine.render(other, NamingTemplate(
            template="{name}{separator}{tag}")), "Isolation.ogg")

    def test_numbering_case_and_sanitize(self):
        self.assertTrue(self.render("{name}", numbering=True).startswith("04 - "))
        self.assertEqual(self.render("{name}", case="upper"), "ISOLATION.ogg")
        self.assertIn("{separator}", "{separator}")
        self.assertIn("Isolation", self.engine.render(self.context,
                                                      NamingTemplate(template="{name}",
                                                                     suffix="beta")))

    def test_year_and_parent(self):
        self.assertEqual(self.render("{year}"), "1996.ogg")
        self.assertEqual(self.render("{parent}"), "Sepultura.ogg")

    def test_validate_template(self):
        used, unknown = validate_template("{name}_{bogus}")
        self.assertEqual(used, ["name"])
        self.assertEqual(unknown, ["{bogus}"])

    def test_deduplicate(self):
        path, collision = NamingEngine.deduplicate("a.mp3", {"a.mp3"}, lambda _p: False)
        self.assertTrue(collision)
        self.assertEqual(path, "a (1).mp3")


class ScannerTests(unittest.TestCase):
    def test_scan_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "Musicas")
            out = os.path.join(src, "convertidos")
            os.makedirs(os.path.join(src, "Sepultura"))
            os.makedirs(out)
            for rel in ("Isolation.flac", "Roots.mp3", "Sepultura/Show.mkv",
                        "Sepultura/nota.txt", "skip.mp3", "convertidos/antigo.ogg",
                        ".oculto.mp3"):
                open(os.path.join(src, rel), "w").close()
            result = scan_folder(src, ScanOptions(exclude_patterns=["skip*"],
                                                  output_dir=out))
            found = sorted(os.path.relpath(p, src) for p in result.files)
            self.assertEqual(found, ["Isolation.flac", "Roots.mp3", "Sepultura/Show.mkv"])
            flat = scan_folder(src, ScanOptions(recursive=False, output_dir=out,
                                                exclude_patterns=["skip*"]))
            self.assertEqual(sorted(os.path.basename(p) for p in flat.files),
                             ["Isolation.flac", "Roots.mp3"])

    def test_structure_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "Musicas")
            os.makedirs(os.path.join(src, "Sepultura"))
            resolver = OutputResolver(OutputPolicy(mode="folder",
                                                   folder=os.path.join(tmp, "Saida"),
                                                   source_root=src))
            folder = resolver.final_folder(os.path.join(src, "Sepultura", "Show.mkv"))
            self.assertEqual(folder, os.path.join(tmp, "Saida", "Sepultura"))

    def test_output_inside_source_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            resolver = OutputResolver(OutputPolicy(mode="folder",
                                                   folder=os.path.join(tmp, "saida"),
                                                   source_root=tmp))
            self.assertTrue(resolver.check_conflicts())


class StoreTests(unittest.TestCase):
    def test_jobs_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(os.path.join(tmp, "q.db"))
            job = ConversionJob(file="/tmp/a.mp3",
                                config=ConversionConfig(audio=AudioSettings(
                                    bitrate="128k", codec="libopus")))
            store.add_jobs([job])
            loaded = store.load_jobs()
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].config.audio.codec, "libopus")
            self.assertEqual(loaded[0].config.audio.bitrate, "128k")
            store.close()

    def test_profiles_builtin_and_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProfileStore(os.path.join(tmp, "profiles.json"))
            self.assertGreaterEqual(len(store.all()), 8)
            profile = store.find("music_light")
            self.assertIsNotNone(profile)
            clone = store.duplicate(profile, "Meu MP3")
            self.assertEqual(store.find(clone.id).name, "Meu MP3")
            self.assertFalse(store.find(clone.id).builtin)
            reloaded = ProfileStore(os.path.join(tmp, "profiles.json"))
            self.assertIsNotNone(reloaded.find(clone.id))


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@unittest.skipUnless(ffmpeg_available(), "FFmpeg não encontrado no PATH")
class MediaIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="umc_tests_")
        cls.ff = FFmpegInfo.locate()
        cls.ff.ensure_loaded()
        cls.catalog = CodecCatalog(cls.ff)
        cls.analyzer = MediaAnalyzer(cls.ff)
        cls.mp3 = cls._make(["-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                             "-metadata", "artist=Sepultura", "-c:a", "libmp3lame"],
                            "a.mp3")
        cls.mp4 = cls._make(["-f", "lavfi", "-i",
                             "testsrc=size=160x120:rate=10:duration=1",
                             "-f", "lavfi", "-i", "sine=frequency=300:duration=1",
                             "-c:v", "libx264", "-preset", "ultrafast",
                             "-pix_fmt", "yuv420p", "-c:a", "aac"], "b.mp4")

    @classmethod
    def _make(cls, args, name) -> str:
        path = os.path.join(cls.tmp, name)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", *args,
                        "-y", path], check=True)
        return path

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_analysis(self):
        info = self.analyzer.analyze(self.mp4)
        self.assertTrue(info.analyzed)
        self.assertTrue(info.is_video)
        self.assertIsNotNone(info.main_audio)
        self.assertEqual(info.main_audio.codec, "aac")
        self.assertEqual((info.main_video.width, info.main_video.height), (160, 120))
        self.assertAlmostEqual(info.duration or 0, 1.0, places=1)

    def test_container_compatibility(self):
        # opus não vai para MP3; MP3 não vai para WAV
        self.assertNotIn("libopus", [o.id for o in self.catalog.audio_options("mp3")])
        self.assertNotIn("libmp3lame", [o.id for o in self.catalog.audio_options("wav")])
        # extração sem recodificação de AAC do MP4
        info = self.analyzer.analyze(self.mp4)
        from universal_converter.media.command_builder import CommandBuilder
        builder = CommandBuilder(self.catalog)
        config = ConversionConfig(kind="audio", container="copy",
                                  audio=AudioSettings(codec="copy"))
        container = builder.effective_container(config, info)
        self.assertIn(container, ("adts", "m4a", "mka"))

    def test_quick_info_reads_tags_without_probe(self):
        path = self._make(["-f", "lavfi", "-i", "sine=frequency=500:duration=1",
                           "-metadata", "title=Título Ä", "-metadata", "artist=Sepultura",
                           "-metadata", "album=Roots", "-c:a", "libmp3lame",
                           "-id3v2_version", "3"], "tags.mp3")
        info = self.analyzer.quick_info(path)
        self.assertEqual(info.tag("title"), "Título Ä")
        self.assertEqual(info.tag("artist"), "Sepultura")
        self.assertEqual(info.tag("album"), "Roots")
        self.assertEqual(info.size, os.path.getsize(path))

    def test_convert_to_ogg(self):
        info = self.analyzer.analyze(self.mp3)
        from universal_converter.media.command_builder import CommandBuilder
        from universal_converter.media.runner import JobRunner
        builder = CommandBuilder(self.catalog, threads_per_job=1)
        target = os.path.join(self.tmp, "out.ogg")
        config = ConversionConfig(kind="audio", container="ogg",
                                  audio=AudioSettings(codec="libvorbis", mode="vbr",
                                                      quality=4))
        result = builder.build(config, info, self.mp3, target)
        self.assertTrue(result.ok, result.error)
        outcome = JobRunner(self.ff.ffmpeg).run(result.args, target, info.duration)
        self.assertTrue(outcome.success, outcome.message)
        converted = self.analyzer.analyze(target, use_cache=False)
        self.assertEqual(converted.main_audio.codec, "vorbis")

    def test_never_overwrite_source(self):
        info = self.analyzer.analyze(self.mp3)
        from universal_converter.media.command_builder import CommandBuilder
        builder = CommandBuilder(self.catalog)
        config = ConversionConfig(kind="audio", container="mp3",
                                  audio=AudioSettings(codec="libmp3lame"))
        before = os.stat(self.mp3).st_size
        result = builder.build(config, info, self.mp3, os.path.join(self.tmp, "x.mp3"))
        self.assertTrue(result.ok)
        from universal_converter.media.runner import JobRunner
        outcome = JobRunner(self.ff.ffmpeg).run(result.args, os.path.join(self.tmp,
                                                                          "x.mp3"),
                                                info.duration)
        self.assertTrue(outcome.success)
        self.assertEqual(os.stat(self.mp3).st_size, before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
