"""
Во что обошёлся бы прогон при оплате по счётчику (OpenRouter / прямой API).

Прогон, описанный в docs/LLM-BASELINE.md, шёл по подписке через Claude Code,
и заплаченные за него деньги -- это не цена запросов, а цена запросов ПЛЮС
собственный системный промпт и описания инструментов Claude Code, которые
уходили провайдеру при каждом вызове. Здесь считается цена самих запросов.

Размеры измерены, а не оценены:
  * выходные токены -- из протоколов прогона (usage.output_tokens);
  * входные -- восстановлены воспроизведением эпизодов (tests/measure_prompts.py)
    и переведены в токены настоящим токенизатором Anthropic методом разностей
    (два вызова с одинаковым хвостом и разной системной частью).

    python3 tests/cost_estimate.py
"""

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- цены, $ за миллион токенов (Anthropic = OpenRouter, сквозная) ----------
IN_PER_M = 1.00
OUT_PER_M = 5.00
CACHE_WRITE_MULT = 1.25      # запись кэша, TTL 5 минут
CACHE_READ_MULT = 0.10       # чтение кэша

# --- измерено (см. заголовок) ------------------------------------------------
SYS_TOKENS = 5587            # системная часть, 11 449 символов
USER_CHARS_PER_TOKEN = 1.94  # русский технический текст


def load_rows():
    rows = []
    for line in open(os.path.join(ROOT, "results", "llm.jsonl"),
                     encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main():
    sizes = json.load(open(os.path.join(ROOT, "results", "prompt_sizes.json"),
                           encoding="utf-8"))
    rows = {r["scenario"]: r for r in load_rows()}
    sids = sorted(sizes["episodes"])

    print("=" * 92)
    print("РАЗМЕР ЗАПРОСОВ")
    print("=" * 92)
    print(f"{'сцен.':<7}{'вызовов':>9}{'сист. вход':>12}{'польз. вход':>13}"
          f"{'вход всего':>12}{'выход':>10}")
    tot = {"calls": 0, "sys": 0, "usr": 0, "out": 0}
    per = {}
    for sid in sids:
        e = sizes["episodes"][sid]
        calls = e["calls"]
        sys_t = SYS_TOKENS * calls
        usr_t = round(e["user_chars_total"] / USER_CHARS_PER_TOKEN)
        out_t = sum(t for t in (rows[sid].get("tokens_per_step") or []))
        per[sid] = {"calls": calls, "sys": sys_t, "usr": usr_t, "out": out_t}
        for k, v in (("calls", calls), ("sys", sys_t), ("usr", usr_t),
                     ("out", out_t)):
            tot[k] += v
        print(f"{sid:<7}{calls:>9}{sys_t:>12,}{usr_t:>13,}"
              f"{sys_t + usr_t:>12,}{out_t:>10,}".replace(",", " "))
    print(f"{'итого':<7}{tot['calls']:>9}{tot['sys']:>12,}{tot['usr']:>13,}"
          f"{tot['sys'] + tot['usr']:>12,}{tot['out']:>10,}".replace(",", " "))

    # ---------------- стоимость ----------------
    def money(x):
        return f"${x:,.2f}".replace(",", " ")

    out_cost = tot["out"] / 1e6 * OUT_PER_M
    usr_cost = tot["usr"] / 1e6 * IN_PER_M

    # без кэша: системная часть оплачивается целиком на каждом вызове
    nocache_in = (tot["sys"] + tot["usr"]) / 1e6 * IN_PER_M
    nocache = nocache_in + out_cost

    # с кэшем: системная часть неизменна побайтно, значит пишется один раз
    # на процесс и дальше читается. Сценарии шли пятью параллельными
    # процессами -- считаем пять записей, остальное чтения.
    writes = 5
    reads = tot["calls"] - writes
    sys_cached = (writes * SYS_TOKENS * CACHE_WRITE_MULT
                  + reads * SYS_TOKENS * CACHE_READ_MULT) / 1e6 * IN_PER_M
    cached = sys_cached + usr_cost + out_cost

    print()
    print("=" * 92)
    print("СТОИМОСТЬ ПО СЧЁТЧИКУ "
          f"(вход {money(IN_PER_M)}/млн, выход {money(OUT_PER_M)}/млн)")
    print("=" * 92)
    print(f"{'статья':<46}{'токенов':>14}{'цена':>12}")
    print(f"{'выход (измерен точно)':<46}{tot['out']:>14,}"
          f"{money(out_cost):>12}".replace(",", " "))
    print(f"{'вход, пользовательская часть':<46}{tot['usr']:>14,}"
          f"{money(usr_cost):>12}".replace(",", " "))
    print(f"{'вход, системная часть без кэша':<46}{tot['sys']:>14,}"
          f"{money(tot['sys'] / 1e6 * IN_PER_M):>12}".replace(",", " "))
    print(f"{'вход, системная часть с кэшем ' + f'({writes} записи, {reads} чтений)':<46}"
          f"{'':>14}{money(sys_cached):>12}")
    print("-" * 92)
    print(f"{'ИТОГО без кэширования':<46}{'':>14}{money(nocache):>12}")
    print(f"{'ИТОГО с кэшированием системной части':<46}{'':>14}"
          f"{money(cached):>12}")

    print()
    print(f"{'сцен.':<7}{'без кэша':>12}{'с кэшем':>12}")
    for sid in sids:
        p = per[sid]
        n = ((p["sys"] + p["usr"]) / 1e6 * IN_PER_M
             + p["out"] / 1e6 * OUT_PER_M)
        c = ((SYS_TOKENS * CACHE_WRITE_MULT
              + (p["calls"] - 1) * SYS_TOKENS * CACHE_READ_MULT) / 1e6 * IN_PER_M
             + p["usr"] / 1e6 * IN_PER_M + p["out"] / 1e6 * OUT_PER_M)
        print(f"{sid:<7}{money(n):>12}{money(c):>12}")

    print()
    print("Выходные токены дают "
          f"{out_cost / nocache * 100:.0f} % цены прогона без кэширования и "
          f"{out_cost / cached * 100:.0f} % с кэшированием:")
    print("на этом бенчмарке платишь за размышление, а не за наблюдения.")


if __name__ == "__main__":
    main()
