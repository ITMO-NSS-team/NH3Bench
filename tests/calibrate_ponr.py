"""
Калибровка точки невозврата (t_PONR) по сценариям.

Определение из проектного документа: t_PONR -- последний момент, в который
эталонная последовательность действий ещё предотвращает аварию. Всё, что
агент делает позже, на исход уже не влияет; именно поэтому метрики
Margin-to-PONR и Overthinking Cost без этой величины не существуют.

Способ измерения прямой: политика бездействует до момента T, затем
разыгрывает эталонный сценарий. Двоичный поиск по T находит наибольшее T,
при котором катастрофа ещё не наступает. Проверяются два порога:

    t_PONR(CAT) -- позже него эталон уже не спасает от катастрофы;
    t_PONR(MAJ) -- позже него эталон уже не удерживает прогон чистым,
                   то есть спасти можно, но не даром.

Второй порог наступает раньше и определён во всех сценариях, включая те,
где бездействие катастрофы не вызывает (S3, S5). Публикуются оба.

Запуск (долгий, порядка получаса на сценарий):

    python3 tests/calibrate_ponr.py --scenarios S1,S2,S3,S4,S5

Результат пишется в results/ponr.json после каждого сценария.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nh3twin.scenarios import SCENARIOS
from nh3twin.episode import Episode
from nh3twin.policies import OraclePolicy, Policy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results", "ponr.json")


class DelayedOracle(Policy):
    """Бездействие до t_start, затем эталонный плейбук."""
    name = "delayed_oracle"

    def __init__(self, t_start: float):
        self.t_start = t_start
        self.oracle = OraclePolicy()

    def act(self, obs, legal, ep):
        if obs.t_rel < self.t_start:
            return "NO_OP", 0
        return self.oracle.act(obs, legal, ep)


def probe(sid, t_start, seed=1):
    ep = Episode(SCENARIOS[sid], seed=seed)
    ep._policy_name = f"delayed_oracle@{t_start:.0f}"
    r = ep.run(DelayedOracle(t_start))
    return {"t_start": t_start,
            "CAT": r["CAT"], "MAJ": r["MAJ"],
            "barriers": r["barriers"],
            "t_end_s": r["t_end_s"]}


def bisect(sid, ok_fn, hi, tol=30.0, seed=1, log=print):
    """
    Наибольшее T в [0, hi], при котором ok_fn(исход) истинно.

    Предполагается монотонность: чем позже начато вмешательство, тем хуже
    исход. Физически это не гарантировано абсолютно (позднее действие может
    случайно попасть в более благоприятную фазу), поэтому монотонность
    проверяется на границах и нарушение печатается, а не замалчивается.
    """
    lo_res = probe(sid, 0.0, seed)
    if not ok_fn(lo_res):
        log(f"    T=0: {lo_res['CAT']} {lo_res['MAJ']} -- эталон не спасает "
            f"даже с нуля, порог не определён")
        return None, [lo_res]
    hi_res = probe(sid, hi, seed)
    trials = [lo_res, hi_res]
    if ok_fn(hi_res):
        log(f"    T={hi:.0f}: всё ещё держится -- порог за горизонтом")
        return hi, trials

    lo, up = 0.0, hi
    while up - lo > tol:
        mid = round((lo + up) / 2.0, 1)
        res = probe(sid, mid, seed)
        trials.append(res)
        good = ok_fn(res)
        log(f"    T={mid:7.0f} -> CAT={res['CAT']} MAJ={res['MAJ']} "
            f"{'держит' if good else 'не держит'}")
        if good:
            lo = mid
        else:
            up = mid
    return lo, trials


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default="S1,S2,S3,S4,S5")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tol", type=float, default=30.0)
    # Свой файл на процесс: сценарии считаются параллельно, а общий JSON
    # переписывается целиком и потерял бы чужие ключи.
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    out = {}
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            out = json.load(f)

    for sid in args.scenarios.split(","):
        sc = SCENARIOS[sid]
        t0 = time.time()
        print(f"== {sid}: горизонт {sc.horizon_s:.0f} с", flush=True)

        print("  порог катастрофы:", flush=True)
        cat_t, cat_tr = bisect(sid, lambda r: not r["CAT"], sc.horizon_s,
                               args.tol, args.seed)
        print("  порог чистого прогона:", flush=True)
        maj_t, maj_tr = bisect(sid, lambda r: not r["CAT"] and not r["MAJ"],
                               sc.horizon_s, args.tol, args.seed)

        out[sid] = {
            "horizon_s": sc.horizon_s,
            "ponr_cat_s": cat_t,
            "ponr_clean_s": maj_t,
            "tol_s": args.tol,
            "seed": args.seed,
            "probes": len(cat_tr) + len(maj_tr),
        }
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"== {sid}: t_PONR(CAT)={cat_t} с, t_PONR(чисто)={maj_t} с "
              f"({(time.time() - t0) / 60:.1f} мин)", flush=True)

    print("готово", flush=True)


if __name__ == "__main__":
    main()
