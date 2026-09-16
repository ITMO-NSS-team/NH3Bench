"""Print a compact progress snapshot for the replicated Terra sweep."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


completed = 0
for level in ("none", "low", "medium", "high", "xhigh", "max"):
    cells = []
    for replicate in (2, 3):
        count = line_count(RESULTS / f"terra_reasoning_{level}_r{replicate}.jsonl")
        completed += count
        cells.append(f"r{replicate}={count}/6")
    print(f"{level:6s} " + " ".join(cells))
print(f"new episodes complete: {completed}/72")

for name in (
    "reasoning_rep_a", "reasoning_rep_b", "reasoning_rep_c",
    "reasoning_rep_max2", "reasoning_rep_max3",
):
    path = RESULTS / f"{name}.log"
    if not path.exists():
        continue
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    completed_lines = [line for line in lines if line.startswith("== ") and ": CAT=" in line]
    active_lines = [line for line in lines if line.startswith("== ") and ": старт" in line]
    last_done = completed_lines[-1] if completed_lines else "none"
    last_start = active_lines[-1] if active_lines else "none"
    print(f"{name}:\n  done  {last_done}\n  start {last_start}")
