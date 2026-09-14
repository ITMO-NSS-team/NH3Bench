# -*- coding: utf-8 -*-
"""
Снимки задач на момент приёма смены.

    py trainer/make_snapshots.py            # собрать снимки
    py trainer/make_snapshots.py --check    # проверить совпадение с прогревом

Зачем. Каждая задача начинается с выхода установки на режим: полтора-два
часа модельного времени, 7-14 тысяч шагов интегрирования. На CPython это
20-42 с, в браузере втрое-впятеро дольше, и это время тратится заново при
каждом «смотреть заново» -- а на стенде посетитель столько не ждёт.

Состояние эпизода после прогрева целиком укладывается в 42 КБ и
восстанавливается за миллисекунду. Физика при этом не меняется: снимок --
это ровно тот объект, который дал бы прогрев, и проверка --check убеждается,
что продолжение расчёта из снимка совпадает с продолжением из прогрева
шаг за шагом.

Снимок зависит от структуры классов имитатора. Если она изменилась, старый
снимок загрузить не удастся -- тогда драйвер молча считает прогрев, как
раньше, и достаточно перегенерировать снимки. Поэтому в них пишется версия
формата и коммит.
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import pickle
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

sys.path.insert(0, os.path.join(ROOT, "trainer"))

from nh3twin.episode import Episode                                 # noqa: E402
from nh3twin.scenarios import SCENARIOS                             # noqa: E402
# Отпечаток физики считает драйвер -- той же функцией, которой потом сверяет.
from driver import (sources_digest, SNAP_DIR,                       # noqa: E402
                    _mk_array, _mk_rng)

# Каталог берётся у драйвера, а не задаётся здесь: иначе снимки пишутся в
# одно место, а ищутся в другом -- и локально путь снимка не проверить.
OUT_DIR = SNAP_DIR
# Пятый протокол есть и в CPython 3.11, и в Python 3.12 внутри Pyodide.
PROTO = 5
VERSION = 1


class _PortablePickler(pickle.Pickler):
    """
    Снимок, не зависящий от версии numpy.

    Внутренние представления numpy между 1.x и 2.x несовместимы по именам
    модулей, а numpy в браузере свой. Поэтому массив пишется списком чисел,
    скаляр -- обычным float, генератор -- своим состоянием; собирает их
    обратно driver уже средствами той numpy, что есть.
    """

    def reducer_override(self, obj):
        import numpy as np
        if isinstance(obj, np.ndarray):
            return (_mk_array, (obj.tolist(), str(obj.dtype)))
        if isinstance(obj, np.random.Generator):
            return (_mk_rng, (obj.bit_generator.state,))
        if isinstance(obj, np.generic):
            v = obj.item()
            return (float, (v,)) if isinstance(v, float) else (int, (v,))
        return NotImplemented


def build_one(sid: str) -> bytes:
    ep = Episode(SCENARIOS[sid], seed=1)
    buf = io.BytesIO()
    _PortablePickler(buf, protocol=PROTO).dump(
        {"v": VERSION, "sid": sid, "ep": ep, "digest": sources_digest()})
    return buf.getvalue()


def build(sids=None) -> dict:
    os.makedirs(OUT_DIR, exist_ok=True)
    out = {}
    for sid in (sids or list(SCENARIOS)):
        t0 = time.time()
        blob = build_one(sid)
        path = os.path.join(OUT_DIR, sid + ".pkl")
        with open(path, "wb") as fh:
            fh.write(blob)
        out[sid] = blob
        print(f"  {sid}: {len(blob) / 1024:6.0f} КБ "
              f"(прогрев занял {time.time() - t0:5.1f} с)")
    return out


def portability(sid: str) -> list:
    """
    Ссылки, которые могут не существовать в другой версии numpy.

    Проверка нужна потому, что непереносимый снимок не ломается заметно: он
    просто не загружается в браузере, драйвер уходит на прогрев, и всё
    выглядит как «почему-то долго».
    """
    import io as _io
    import pickletools
    bad = []
    with open(os.path.join(OUT_DIR, sid + ".pkl"), "rb") as fh:
        blob = fh.read()
    for op, arg, _pos in pickletools.genops(_io.BytesIO(blob)):
        if not isinstance(arg, str):
            continue
        # Внутренности numpy: приватные модули и всё, что связано с random.
        if (arg.startswith("numpy._") or arg.startswith("numpy.core")
                or arg.startswith("numpy.random")):
            bad.append(arg)
    return sorted(set(bad))


def check(sids=None) -> int:
    """
    Снимок обязан давать ту же траекторию, что прогрев. Иначе просмотр записей
    показывал бы не тот эпизод, который был у модели, -- незаметно и потому
    опасно.
    """
    import numpy as np
    bad = 0
    for sid in (sids or list(SCENARIOS)):
        path = os.path.join(OUT_DIR, sid + ".pkl")
        if not os.path.exists(path):
            print(f"  {sid}: снимка нет"); bad += 1; continue
        with open(path, "rb") as fh:
            snap = pickle.load(fh)
        a = snap["ep"]
        b = Episode(SCENARIOS[sid], seed=1)          # честный прогрев
        d0 = float(np.max(np.abs(a.plant.y - b.plant.y)))
        ta = abs(a.plant.t - b.plant.t)
        # и продолжение: пять минут задачи вперёд
        a.advance(300.0); b.advance(300.0)
        d1 = float(np.max(np.abs(a.plant.y - b.plant.y)))
        refs = portability(sid)
        ok = d0 < 1e-9 and ta < 1e-9 and d1 < 1e-9 and not refs
        if not ok:
            bad += 1
        print(f"  {sid}: расхождение на старте {d0:.3e}, "
              f"через 300 с {d1:.3e}, "
              f"непереносимых ссылок {len(refs)} -> "
              f"{'совпало' if ok else 'НЕГОДЕН'}")
        for r in refs[:4]:
            print(f"      зависит от версии numpy: {r}")
    return bad


def as_files() -> dict:
    """Снимки в виде {имя: base64} для встраивания в HTML тренажёра."""
    out = {}
    if not os.path.isdir(OUT_DIR):
        return out
    for name in sorted(os.listdir(OUT_DIR)):
        if not name.endswith(".pkl"):
            continue
        with open(os.path.join(OUT_DIR, name), "rb") as fh:
            out["snap/" + name] = base64.b64encode(fh.read()).decode()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default="")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    sids = [s for s in args.scenarios.split(",") if s] or None
    if args.check:
        sys.exit(1 if check(sids) else 0)
    print("сборка снимков (каждый требует полного прогрева):")
    build(sids)
    print("\nпроверка:")
    sys.exit(1 if check(sids) else 0)


if __name__ == "__main__":
    main()
