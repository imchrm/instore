"""Разбор и проверка API-ключей.

Формат конфига ``API_KEYS`` - пары ``имя:ключ`` через запятую. Из имени
формируется стабильный ``key_id``, к которому привязаны задачи и cookies.
Значения ключей нигде не логируются: ``repr`` реестра их не раскрывает.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    """Привести имя ключа к стабильному ``key_id`` из ``[a-z0-9_]``."""
    return _SLUG_RE.sub("_", name.strip().lower()).strip("_")


@dataclass(frozen=True, slots=True)
class ApiKeyRegistry:
    """Неизменяемый реестр соответствия ``ключ -> key_id``."""

    _by_key: Mapping[str, str] = field(repr=False)

    @classmethod
    def from_config(cls, raw: str) -> ApiKeyRegistry:
        """Разобрать строку ``API_KEYS`` вида ``имя1:ключ1,имя2:ключ2``.

        Пустые сегменты пропускаются. Дубликаты ключей или ``key_id``, а также
        отсутствие валидных пар считаются ошибкой конфигурации.
        """
        by_key: dict[str, str] = {}
        seen_ids: set[str] = set()
        for segment in raw.split(","):
            item = segment.strip()
            if not item:
                continue
            name, separator, key = item.partition(":")
            name = name.strip()
            key = key.strip()
            if not separator or not name or not key:
                msg = "API_KEYS: ожидается формат 'имя:ключ' через запятую"
                raise ValueError(msg)
            key_id = _slugify(name)
            if not key_id:
                msg = f"API_KEYS: имя {name!r} даёт пустой key_id"
                raise ValueError(msg)
            if key_id in seen_ids:
                msg = f"API_KEYS: дублирующийся key_id {key_id!r}"
                raise ValueError(msg)
            if key in by_key:
                msg = "API_KEYS: дублирующийся ключ"
                raise ValueError(msg)
            seen_ids.add(key_id)
            by_key[key] = key_id
        if not by_key:
            msg = "API_KEYS: не задан ни один ключ"
            raise ValueError(msg)
        return cls(dict(by_key))

    def key_id_for(self, key: str) -> str | None:
        """Вернуть ``key_id`` для ключа или ``None``, если ключ неизвестен."""
        return self._by_key.get(key)

    def __len__(self) -> int:
        return len(self._by_key)

    def __contains__(self, key: str) -> bool:
        return key in self._by_key
