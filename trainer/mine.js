// =====================================================================
// The visitor's own runs in the results table.
//
// The score is not computed here: it comes from the twin, where the same
// metrics.bench_score_run that produced the cells in results/ computed it
// (see driver.Session._score). This file only stores, aggregates and
// deletes -- otherwise a person's row would not be comparable with a
// model's row.
//
// Storage is this browser's localStorage. Nothing is sent anywhere, and
// the table says so: an experiment run at a conference stand must not
// look like part of the published set.
// =====================================================================

const MINE_KEY = "nh3.myruns";
const MINE_NAME_KEY = "nh3.myname";
const MINE_MAX = 200;              // more is pointless in localStorage

// Russian labels; the English ones are in I18N_JS under the same keys.
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
  } catch (e) { return dflt; }        // a private window -- simply no memory
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

// A run assembled from the task result. The score is taken as it is; a
// hand-stopped run and a quick try do not enter the mean -- neither is a
// complete task.
function mineRun(f, kind, name) {
  const sc = (typeof SCEN !== "undefined")
    ? SCEN.find(x => x.sid === f.sid) : null;
  const forced = !!f.forced;
  // The command sequence is stored with the result: without it the visitor's
  // run could not be placed next to a model's run in the decision comparison.
  // Compact form -- [second, command, cost of the decision in seconds].
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
    // The task language is part of what the person read, exactly as for a
    // model.
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

// Adding replaces the previous result of the same task in the same
// experiment. Otherwise one row would hold several attempts at one task, and
// it would be unclear which of them is in the mean.
function mineAdd(f, kind, name) {
  const r = mineRun(f, kind, name);
  const arr = mineLoad();
  const kept = arr.filter(x => !(x.kind === r.kind && x.agent === r.agent
                                 && x.scenario === r.scenario));
  const replaced = arr.length - kept.length;
  kept.push(r);
  // The storage answer matters: in a private window and when the quota is
  // exhausted the write does not go through, and saying "added" would then be
  // a lie.
  const ok = mineSave(kept);
  return { run: r, replaced: replaced, ok: ok };
}

function mineDelAgent(kind, agent) {
  mineSave(mineLoad().filter(x => !(x.kind === kind && x.agent === agent)));
}

function mineClear() {
  try { localStorage.removeItem(MINE_KEY); } catch (e) { /* already empty */ }
}

// Aggregation into table rows by the same rules as demo_manifest: the mean
// covers scored tasks only, and the Regulation Gap only a complete row. A
// mean over part of the tasks is not comparable with a mean over all of them.
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
  // Complete rows first, then by the mean; the quick try goes last.
  return out.sort((x, y) => (x.kind === "quick") - (y.kind === "quick")
                            || (y.score_mean || 0) - (x.score_mean || 0));
}

// ---------------------------------------------------------------------
// The visitor's run in the decision comparison
//
// The comparison aligns two command sequences; the physics of a person's
// run is the same as a model's, so the rows are commensurable. Nothing is
// recomputed here: times, commands and the cost of a decision come from
// the stored record.
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
    // The record does not go into Watch: the twin does not replay it, that
    // needs a per-decision transcript with tokens. In the decision comparison
    // it is complete as it is.
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

// A person's decision costs seconds, not tokens: they spend none, but the
// twin charged their deliberation to the task clock in exactly those seconds.
function mineDiffSteps(id) {
  const r = mineLoad().find(x => x.id === id);
  if (!r) return null;
  return (r.records || []).map((x, i) => ({
    i: i + 1, t: x[0], aid: x[1], tokens: 0, secs: x[2], status: "ok",
  })).filter(s => s.aid);
}

// ---------------------------------------------------------------------
// Adding from the result screen and from the quick try
// ---------------------------------------------------------------------

// One and the same block on two screens: the experiment-name field and the
// button. The name is remembered, so the second task lands in the same
// experiment without typing it again.
//
// The parts are marked with classes rather than ids: this block lives on two
// screens at once, and a lookup by id found the other screen's button -- it
// sits higher in the markup, so the handler went to an invisible button.
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
