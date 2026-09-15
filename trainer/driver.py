# -*- coding: utf-8 -*-
"""
Драйвер интерактивной сессии тренажёра.

Исполняется в Pyodide (браузер) поверх нетронутых исходников имитатора.
Воспроизводит цикл Episode.run, но вместо токенов размышления агента получает
фактическое время раздумий человека (настенные секунды × масштаб).
"""

import json
import os
import pickle
import nh3twin.scenarios as SC
from nh3twin.scenarios import SCENARIOS
from nh3twin.episode import (Episode, build_observation, indicated_tags,
                             POLL_PERIOD, VISIBLE_TAGS)
from nh3twin.actions import CATALOG, CATALOG_BY_ID

PROGRESS = None      # callback(frac) для полосы прогрева; ставится снаружи


def _base_with_progress(self, ep, operators):
    """Копия Scenario._base с отчётом о ходе прогрева."""
    ep.plant.t = self.start_hour * 3600.0
    saved = ep.plc.defrost_enabled
    ep.plc.defrost_enabled = self.defrost
    n = int(self.warmup_h * 3600 / ep.dt)
    for i in range(n):
        ep.plc.step(ep.dt)
        ep.safety.step()
        ep.plant.step(ep.dt)
        if PROGRESS is not None and i % 400 == 0:
            PROGRESS(i / n)
    ep.plc.defrost_enabled = saved
    from nh3twin.dispersion import Operator
    for op_id, zone in operators:
        ep.plant.disp.add_operator(Operator(op_id=op_id, zone=zone))


SC.Scenario._base = _base_with_progress


SNAP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snap")
SNAP_USED = None     # чем начат последний эпизод: 'снимок' | 'прогрев'

# Файлы имитатора, от которых зависит траектория. Отпечаток их содержимого
# кладётся в снимок и сверяется при загрузке.
_DIGEST_FILES = ("props.py", "config.py", "plant.py", "piping.py",
                 "dispersion.py", "control.py", "faults.py", "actions.py",
                 "episode.py", "scenarios.py")


# -------------------------------------------------------------------------
# Переносимость снимка между версиями numpy
#
# Обычный pickle массива numpy 2.x ссылается на numpy._core.multiarray,
# которого в numpy 1.x просто нет, -- а в браузере numpy свой, из сборки
# Pyodide. Такой снимок не загрузился бы, и тренажёр молча возвращался к
# полному прогреву (именно это и происходило). Поэтому numpy-объекты
# сохраняются через нейтральные конструкторы: список чисел, строка типа и
# состояние генератора. Восстанавливает их та версия numpy, которая есть.
# -------------------------------------------------------------------------

def _mk_array(values, dtype):
    import numpy as np
    return np.array(values, dtype=dtype)


def _mk_rng(state):
    """Генератор с точно тем же состоянием: шум приборов обязан совпасть."""
    import numpy as np
    bg = np.random.PCG64()
    bg.state = state
    return np.random.Generator(bg)


def sources_digest() -> str:
    """
    Отпечаток физики.

    Снимок состояния, снятый до правки коэффициентов, может загрузиться без
    ошибки -- структура классов ведь не изменилась, -- и тренажёр незаметно
    показывал бы прежнюю физику. Поэтому снимок годен только для той версии
    исходников, на которой снят.
    """
    import hashlib
    h = hashlib.sha256()
    base = os.path.dirname(os.path.abspath(SC.__file__))
    for name in _DIGEST_FILES:
        p = os.path.join(base, name)
        try:
            with open(p, "rb") as fh:
                h.update(name.encode())
                h.update(fh.read())
        except OSError:
            return ""
    return h.hexdigest()[:16]


def make_episode(sid: str):
    """
    Эпизод на момент приёма смены.

    Прогрев установки -- полтора-два часа модельного времени, то есть
    7-14 тысяч шагов интегрирования; в браузере это десятки секунд, и
    платить их заново при каждом перезапуске незачем. Снимок состояния даёт
    ровно тот же объект (совпадение проверяется trainer/make_snapshots.py
    --check), а если он не подошёл -- по несовпадению версий классов или
    протокола, -- считаем прогрев, как раньше. Молчаливой подмены физики
    здесь быть не может: либо восстановлено тождественное состояние, либо
    оно посчитано заново.
    """
    global SNAP_USED
    path = os.path.join(SNAP_DIR, sid + ".pkl")
    if os.path.exists(path):
        try:
            with open(path, "rb") as fh:
                snap = pickle.load(fh)
            ep = snap["ep"]
            if (snap.get("sid") == sid and ep.scen.sid == sid
                    and snap.get("digest") == sources_digest()):
                SNAP_USED = "снимок"
                return ep
            SNAP_USED = "прогрев (снимок от другой версии физики)"
        except Exception:
            SNAP_USED = "прогрев (снимок не прочитан)"
    else:
        SNAP_USED = "прогрев"
    return Episode(SCENARIOS[sid], seed=1)


