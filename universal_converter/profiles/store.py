"""Perfis de conversão: prontos, personalizados, persistência e aplicação."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import asdict, dataclass, field

from ..core.jsonio import read_json, write_json_atomic
from ..core.util import app_data_dir
from ..media.codecs import builtin_profiles
from ..media.models import AudioSettings, ConversionConfig, VideoSettings


@dataclass
class Profile:
    id: str
    name: str
    kind: str = "audio"              # audio | video
    container: str = "mp3"
    description: str = ""
    builtin: bool = False
    audio: AudioSettings = field(default_factory=AudioSettings)
    video: VideoSettings = field(default_factory=VideoSettings)
    container_auto: bool = False

    def to_dict(self, include_id: bool = True) -> dict:
        data = {
            "name": self.name, "kind": self.kind, "container": self.container,
            "description": self.description, "builtin": self.builtin,
            "audio": self.audio.to_dict(), "video": self.video.to_dict(),
            "container_auto": self.container_auto,
        }
        if include_id:
            data["id"] = self.id
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        return cls(
            id=data.get("id") or uuid.uuid4().hex[:10],
            name=data.get("name", "Perfil"),
            kind=data.get("kind", "audio"),
            container=data.get("container", "mp3"),
            description=data.get("description", ""),
            builtin=bool(data.get("builtin")),
            audio=AudioSettings.from_dict(data.get("audio")),
            video=VideoSettings.from_dict(data.get("video")),
            container_auto=bool(data.get("container_auto")),
        )

    def config(self) -> ConversionConfig:
        return ConversionConfig(kind=self.kind, container=self.container,
                                audio=AudioSettings.from_dict(self.audio.to_dict()),
                                video=VideoSettings.from_dict(self.video.to_dict()))


class ProfileStore:
    """Catálogo de perfis (embutidos + do usuário), salvo em JSON."""

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(app_data_dir(), "profiles.json")
        self.user: list[Profile] = []
        self.builtin: list[Profile] = [Profile.from_dict(p) for p in builtin_profiles()]
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        data = read_json(self.path, default={}) or {}
        raw = data.get("profiles", []) if isinstance(data, dict) else []
        self.user = [Profile.from_dict(p) for p in raw if isinstance(p, dict)]
        self.user = [p for p in self.user if not p.builtin]

    def save(self) -> bool:
        data = {
            "version": 1,
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "profiles": [p.to_dict() for p in self.user],
        }
        folder = os.path.dirname(self.path)
        if folder and not os.path.isdir(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError:
                return False
        return write_json_atomic(self.path, data)

    # ------------------------------------------------------------------
    def all(self) -> list[Profile]:
        return list(self.user) + list(self.builtin)

    def find(self, profile_id: str) -> Profile | None:
        for profile in self.user + self.builtin:
            if profile.id == profile_id:
                return profile
        return None

    def upsert(self, profile: Profile) -> None:
        profile.builtin = False
        for index, existing in enumerate(self.user):
            if existing.id == profile.id:
                self.user[index] = profile
                break
        else:
            self.user.append(profile)
        self.save()

    def duplicate(self, profile: Profile, new_name: str | None = None) -> Profile:
        clone = Profile.from_dict(profile.to_dict(include_id=False))
        clone.id = uuid.uuid4().hex[:10]
        clone.builtin = False
        clone.name = new_name or self.unique_name(f"{profile.name} (cópia)")
        self.user.append(clone)
        self.save()
        return clone

    def delete(self, profile_id: str) -> bool:
        for index, profile in enumerate(self.user):
            if profile.id == profile_id:
                del self.user[index]
                self.save()
                return True
        return False

    def unique_name(self, base: str) -> str:
        names = {p.name for p in self.all()}
        if base not in names:
            return base
        counter = 2
        while f"{base} {counter}" in names:
            counter += 1
        return f"{base} {counter}"

    # ------------------------------------------------------------------
    @staticmethod
    def from_config(name: str, config: ConversionConfig, description: str = "") -> Profile:
        return Profile(
            id=uuid.uuid4().hex[:10], name=name, kind=config.kind,
            container=config.container, description=description,
            audio=AudioSettings.from_dict(config.audio.to_dict()),
            video=VideoSettings.from_dict(config.video.to_dict()),
        )

    @staticmethod
    def export_file(path: str, profiles: list[Profile]) -> bool:
        payload = {"version": 1, "profiles": [p.to_dict() for p in profiles]}
        return write_json_atomic(path, payload)

    @staticmethod
    def import_file(path: str) -> list[Profile]:
        data = read_json(path, default=None)
        if not data:
            return []
        raw = data.get("profiles") if isinstance(data, dict) else data
        if not isinstance(raw, list):
            return []
        profiles = []
        for item in raw:
            if isinstance(item, dict):
                item = dict(item)
                item["id"] = uuid.uuid4().hex[:10]
                item["builtin"] = False
                profiles.append(Profile.from_dict(item))
        return profiles
