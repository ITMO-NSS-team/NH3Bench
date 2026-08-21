# -*- coding: utf-8 -*-
"""Сборка экспертного описания в один HTML-файл."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from expert_doc_text import (TITLE, SUBTITLE, PURPOSE, INTRO, TWIN, BENCH,
                             S1, S2, S3, S4, S5, FINAL, TABLE1)

D = os.path.dirname(os.path.abspath(__file__))
F = json.load(open(os.path.join(D, "expert_figs.json")))

# ======================= SVG-схемы =======================

SVG_SCHEME = """
<svg viewBox="0 0 940 560" xmlns="http://www.w3.org/2000/svg" font-family="DejaVu Sans, sans-serif">
<defs>
<marker id="ar" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
<path d="M0,0 L7,3 L0,6 Z" fill="#111"/></marker>
</defs>
<style>
 .p{stroke:#111;stroke-width:1.6;fill:none;marker-end:url(#ar)}
 .pl{stroke:#111;stroke-width:2.4;fill:none;marker-end:url(#ar)}
 .pd{stroke:#555;stroke-width:1.4;fill:none;stroke-dasharray:6 4;marker-end:url(#ar)}
 .eq{fill:#fff;stroke:#111;stroke-width:1.6}
 .tx{font-size:12px;fill:#111}
 .ts{font-size:10.5px;fill:#333}
 .tb{font-size:12.5px;font-weight:bold;fill:#111}
</style>

<!-- Конденсаторы -->
<rect class="eq" x="700" y="20" width="90" height="60"/>
<rect class="eq" x="810" y="20" width="90" height="60"/>
<path d="M710,35 h70 M710,50 h70 M710,65 h70 M820,35 h70 M820,50 h70 M820,65 h70" stroke="#555" stroke-width="1"/>
<text class="tb" x="700" y="14">КД1</text><text class="tb" x="810" y="14">КД2</text>
<text class="ts" x="700" y="96">испарительные конденсаторы (кровля)</text>

<!-- Линейный ресивер -->
<rect class="eq" x="770" y="130" width="130" height="44" rx="20"/>
<text class="tb" x="770" y="124">РЛ</text>
<text class="ts" x="772" y="157">линейный ресивер</text>

<!-- Верхняя ступень -->
<circle class="eq" cx="585" cy="120" r="26"/><circle class="eq" cx="650" cy="120" r="26"/>
<text class="tb" x="570" y="86">КМ3</text><text class="tb" x="637" y="86">КМ4</text>
<text class="ts" x="560" y="165">верхняя ступень</text>

<!-- ЦР-СД -->
<rect class="eq" x="430" y="210" width="120" height="66" rx="22"/>
<rect x="432" y="248" width="116" height="26" rx="12" fill="#d9e2ea" stroke="none"/>
<text class="tb" x="430" y="204">ЦР-СД</text>
<text class="ts" x="434" y="228">t₀ = −10 °С</text>
<text class="ts" x="434" y="242">≈1,9 кгс/см²</text>

<!-- Бустеры -->
<circle class="eq" cx="300" cy="140" r="26"/><circle class="eq" cx="365" cy="140" r="26"/>
<text class="tb" x="285" y="106">КМ1</text><text class="tb" x="352" y="106">КМ2</text>
<text class="ts" x="272" y="185">бустер-компрессоры</text>

<!-- ЦР-НД -->
<rect class="eq" x="120" y="230" width="120" height="66" rx="22"/>
<rect x="122" y="266" width="116" height="28" rx="12" fill="#d9e2ea" stroke="none"/>
<text class="tb" x="120" y="224">ЦР-НД</text>
<text class="ts" x="124" y="248">t₀ = −40 °С</text>
<text class="ts" x="124" y="262">вакуум ≈0,3</text>

<!-- Насосы -->
<circle class="eq" cx="150" cy="340" r="14"/><circle class="eq" cx="185" cy="340" r="14"/>
<text class="ts" x="132" y="372">НА1, НА2</text>
<circle class="eq" cx="460" cy="330" r="14"/><circle class="eq" cx="495" cy="330" r="14"/>
<text class="ts" x="442" y="362">НА3, НА4</text>

<!-- Потребители НД -->
<rect class="eq" x="60" y="420" width="150" height="52"/>
<path d="M75,428 v36 M95,428 v36 M115,428 v36 M135,428 v36 M155,428 v36 M175,428 v36 M195,428 v36" stroke="#555" stroke-width="1"/>
<text class="tb" x="60" y="414">ВО-3, ВО-4</text>
<text class="ts" x="60" y="490">НТ-склад −20 °С</text>
<rect class="eq" x="240" y="420" width="150" height="52"/>
<path d="M255,428 v36 M275,428 v36 M295,428 v36 M315,428 v36 M335,428 v36 M355,428 v36 M375,428 v36" stroke="#555" stroke-width="1"/>
<text class="tb" x="240" y="414">ВО-5, ВО-6</text>
<text class="ts" x="240" y="490">морозильная −30 °С</text>

<!-- Потребители СД -->
<rect class="eq" x="440" y="420" width="140" height="52"/>
<text class="tb" x="440" y="414">ВО-2</text>
<text class="ts" x="440" y="490">камера +2 °С</text>
<rect class="eq" x="610" y="420" width="170" height="52"/>
<path d="M625,428 v36 M650,428 v36 M675,428 v36 M700,428 v36 M725,428 v36 M750,428 v36" stroke="#555" stroke-width="1"/>
<text class="tb" x="610" y="414">ВО-1 + льдоаккумулятор</text>
<text class="ts" x="610" y="490">ледяная вода → молоко</text>

<!-- Линии: всасывание НД -->
<path class="pd" d="M135,420 v-60 v-30"/>
<path class="pd" d="M310,420 v-80 h-120"/>
<path class="pd" d="M200,230 v-40 h74" />
<text class="ts" x="205" y="204">всас НД</text>
<!-- нагнетание бустеров в ЦР-СД -->
<path class="p" d="M333,166 v20 h100 v24"/>
<text class="ts" x="342" y="199">в промсосуд</text>
<!-- всас ВД из ЦР-СД -->
<path class="pd" d="M550,230 h20 v-84"/>
<text class="ts" x="548" y="222">всас ВД</text>
<!-- нагнетание ВД в конденсаторы -->
<path class="p" d="M650,94 v-40 h50"/>
<path class="p" d="M700,54 h100" transform="translate(10,0)"/>
<text class="ts" x="660" y="42">нагнетание</text>
<!-- конденсат в РЛ -->
<path class="pl" d="M860,80 v50"/>
<!-- жидкость РЛ -> ЦР-СД -->
<path class="pl" d="M770,152 h-160 v70 h-60"/>
<text class="ts" x="600" y="146">жидкость ВД</text>
<!-- жидкость ЦР-СД -> ЦР-НД (подпитка через клапан уровня) -->
<path class="pl" d="M430,258 h-100 v0"/>
<polygon points="330,252 318,258 330,264" fill="#fff" stroke="#111" stroke-width="1.4"/>
<polygon points="306,252 318,258 306,264" fill="#fff" stroke="#111" stroke-width="1.4"/>
<path class="pl" d="M306,258 h-66"/>
<text class="ts" x="288" y="246">КУ</text>
<!-- насосная подача НД -->
<path class="pl" d="M150,296 v30"/>
<path class="pl" d="M150,354 v30 h-15 v36"/>
<path class="pl" d="M167,384 h143 v36"/>
<!-- насосная подача СД -->
<path class="pl" d="M460,276 v40"/>
<path class="pl" d="M460,344 v40 h50 v36"/>
<path class="pl" d="M477,384 h208 v36"/>
<!-- горячий пар оттайки -->
<path class="pd" d="M615,60 h-500 v340" stroke="#8b1a1a"/>
<text class="ts" x="118" y="54" fill="#8b1a1a">горячий пар на оттайку</text>
<!-- Газоанализаторы -->
<rect class="eq" x="330" y="520" width="230" height="28"/>
<text class="ts" x="338" y="538">АТ-1 машзал · АТ-2 цех — стационарные ГА</text>
</svg>
"""

SVG_PLAN = """
<svg viewBox="0 0 940 330" xmlns="http://www.w3.org/2000/svg" font-family="DejaVu Sans, sans-serif">
<style>
 .rm{fill:#fff;stroke:#111;stroke-width:1.8}
 .tb{font-size:13px;font-weight:bold;fill:#111}
 .ts{font-size:11px;fill:#333}
 .tt{font-size:11.5px;fill:#8b1a1a}
 .w{stroke:#555;stroke-width:1.2;stroke-dasharray:5 4;fill:none}
</style>
<rect class="rm" x="330" y="120" width="180" height="90"/>
<text class="tb" x="345" y="145">ЩИТОВАЯ</text>
<text class="ts" x="345" y="162">сменный инженер</text>
<text class="ts" x="345" y="177">(испытуемый) + 2 обходчика</text>

<rect class="rm" x="60" y="110" width="190" height="110"/>
<text class="tb" x="75" y="136">МАШИННОЕ ОТДЕЛЕНИЕ</text>
<text class="ts" x="75" y="153">КМ1…КМ4, ЦР-НД, ЦР-СД, РЛ</text>
<text class="ts" x="75" y="168">указатели уровня, манометры</text>
<text class="ts" x="75" y="183">АТ-1</text>

<rect class="rm" x="590" y="110" width="170" height="110"/>
<text class="tb" x="605" y="136">ЦЕХ</text>
<text class="ts" x="605" y="153">приёмка, пастеризация</text>
<text class="ts" x="605" y="168">АТ-2</text>

<rect class="rm" x="60" y="20" width="190" height="55"/>
<text class="tb" x="75" y="42">КРОВЛЯ</text>
<text class="ts" x="75" y="60">КД1, КД2, насосы орошения</text>

<rect class="rm" x="590" y="20" width="170" height="55"/>
<text class="tb" x="605" y="42">НТ-СКЛАД / МОРОЗ.</text>
<text class="ts" x="605" y="60">ВО-3…ВО-6, вентили оттайки</text>

<rect class="rm" x="330" y="255" width="180" height="50"/>
<text class="tb" x="345" y="278">СБОРНЫЙ ПУНКТ</text>
<text class="ts" x="345" y="295">эвакуация</text>

<path class="w" d="M330,160 h-80"/><text class="tt" x="262" y="152">75 с</text>
<path class="w" d="M510,160 h80"/><text class="tt" x="532" y="152">60 с</text>
<path class="w" d="M400,120 C360,80 260,60 250,55"/><text class="tt" x="300" y="78">180 с</text>
<path class="w" d="M460,120 C500,80 570,60 590,55"/><text class="tt" x="520" y="78">110–120 с</text>
<path class="w" d="M420,210 v45"/><text class="tt" x="428" y="238">90 с</text>
<text class="ts" x="60" y="322">Времена — в одну сторону, быстрым шагом. Работа на месте: отсчёт уровня 70 с; замер переносным ГА 45 с; ручной вентиль 100–110 с; отсечь сосуд ≈ 4 мин; закрыть наряд-допуск ≈ 4 мин.</text>
</svg>
"""

SVG_CYCLE = """
<svg viewBox="0 0 940 240" xmlns="http://www.w3.org/2000/svg" font-family="DejaVu Sans, sans-serif">
<defs><marker id="a2" markerWidth="9" markerHeight="9" refX="8" refY="3.5" orient="auto">
<path d="M0,0 L8,3.5 L0,7 Z" fill="#111"/></marker></defs>
<style>
 .b{fill:#fff;stroke:#111;stroke-width:1.8}
 .tb{font-size:13px;font-weight:bold;fill:#111}
 .ts{font-size:11px;fill:#333}
 .ar{stroke:#111;stroke-width:1.6;fill:none;marker-end:url(#a2)}
 .tt{font-size:11px;fill:#8b1a1a}
</style>
<rect class="b" x="40" y="70" width="200" height="80"/>
<text class="tb" x="55" y="98">ПАНЕЛЬ ЩИТА</text>
<text class="ts" x="55" y="116">приборы, сигнализация,</text>
<text class="ts" x="55" y="131">доклады обходчиков</text>

<rect class="b" x="330" y="70" width="200" height="80"/>
<text class="tb" x="345" y="98">РЕШЕНИЕ</text>
<text class="ts" x="345" y="116">выбор одной команды</text>
<text class="ts" x="345" y="131">из каталога (133 шт.)</text>

<rect class="b" x="620" y="70" width="240" height="80"/>
<text class="tb" x="635" y="98">УСТАНОВКА ЖИВЁТ</text>
<text class="ts" x="635" y="116">физика идёт непрерывно,</text>
<text class="ts" x="635" y="131">обходчики идут и работают</text>

<path class="ar" d="M240,110 h90"/>
<path class="ar" d="M530,110 h90"/>
<path class="ar" d="M740,150 C740,205 300,205 145,152"/>
<text class="ts" x="380" y="212">новый опрос панели через 10 с</text>

<text class="tt" x="255" y="98">опрос</text>
<text class="tt" x="536" y="92">обдумывание — время!</text>
<text class="tt" x="536" y="106">исполнение — время!</text>
<text class="ts" x="40" y="40">Пока испытуемый думает и пока команда исполняется, процесс НЕ ждёт. Долгое правильное решение может опоздать.</text>
</svg>
"""

SVG_DEFROST = """
<svg viewBox="0 0 940 300" xmlns="http://www.w3.org/2000/svg" font-family="DejaVu Sans, sans-serif">
<defs><marker id="a3" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
<path d="M0,0 L7,3 L0,6 Z" fill="#111"/></marker></defs>
<style>
 .eq{fill:#fff;stroke:#111;stroke-width:1.7}
 .p{stroke:#111;stroke-width:2;fill:none;marker-end:url(#a3)}
 .pd{stroke:#555;stroke-width:1.5;stroke-dasharray:6 4;fill:none;marker-end:url(#a3)}
 .tb{font-size:12.5px;font-weight:bold;fill:#111}
 .ts{font-size:11px;fill:#333}
 .tr{font-size:11.5px;fill:#8b1a1a}
 .v{fill:#fff;stroke:#111;stroke-width:1.5}
</style>
<rect class="eq" x="380" y="90" width="220" height="80"/>
<path d="M400,98 v64 M430,98 v64 M460,98 v64 M490,98 v64 M520,98 v64 M550,98 v64 M580,98 v64" stroke="#555" stroke-width="1"/>
<text class="tb" x="380" y="82">батарея ВО-3 (НТ-склад)</text>
<text class="tr" x="388" y="192">после зависшей оттайки: 9,2 кгс/см², металл +10 °С</text>

<!-- подача жидкости с СВ -->
<path class="p" d="M120,130 h180"/>
<polygon class="v" points="300,122 318,130 300,138"/>
<polygon class="v" points="336,122 318,130 336,138"/>
<rect class="v" x="310" y="102" width="16" height="12"/>
<path class="p" d="M336,130 h44"/>
<text class="tb" x="60" y="122">жидкость −40 °С</text>
<text class="ts" x="60" y="137">от насосов ЦР-НД</text>
<text class="ts" x="286" y="158">СВ подачи</text>
<text class="tr" x="238" y="98">откроется по термостату —</text>
<text class="tr" x="238" y="112">камера тёплая!</text>

<!-- горячий пар с вентилем -->
<path class="pd" d="M490,30 v40" stroke="#8b1a1a"/>
<polygon class="v" points="482,52 490,66 498,52" transform="translate(0,-10)"/>
<text class="tb" x="500" y="34" fill="#8b1a1a">горячий пар</text>
<text class="ts" x="500" y="50">ручной вентиль — РАБОТАЕТ</text>

<!-- всас -->
<path class="pd" d="M600,130 h120"/>
<polygon class="v" points="700,122 718,130 700,138" transform="translate(-40,0)"/>
<text class="ts" x="640" y="152">на всас НД</text>
<text class="tb" x="730" y="134">ЦР-НД</text>

<!-- контроллер -->
<rect class="eq" x="380" y="230" width="220" height="46"/>
<text class="tb" x="392" y="250">СЕКВЕНСОР ОТТАЙКИ — ЗАВИС</text>
<text class="ts" x="392" y="266">стадия не идёт; команды «прервать» глотает</text>
<path class="pd" d="M490,230 v-60" stroke="#8b1a1a"/>
<text class="tr" x="500" y="205">через 10 мин сам сбросит</text>
<text class="tr" x="500" y="219">секцию в «охлаждение»</text>
</svg>
"""

SVG_TRAP = """
<svg viewBox="0 0 940 300" xmlns="http://www.w3.org/2000/svg" font-family="DejaVu Sans, sans-serif">
<style>
 .eq{fill:#fff;stroke:#111;stroke-width:1.7}
 .p{stroke:#111;stroke-width:2.4;fill:none}
 .tb{font-size:12.5px;font-weight:bold;fill:#111}
 .ts{font-size:11px;fill:#333}
 .tr{font-size:11.5px;fill:#8b1a1a}
 .v{fill:#fff;stroke:#111;stroke-width:1.6}
 .vx{fill:#8b1a1a;stroke:#8b1a1a;stroke-width:1.6}
</style>
<rect class="eq" x="40" y="110" width="120" height="60" rx="20"/>
<text class="tb" x="40" y="102">ЦР-СД</text>
<circle class="eq" cx="210" cy="140" r="16"/>
<text class="ts" x="196" y="176">насос</text>

<path class="p" d="M160,140 h34 M226,140 h84"/>
<!-- запорный вентиль у сосуда -->
<polygon class="v" points="310,132 328,140 310,148"/>
<polygon class="v" points="346,132 328,140 346,148"/>
<text class="ts" x="292" y="120">ЗВ у сосуда</text>
<path class="p" d="M346,140 h214"/>
<!-- утечка -->
<path d="M430,140 l-8,-26 M430,140 l0,-30 M430,140 l8,-26" stroke="#8b1a1a" stroke-width="1.6"/>
<text class="tr" x="380" y="92">сальник травит (95 ppm)</text>
<!-- заглушенный ГПК -->
<path class="p" d="M480,140 v-0" />
<path d="M490,140 v-34" stroke="#111" stroke-width="1.8"/>
<rect class="vx" x="482" y="106" width="16" height="10"/>
<text class="tr" x="452" y="60">ГПК ЗАГЛУШЕН</text>
<text class="ts" x="452" y="75">(негерметичен, до замены)</text>
<!-- соленоид у батареи -->
<polygon class="v" points="560,132 578,140 560,148"/>
<polygon class="v" points="596,132 578,140 596,148"/>
<rect class="v" x="570" y="112" width="16" height="12"/>
<text class="ts" x="548" y="168">СВ подачи ВО-1</text>
<path class="p" d="M596,140 h60"/>
<rect class="eq" x="656" y="110" width="200" height="60"/>
<text class="tb" x="656" y="102">ВО-1 (испаритель лед. воды)</text>

<rect x="336" y="196" width="330" height="86" fill="none" stroke="#8b1a1a" stroke-width="1.4" stroke-dasharray="7 5"/>
<text class="tr" x="344" y="216">ЗАПЕРТЫЙ УЧАСТОК: если закрыты И ЗВ, И СВ —</text>
<text class="tr" x="344" y="232">жидкость без паровой подушки; прогрев машзалом</text>
<text class="tr" x="344" y="248">+9 кгс/см² на градус; защиты нет — клапан заглушен.</text>
<text class="tb" x="344" y="272">Верно: ЗВ закрыть, СВ ОСТАВИТЬ ОТКРЫТЫМ.</text>
</svg>
"""

# ======================= HTML =======================

def fig(name, num, caption):
    return (f'<figure><img src="data:image/png;base64,{F[name]}" '
            f'alt="Рис. {num}"><figcaption>Рис. {num} — {caption}'
            f'</figcaption></figure>')

def svgfig(svg, num, caption):
    return (f'<figure class="svgf">{svg}<figcaption>Рис. {num} — {caption}'
            f'</figcaption></figure>')

CSS = """
body{font-family:"PT Serif",Georgia,"Times New Roman",serif;background:#fff;
 color:#111;margin:0;padding:0 16px;font-size:15.5px;line-height:1.52}
.page{max-width:880px;margin:0 auto;padding:28px 0 60px}
.stamp{border:2.2px solid #111;padding:22px 26px;margin-bottom:30px}
.stamp .k{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#444}
h1{font-size:27px;margin:10px 0 6px;line-height:1.25}
.sub{font-size:17px;margin:0 0 14px;color:#222}
.purp{font-size:13.5px;color:#444;border-top:1px solid #999;padding-top:10px}
h2{font-size:20px;margin:42px 0 12px;border-bottom:2px solid #111;padding-bottom:5px}
h3{font-size:16.5px;margin:24px 0 8px}
p{margin:9px 0;text-align:justify}
ol{margin:8px 0 8px 22px}
table.t{border-collapse:collapse;margin:14px 0;width:100%;font-size:14px}
table.t caption{caption-side:top;text-align:left;font-size:13.5px;color:#333;
 padding-bottom:5px;font-style:italic}
table.t th,table.t td{border:1px solid #111;padding:5px 9px;text-align:left;
 vertical-align:top}
table.t th{background:#eee;font-weight:bold}
table.vlist td:nth-child(2){width:64px}
table.vlist td{height:26px}
.q{border:1.6px solid #111;background:#f6f4ef;padding:12px 16px;margin:18px 0;
 font-size:14.5px}
figure{margin:20px 0;text-align:center}
figure img{max-width:100%;border:1px solid #bbb}
figure.svgf svg{max-width:100%;height:auto;border:1px solid #bbb;background:#fff}
figcaption{font-size:13.5px;color:#333;margin-top:7px;text-align:center}
.sig{margin-top:34px;font-size:13.5px;color:#444;border-top:1px solid #999;
 padding-top:10px}
b{font-weight:700}
@media print{.page{max-width:none}.q{background:#fff}}
"""

parts = []
parts.append(f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{TITLE} — описание для экспертной проверки</title>
<link href="https://fonts.googleapis.com/css2?family=PT+Serif:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="page">
<div class="stamp">
<div class="k">Для экспертной проверки · не для эксплуатации</div>
<h1>{TITLE}</h1>
<p class="sub">{SUBTITLE}</p>
<p class="purp">{PURPOSE}. Просьба читать с карандашом: в конце каждого
раздела — вопросы, в конце документа — лист замечаний.</p>
</div>""")

parts.append(INTRO)

# Раздел 2 с врезкой схем
twin_parts = TWIN.split("<h3>2.2. Что имитируется</h3>")
parts.append(twin_parts[0])
parts.append(svgfig(SVG_SCHEME, 1,
    "принципиальная схема имитируемой установки (упрощённо; КУ — клапан "
    "уровня, штриховые линии — паровые, сплошные — жидкостные)"))
parts.append(TABLE1)
parts.append("<h3>2.2. Что имитируется</h3>" + twin_parts[1].split(
    "<h3>2.3. Что упрощено")[0])
parts.append(fig("fig_normal", 2,
    "штатный суточный ход по данным имитатора: уставки камер держатся, "
    "молоко в границе, лёд намораживается к пику приёмки"))
parts.append("<h3>2.3. Что упрощено" + twin_parts[1].split(
    "<h3>2.3. Что упрощено")[1])

# Раздел 3 с планом и циклом
bench_parts = BENCH.split("<h3>3.2. Ход времени</h3>")
parts.append(bench_parts[0])
parts.append(svgfig(SVG_PLAN, 3,
    "план размещения и времена переходов обходчиков"))
parts.append("<h3>3.2. Ход времени</h3>" + bench_parts[1].split(
    "<h3>3.3. Чем может")[0])
parts.append(svgfig(SVG_CYCLE, 4,
    "цикл испытания: решение и исполнение стоят времени"))
parts.append("<h3>3.3. Чем может" + bench_parts[1].split(
    "<h3>3.3. Чем может")[1])

# Задача 1
s1p = S1.split("<h3>4.3. Развитие")
parts.append(s1p[0])
parts.append(svgfig(SVG_DEFROST, 5,
    "узел оттайки ВО-3 на момент начала задачи: батарея под горячим паром, "
    "камера тёплая, секвенсор завис"))
parts.append("<h3>4.3. Развитие" + s1p[1].split("<h3>4.4. Верные")[0])
parts.append(fig("fig_s1", 6,
    "задача №1 при бездействии (прогон имитатора): сброс секции на 600-й "
    "секунде, открытие подачи, гидроудар и разрыв на 614-й"))
parts.append("<h3>4.4. Верные" + s1p[1].split("<h3>4.4. Верные")[1])

# Задача 2
s2p = S2.split("<h3>5.4. Верные действия</h3>")
parts.append(s2p[0])
parts.append(fig("fig_s2", 7,
    "задача №2 при бездействии (прогон имитатора): показание уровнемера "
    "застыло, фактический уровень уходит к уносу; внизу — концентрация в "
    "машзале"))
parts.append("<h3>5.4. Верные действия</h3>" + s2p[1])

# Задача 3
s3p = S3.split("<h3>6.3. Развитие")
parts.append(s3p[0])
parts.append(fig("fig_s3", 8,
    "задача №3 при бездействии (прогон имитатора): рост давления до защиты; "
    "в середине — признак воздуха (расхождение температур); внизу — молоко"))
parts.append("<h3>6.3. Развитие" + s3p[1])

# Задача 4
s4p = S4.split("<h3>7.3. Развитие")
parts.append(s4p[0])
parts.append(svgfig(SVG_TRAP, 9,
    "задача №4: жидкостная линия ЦР-СД → ВО-1 с травящим сальником и "
    "заглушенным ГПК; рамкой — участок, который нельзя запирать с двух "
    "сторон"))
parts.append(fig("fig_s4", 10,
    "давление запертого участка после закрытия обоих вентилей (расчёт по "
    "модели): около 9 кгс/см² на градус прогрева, разрыв через ~15 минут"))
parts.append("<h3>7.3. Развитие" + s4p[1])

# Задача 5
s5p = S5.split("<h3>8.3. Развитие")
parts.append(s5p[0])
parts.append(fig("fig_s5", 11,
    "задача №5 (прогон имитатора): просроченный стационарный прибор дрейфует "
    "к аварийной уставке, фактическая концентрация — единицы мг/м³"))
parts.append("<h3>8.3. Развитие" + s5p[1])

parts.append(FINAL)
parts.append("</div></body></html>")

out = "\n".join(parts)
path = "/mnt/user-data/outputs/NH3Ops-описание-для-эксперта.html"
open(path, "w", encoding="utf-8").write(out)
print("записан:", path, round(len(out) / 1024), "КБ")