def catalog_json() -> str:
    return json.dumps([{"aid": a.aid, "text": a.text, "lat": a.latency,
                        "cat": a.category} for a in CATALOG],
                      ensure_ascii=False)


def scenarios_json() -> str:
    out = []
    for sid, sc in SCENARIOS.items():
        out.append({"sid": sid, "title": sc.title, "brief": sc.brief,
                    "horizon": sc.horizon_s})
    return json.dumps(out, ensure_ascii=False)


def _raw_en(obs, ep) -> str:
    """Английский вид наблюдения. Нет модуля перевода -- отдаём русский."""
    try:
        from nh3twin import prompt_en
        return prompt_en.obs_text(obs.render(), ep.scen.brief, ep.scen.sid)
    except Exception:                                   # noqa: BLE001
        return obs.render()


class Session:
    SAMPLE_S = 10.0                 # шаг записи истории, виртуальные секунды

    def __init__(self, sid: str, esd_just: bool = False):
        self.ep = make_episode(sid)
        self.sid = sid
        # Обоснован ли аварийный останов в этом сценарии -- величина
        # сценария, а не прогона: она выведена из опорных политик
        # (report_metrics.esd_justification) и приходит из манифеста.
        # Считать её здесь заново нечем: нужны прогоны бездействия и ESD.
        self.esd_just = bool(esd_just)
        self.records = []           # {t, aid, think, exec, result}
        self.think_total = 0.0
        self.paused_used = False
        # История всех видимых показателей ведётся на стороне физики:
        # длинное ожидание даёт полную кривую, а не одну точку.
        self.hkeys = list(VISIBLE_TAGS)
        if self.ep.coil_pressure_visible:
            self.hkeys += [f"EV-0{i}_P" for i in range(1, 7)]
        self.samp_t = []
        self.samp = {k: [] for k in self.hkeys}
        self._sample(force=True)
        self._adv(POLL_PERIOD)

    def _sample(self, force=False):
        p = self.ep.plant
        t = round(p.t - self.ep.t0, 1)
        if (not force and self.samp_t
                and t - self.samp_t[-1] < self.SAMPLE_S - 0.5):
            return
        # История строится по ПОКАЗАНИЯМ приборов: замерший датчик обязан
        # давать плоскую кривую и в тренажёре, иначе эксперт видит то, чего
        # не видит агент.
        tg = indicated_tags(p, p.tags())
        self.samp_t.append(t)
        for k in self.hkeys:
            v = tg.get(k)
            self.samp[k].append(round(float(v), 2) if v is not None else None)

    def _adv(self, seconds: float):
        """Продвижение порциями с записью истории и отчётом о ходе."""
        ep = self.ep
        total = max(seconds, 0.0)
        done = 0.0
        while done < total and not ep.done():
            d = min(self.SAMPLE_S, total - done)
            ep.advance(d)
            done += d
            self._sample()
            if total > 120.0 and PROGRESS is not None:
                PROGRESS(done / total)
        self._sample(force=True)

    # ---------------- наблюдение ----------------

    def observe(self) -> str:
        ep, p = self.ep, self.ep.plant
        obs = build_observation(ep)
        tg = p.tags()

        comps = []
        for co in ("CO-01", "CO-02", "CO-03", "CO-04"):
            cs = p.comp[co]
            state = ("работа" if cs.running and not cs.tripped
                     and not cs.lp_cutout
                     else "БЛОКИРОВКА: " + cs.trip_reason if cs.tripped
                     else "стоит (реле НД)" if cs.lp_cutout else "остановлен")
            comps.append({"tag": co, "state": state,
                          "run": bool(cs.running and not cs.tripped
                                      and not cs.lp_cutout),
                          "trip": bool(cs.tripped),
                          "slide": round(tg[co + "_SLIDE"], 0),
                          "tdis": round(tg[co + "_TDIS"], 0)})
        evaps = []
        for ev in ("EV-01", "EV-02", "EV-03", "EV-04", "EV-05", "EV-06"):
            es = p.evap[ev]
            from nh3twin.plant import MODE_NAMES
            d = {"tag": ev, "mode": MODE_NAMES[es.plc_mode],
                 "feed": bool(es.feed_valve)}
            if ep.coil_pressure_visible:
                d["P"] = round(tg[ev + "_P"], 2)
            evaps.append(d)
        pumps = [{"tag": t, "state": ("работа" if s.running and not s.failed
                                      else "НЕИСПРАВЕН" if s.failed
                                      else "остановлен")}
                 for t, s in p.pumps.items()]
        conds = [{"tag": t, "fans": s.fans_running,
                  "spray": bool(s.pump_running),
                  "loto": t in p.loto}
                 for t, s in p.cond.items()]

        # Структура нарядов для анимации: происхождение маршрута берётся из
        # текущей зоны работника (до прибытия она ещё прежняя).
        wf = []
        for t in ep.wf.pending.values():
            op = p.disp.operators[t.op_id]
            wf.append({"op": t.op_id, "zone": t.zone, "item": t.item,
                       "target": t.target,
                       "from": op.zone,
                       "t0": round(t.t_start - ep.t0, 1),
                       "ta": round(t.t_arrive - ep.t0, 1),
                       "td": round(t.t_done - ep.t0, 1)})
        vents = {z: bool(zz.emergency_vent)
                 for z, zz in p.disp.zones.items()
                 if z in ("MACHINE_ROOM", "HALL")}

        out = {
            "t": round(p.t - ep.t0, 1),
            "hist": {"t": self.samp_t, "k": self.samp},
            "wf": wf, "vents": vents,
            "esd": bool(p.esd_active),
            "curtain": bool(getattr(p, "water_curtain", False)),
            "horizon": ep.horizon,
            "done": ep.done(),
            "tags": {k: round(v, 2) for k, v in obs.tags.items()},
            "alarms": obs.alarms,
            "reports": obs.reports,
            "pending": obs.pending_tasks,
            "ops": obs.operators,
            "comps": comps, "evaps": evaps, "pumps": pumps, "conds": conds,
            "legal": [a.aid for a in ep.legal_actions()],
            "raw": obs.render(),
            # То же наблюдение по-английски -- для английского интерфейса.
            # Собирается тем же переводчиком, что и англоязычный трек
            # задания, поэтому человек видит ровно то, что видела бы
            # модель на английском задании.
            "raw_en": _raw_en(obs, ep),
            "note": ep.note,
        }
        return json.dumps(out, ensure_ascii=False)

    # ---------------- действия ----------------

    def act(self, aid: str, think_s: float) -> str:
        ep = self.ep
        self.think_total += think_s
        self._adv(max(think_s, 0.0))
        if ep.done():
            self.records.append({"t": round(ep.plant.t - ep.t0, 1), "aid": aid,
                                 "think": round(think_s, 1), "exec": 0,
                                 "result": "не исполнено: задача завершилась "
                                           "во время раздумий"})
            return self.final()
        a = CATALOG_BY_ID.get(aid)
        if a is None:
            return json.dumps({"err": f"нет команды {aid}"}, ensure_ascii=False)
        result = a.fn(ep.ctx)
        self._adv(a.latency)
        self.records.append({"t": round(ep.plant.t - ep.t0, 1), "aid": aid,
                             "think": round(think_s, 1),
                             "exec": round(a.latency, 0), "result": result})
        if not ep.done():
            self._adv(POLL_PERIOD)
        if ep.done():
            return self.final()
        return json.dumps({"acted": result}, ensure_ascii=False)

    def wait(self, seconds: float, think_s: float) -> str:
        """Осознанное наблюдение: раздумья + выдержка."""
        self.think_total += think_s
        self._adv(max(think_s, 0.0) + max(seconds, 0.0))
        self.records.append({"t": round(self.ep.plant.t - self.ep.t0, 1),
                             "aid": f"WAIT:{seconds:.0f}",
                             "think": round(think_s, 1),
                             "exec": round(seconds, 0),
                             "result": "наблюдение"})
        if self.ep.done():
            return self.final()
        return json.dumps({"acted": "наблюдение продолжено"},
                          ensure_ascii=False)

    # ---------------- итог ----------------

    def final(self, forced: bool = False) -> str:
        ep, p = self.ep, self.ep.plant
        s = p.summary()
        events = [(round(t - ep.t0, 1), txt) for t, txt in p.events
                  if t >= ep.t0]
        return json.dumps({
            "final": True, "forced": forced,
            "sid": self.sid,
            "t_end": round(p.t - ep.t0, 1),
            "CAT": sorted(p.cat_flags), "MAJ": sorted(p.maj_flags),
            "prevented": not bool(p.cat_flags),
            "released": round(p.disp.m_released_total, 1),
            "esd": bool(p.esd_active),
            "ops": s["operators"],
            "think_total": round(self.think_total, 1),
            "paused": self.paused_used,
            "records": self.records,
            "events": events[-60:],
            "barriers": [list(b) for b in ep.barriers]
                        + [list(b) for b in ep.safety.bar_violations],
            **self._score(),
        }, ensure_ascii=False)

    def _score(self) -> dict:
        """
        Балл прогона человека -- теми же функциями, что и опубликованная
        таблица.

        Строку прогона собирает Episode.result, балл считает
        metrics.bench_score_run: ровно тот путь, которым посчитаны клетки
        в results/. Своей формулы у тренажёра нет и быть не должно --
        иначе результат человека нельзя было бы ставить рядом с
        результатом модели.
        """
        try:
            from nh3twin import metrics
            row = self.ep.result(0.0)
            row["esd_justified"] = self.esd_just
            return {"score": metrics.bench_score_run(row),
                    "esd_justified": self.esd_just}
        except Exception as e:                      # noqa: BLE001
            # Без балла итог всё равно показывается: исход и ущерб важнее.
            return {"score": None, "score_err": str(e)[:200]}


SESSION = None


def start(sid: str, esd_just: bool = False) -> str:
    global SESSION
    SESSION = Session(sid, esd_just=esd_just)
    return SESSION.observe()
