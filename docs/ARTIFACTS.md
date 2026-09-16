# Generated artifacts

Three HTML deliverables are produced from this repo. They are build outputs — regenerate
rather than hand-edit. All are single self-contained files (inline CSS/JS/base64 assets).

| Artifact | Built by | Audience |
|---|---|---|
| `viz/nh3bench-expert-guide.html` (~750 KB) | `viz/build_expert_doc.py` | plant operator validating realism |
| `trainer/nh3bench-demo.html` (~3.3 MB) | `trainer/build_trainer.py` | same operator, hands-on |
| `nh3twin-hmi.html` (~290 KB) | `viz/build_html.py` | internal — ISA-101 mnemonic with trends |
| `NH3Ops-Bench-design.md` | hand-written | benchmark design, Russian (`docs/DESIGN-original-ru.md`) |

---

## Expert validation document

Three-stage build:

```bash
python3 viz/expert_data.py        # runs the twin, dumps viz/expert_data.json
python3 viz/expert_figs.py        # matplotlib → viz/expert_figs.json (base64 PNG)
python3 viz/build_expert_doc.py   # assembles HTML with inline SVG schematics
```

Written in the genre of a Russian противоаварийная тренировка (emergency drill): briefing →
planted faults → timeline under inaction → correct actions → typical errors → questions for
the expert. Nine sections, 11 figures (5 hand-built SVG schematics + 6 charts from real
runs), and a Д/У/Н review sheet.

**All curves come from actual simulation runs** — this is stated in the document and is the
point: the expert validates real behavior, not illustrations. If you retune a scenario,
rebuild the figures or the document lies.

Text lives in `viz/expert_doc_text.py` (Russian), schematics as SVG string constants in
`viz/build_expert_doc.py`.

## Browser trainer

```bash
python3 trainer/build_trainer.py
```

Embeds 12 twin source files plus `trainer/driver.py` as base64, loads Pyodide v0.26.4 from
jsDelivr in a Web Worker, and unpacks them to `/app` in the browser filesystem. The expert
plays the same scenarios agents face; wall-clock thinking time × a chosen scale (×1/×2/×4)
becomes virtual seconds. Pause is allowed but flagged in the protocol.

Screens: load → menu → briefing → play → debrief. The play screen has the pixel map, a
gauge panel in Russian notation, alarms, equipment cards, personnel/dispatch, a grouped
action catalog with search, and a shift log. Debrief compares the expert's outcome with all
four reference policies and offers a JSON protocol download plus a free-text remark field.

Two honesty features worth preserving:
- **"сырой текст щита"** shows the observation exactly as the agent model receives it.
- **Self-test button** runs S1 with no intervention and checks CAT-3 at ~614 s against the
  CPython reference — this is how a user detects Pyodide divergence without trusting us.

When scenario calibration changes, update the `REF` dict in `trainer/build_trainer.py`;
it feeds the debrief comparison table.

### pix.js notes
384×216 logical pixels, integer scale 2–4×. Static scene (rooms, walls, corridor, tank
bodies, base frost) is rendered once into a cached canvas; only animation runs per frame
(~2 650 fillRects, down from ~67 000 before caching). Operator positions interpolate from
dispatch timings (`from`/`t0`/`ta`/`td`), so people keep walking while the expert thinks.
Click regions are declared in `HITS`; operators are hit-tested first via `wpos`.
