// =====================================================================
// Свои прогоны в таблице результатов.
//
// Балл человека считает не этот файл: он приходит из двойника, где его
// считает та же metrics.bench_score_run, которой посчитаны клетки в
// results/ (см. driver.Session._score). Здесь только хранение, сведение
// в строку и удаление -- иначе строка человека не была бы сравнима со
// строкой модели.
//
// Хранилище -- localStorage этого браузера. Ничего никуда не уходит, и об
// этом сказано в самой таблице: опыт, поставленный на стенде, не должен
// выглядеть как часть опубликованного набора.
// =====================================================================

const MINE_KEY = "nh3.myruns";
const MINE_NAME_KEY = "nh3.myname";
const MINE_MAX = 200;              // больше в localStorage держать незачем

// Русские подписи; английские -- в I18N_JS по тем же ключам.
const ML = {
  mineHead: "Ваши прогоны",
  mineNote: "Сохранены только в этом браузере и никуда не отправляются.",
  mineAdd: "в таблицу результатов",
  mineName: "название опыта",
  mineAddBtn: "добавить",
  mineAdded: "добавлено в таблицу",
  mineOpen: "открыть таблицу",
  mineDefault: "мой прогон",
  mineDel: "удалить опыт",
  mineDelAsk: "Удалить опыт целиком?",
  mineHuman: "человек",
  mineQuick: "демо",
  mineQuickNote: "быстрая проба -- сокращённое взаимодействие, " +
                 "не результат бенчмарка",
  mineStopped: "прервано",
  mineStoppedNote: "задача завершена вручную, в среднее не входит",
  mineReplaced: "прежний результат этой задачи в этом опыте заменён",
  mineNoRoom: "не удалось сохранить: память браузера не приняла запись",
  mineNothing: "своих прогонов пока нет",
  mineClear: "удалить все свои прогоны",
  mineScoredBy: "балл посчитан теми же функциями, что и опубликованные",
};

function mineRead(key, dflt) {
  try {
    const v = localStorage.getItem(key);
    return v === null ? dflt : v;
  } catch (e) { return dflt; }        // приватное окно -- просто без памяти
}

function mineWrite(key, val) {
  try { localStorage.setItem(key, val); return true; } catch (e) { return false; }
}

function mineLoad() {
  try {
    const a = JSON.parse(mineRead(MINE_KEY, "[]"));
    return Array.isArray(a) ? a : [];
  } catch (e) { return []; }
}

function mineSave(arr) {
  return mineWrite(MINE_KEY, JSON.stringify(arr.slice(-MINE_MAX)));
}

function mineName() {
  const n = String(mineRead(MINE_NAME_KEY, "") || "").trim();
  return n || L("mineDefault");
}

function mineSetName(n) {
  const v = String(n || "").trim().slice(0, 40);
  mineWrite(MINE_NAME_KEY, v);
  return v || L("mineDefault");
}

// Прогон, собранный из итога задачи. Балл берётся как есть; прерванный
// вручную прогон и быстрая проба в среднее не идут -- это не полная задача.
function mineRun(f, kind, name) {
  const sc = (typeof SCEN !== "undefined")
    ? SCEN.find(x => x.sid === f.sid) : null;
  const forced = !!f.forced;
  // Протокол хранится вместе с итогом: без последовательности команд свой
  // прогон нельзя поставить рядом с прогоном модели в сравнении решений.
  // Формат сжатый -- [секунда, команда, цена решения в секундах].
  const rec = (f.records || []).slice(0, 400)
    .map(r => [Math.round(r.t || 0), String(r.aid || ""),
               Math.round(r.think || 0)])
    .filter(r => r[1]);
  return {
    id: "mine:" + Date.now() + ":" + Math.random().toString(36).slice(2, 7),
    kind: kind === "quick" ? "quick" : "human",
    agent: String(name || mineName()).slice(0, 40),
    scenario: f.sid,
    records: rec,
    // Язык задания -- часть того, что человек читал, ровно как у модели.
    prompt_lang: (typeof LANG !== "undefined" && LANG === "en") ? "en" : "ru",
    score: (f.score === null || f.score === undefined) ? null : f.score,
    CAT: f.CAT || [], MAJ: f.MAJ || [],
    esd: !!f.esd,
    t_end_s: f.t_end, horizon_s: sc ? sc.horizon : null,
    forced: forced,
    scored: kind !== "quick" && !forced && f.score !== null
            && f.score !== undefined,
    when: new Date().toISOString().slice(0, 16).replace("T", " "),
  };
}

// Добавление: прежний результат той же задачи в том же опыте заменяется.
// Иначе в строке оказалось бы несколько попыток одной задачи, и было бы
// неясно, какая из них в среднем.
function mineAdd(f, kind, name) {
  const r = mineRun(f, kind, name);
  const arr = mineLoad();
  const kept = arr.filter(x => !(x.kind === r.kind && x.agent === r.agent
                                 && x.scenario === r.scenario));
  const replaced = arr.length - kept.length;
  kept.push(r);
  // Ответ хранилища важен: в приватном окне и при переполнении запись не
  // проходит, и говорить «добавлено» в этом случае нельзя.
  const ok = mineSave(kept);
  return { run: r, replaced: replaced, ok: ok };
}

function mineDelAgent(kind, agent) {
  mineSave(mineLoad().filter(x => !(x.kind === kind && x.agent === agent)));
}

function mineClear() {
  try { localStorage.removeItem(MINE_KEY); } catch (e) { /* и так пусто */ }
}

