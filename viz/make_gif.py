# -*- coding: utf-8 -*-
"""Сборка GIF из кадров тренажёра: карта установки + бегущая подпись."""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont

SRC = sys.argv[1] if len(sys.argv) > 1 else "frames_s2"
OUT = sys.argv[2] if len(sys.argv) > 2 else "nh3ops_s2.gif"
W = 760                       # ширина кадра GIF
BAR = 46                      # высота полосы с подписью

F_REG = r"C:\Windows\Fonts\arial.ttf"
F_BLD = r"C:\Windows\Fonts\arialbd.ttf"
f_cap = ImageFont.truetype(F_REG, 15)
f_clk = ImageFont.truetype(F_BLD, 17)
f_big = ImageFont.truetype(F_BLD, 30)
f_sub = ImageFont.truetype(F_REG, 16)

BG, FG, MUT, WARN, BAD = "#1c1f21", "#e6e9ea", "#a7aeb2", "#d9a441", "#cf5a4e"

# Подписи по времени задачи (секунды -> текст, цвет). Берётся последняя
# подходящая запись.
# Тексты сверены с фактической трассой прогона (tests: S2, сид 1):
# уровень ЦР-НД 45.5 % до 900 с, далее рост до 100 % к 2400 с;
# NH3 в машзале 25 ppm к 840 с; доклад обходчика LEVEL_GLASS = 45.5.
CAPTIONS = [
    (0,    "Смена принята. Уровень ЦР-НД 45 %, машзал чист", MUT),
    (125,  "Наряд обходчику: сверить уровень по указателю на аппарате", FG),
    (200,  "Обходчик в машзале, ответ через 70 с", FG),
    (330,  "Доклад: по указателю 45.5 % — со щитом сходится", MUT),
    (840,  "NH₃ в машзале 25 ppm: тревога, человек остаётся в зоне", WARN),
    (1500, "Уровень пошёл вверх — регулятор переполняет ресивер", WARN),
    (2100, "80 % и растёт: жидкость подступает к линии всасывания", BAD),
    (2400, "Унос жидкости. Предохранительный клапан, реле высокого давления", BAD),
]
FINAL = ("АВАРИЯ: КАТ-1", "выброс более 100 кг за пределы площадки")


def caption_for(t):
    cur = CAPTIONS[0]
    for t0, txt, col in CAPTIONS:
        if t >= t0:
            cur = (t0, txt, col)
    return cur[1], cur[2]


def hhmmss_to_s(s):
    p = [int(x) for x in s.split(":")]
    return p[0] * 3600 + p[1] * 60 + p[2]


def main():
    meta = json.load(open(os.path.join(SRC, "meta.json"), encoding="utf-8"))
    maps = [m for m in meta if m["kind"] == "map"]
    frames, durations = [], []
    last_map = None

    for m in maps:
        im = Image.open(os.path.join(SRC, m["file"])).convert("RGB")
        h = round(im.height * W / im.width)
        im = im.resize((W, h), Image.NEAREST)      # пиксель-арт: без сглаживания
        t = hhmmss_to_s(m["clock"])
        canvas = Image.new("RGB", (W, h + BAR), BG)
        canvas.paste(im, (0, 0))
        d = ImageDraw.Draw(canvas)
        txt, col = caption_for(t)
        clk = f"t = {m['clock']}"
        d.text((10, h + 8), clk, font=f_clk, fill=FG)
        d.text((18 + d.textlength(clk, font=f_clk), h + 10), txt,
               font=f_cap, fill=col)
        mark = "NH3Bench"
        d.text((W - 10 - d.textlength(mark, font=f_cap), h + 11), mark,
               font=f_cap, fill="#5f676c")
        frames.append(canvas)
        durations.append(130)
        last_map = canvas

    # Финал: затемнённый последний кадр карты с вердиктом.
    if last_map is not None:
        fin = Image.blend(last_map, Image.new("RGB", last_map.size, BG), 0.62)
        d = ImageDraw.Draw(fin)
        wv = d.textlength(FINAL[0], font=f_big)
        ws = d.textlength(FINAL[1], font=f_sub)
        y = fin.height // 2 - 46
        d.text(((fin.width - wv) / 2, y), FINAL[0], font=f_big, fill=BAD)
        d.text(((fin.width - ws) / 2, y + 40), FINAL[1], font=f_sub, fill=FG)
        for _ in range(3):
            frames.append(fin)
            durations.append(700)

    # Общая палитра на все кадры: одинаковый LZW-словарь сжимает пиксель-арт
    # заметно лучше, чем покадровая квантизация.
    pal_src = frames[len(frames) // 2].quantize(colors=96, method=Image.MAXCOVERAGE)
    pal_frames = [f.quantize(palette=pal_src, dither=Image.NONE) for f in frames]

    pal_frames[0].save(OUT, save_all=True, append_images=pal_frames[1:],
                       duration=durations, loop=0, optimize=True, disposal=1)
    size = os.path.getsize(OUT) / 1024
    print(f"{OUT}: {len(frames)} кадров, {frames[0].size[0]}x{frames[0].size[1]}, "
          f"{size:.0f} КБ")

    # Ключевой кадр отдельно (для статьи, где GIF не вставить).
    still = frames[len(maps) - 1]
    still.save(os.path.splitext(OUT)[0] + "_still.png")
    print("ключевой кадр:", os.path.splitext(OUT)[0] + "_still.png")


if __name__ == "__main__":
    main()