// Сведение в строки таблицы по тем же правилам, что demo_manifest:
// среднее -- только по зачтённым задачам, разрыв с регламентом -- только у
// полной строки. Среднее по части задач не сравнимо со средним по всем.
function mineAgents() {
  const sids = MANIFEST.scenarios.map(s => s.sid);
  const reg = MANIFEST.agents.find(a => a.id === "regulation");
  const by = {};
  mineLoad().forEach(r => {
    const key = r.kind + "|" + r.agent;
    if (!by[key]) {
      by[key] = { id: r.agent, kind: r.kind, mine: true,
                  scores: {}, runs: {}, n_total: sids.length };
    }
    by[key].runs[r.scenario] = r;
    if (r.scored && r.score !== null) by[key].scores[r.scenario] = r.score;
  });
  const out = Object.values(by);
  out.forEach(a => {
    const vals = sids.map(s => a.scores[s]).filter(v => v !== undefined);
    a.n_scored = vals.length;
    a.complete = a.kind === "human" && vals.length === sids.length;
    a.score_mean = vals.length
      ? Math.round(vals.reduce((x, y) => x + y, 0) / vals.length * 10) / 10
      : null;
    a.score_worst = vals.length ? Math.min.apply(null, vals) : null;
    a.reg_gap = (a.complete && reg && reg.score_mean !== null)
      ? Math.round((a.score_mean - reg.score_mean) * 10) / 10 : null;
  });
  // Полные строки выше, дальше по среднему; демо -- в конце.
  return out.sort((x, y) => (x.kind === "quick") - (y.kind === "quick")
                            || (y.score_mean || 0) - (x.score_mean || 0));
}

// ---------------------------------------------------------------------
// Свой прогон в сравнении решений
//
// Сравнение выравнивает две последовательности команд; физика у своего
// прохождения та же, что у прогона модели, поэтому строки сопоставимы.
// Пересчёта здесь нет: время, команды и цена решения -- из протокола.
// ---------------------------------------------------------------------

function mineShape(r) {
  return {
    id: r.id, kind: r.kind, agent: r.agent, scenario: r.scenario,
    prompt_lang: r.prompt_lang || "ru",
    score: (r.score === null || r.score === undefined) ? "—" : r.score,
    CAT: r.CAT || [], MAJ: r.MAJ || [], esd: !!r.esd,
    clean: !(r.CAT || []).length && !(r.MAJ || []).length,
    t_end_s: r.t_end_s, horizon_s: r.horizon_s,
    forced: !!r.forced, mine: true,
    // В просмотр запись не идёт: двойник её не переигрывает, там нужен
    // протокол с токенами. В сравнении решений она полноценна.
    watchable: false,
    trace_stats: { n_decisions: (r.records || []).length },
  };
}

function mineDiffRuns(sid) {
  return mineLoad()
    .filter(r => r.scenario === sid && (r.records || []).length)
    .map(mineShape);
}

function mineDiffRunById(id) {
  const r = mineLoad().find(x => x.id === id);
  return r ? mineShape(r) : null;
}

// Цена решения человека -- секунды, а не токены: он их не тратит, но часы
// задачи ему начислены теми же секундами.
function mineDiffSteps(id) {
  const r = mineLoad().find(x => x.id === id);
  if (!r) return null;
  return (r.records || []).map((x, i) => ({
    i: i + 1, t: x[0], aid: x[1], tokens: 0, secs: x[2], status: "ok",
  })).filter(s => s.aid);
}

// ---------------------------------------------------------------------
// Добавление из итогового экрана и из быстрой пробы
// ---------------------------------------------------------------------

// Один и тот же блок на двух экранах: поле с названием опыта и кнопка.
// Название запоминается, поэтому вторая задача попадает в тот же опыт без
// повторного ввода.
// Элементы помечены классами, а не id: этот блок живёт сразу на двух
// экранах, и поиск по id находил кнопку чужого экрана -- она стоит в
// разметке выше, поэтому обработчик уходил на невидимую кнопку.
function mineAddHTML(kind) {
  return "<div class='mineadd'>" +
    "<span class='lbl'>" + L("mineAdd") + "</span>" +
    "<input class='minename' maxlength='40' value='" + esc(mineName()) +
    "' data-ph='" + esc(L("mineName")) + "' placeholder='" +
    esc(L("mineName")) + "'>" +
    "<button class='mineaddb'>" + L("mineAddBtn") + "</button>" +
    "<span class='mineres mut'></span>" +
    (kind === "quick" ? "<div class='mut'>" + L("mineQuickNote") + "</div>"
                      : "<div class='mut'>" + L("mineScoredBy") + "</div>") +
    "</div>";
}

function mineBind(f, kind, box) {
  const root = box || document;
  const b = root.querySelector(".mineaddb");
  if (!b) return;
  b.onclick = () => {
    const name = mineSetName((root.querySelector(".minename") || {}).value);
    const r = mineAdd(f, kind, name);
    const res = root.querySelector(".mineres");
    if (res && !r.ok) {
      res.textContent = L("mineNoRoom");
      return;
    }
    if (res) {
      res.textContent = L("mineAdded") + " — " + name + ". " +
        (r.replaced ? L("mineReplaced") + ". " : "");
      const a = document.createElement("button");
      a.className = "lnk";
      a.textContent = L("mineOpen");
      a.onclick = () => { if (typeof watchLeave === "function") watchLeave();
                          showCompare(); };
      res.appendChild(a);
    }
    b.disabled = true;
  };
}
