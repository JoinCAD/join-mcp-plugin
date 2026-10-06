import json, sys
# usage: python gapcheck.py <benchmark file> classified.json
# Compares a register with a well-populated one: TARGET or more risks, in the benchmark's typical theme mix.
EXCLUDED = {"Scope Alternates & Value Engineering", "Uncategorized"}
TARGET = 50      # a well-populated register tracks 50+ risks
MIN_GAP = 1.5    # flag a theme when it is at least this many risks short of its share of a well-populated register
MAX_FLAGS = 5
mix = {}
for ln in open(sys.argv[1]).read().strip().splitlines()[1:]:
    t, sh = [x.strip() for x in ln.split("|")]
    mix[t] = float(sh)
reg = json.load(open(sys.argv[2]))
bad = sorted({r["theme"] for r in reg if r["theme"] not in mix and r["theme"] not in EXCLUDED})
if bad:
    sys.exit(f"Unknown theme(s): {bad}")
counted = [r for r in reg if r["theme"] not in EXCLUDED]
n = len(counted)
size = max(TARGET, n)
rows = []
for t, sh in mix.items():
    a = sum(r["theme"] == t for r in counted)
    target = sh * size
    gap = target - a
    status = reason = ""
    if gap >= MIN_GAP:
        status = "missing" if a == 0 else "light"
        reason = (f"none logged; a well-populated register would have about {max(1, round(target))}" if a == 0
                  else f"{a} logged vs about {round(target)} in a well-populated register")
    rows.append(dict(theme=t, count=a, target=round(target, 1), gap=round(gap, 1), status=status, reason=reason, share=sh))
flags = sorted([r for r in rows if r["status"]], key=lambda r: -r["gap"])[:MAX_FLAGS]
print(json.dumps(dict(
    counted=n, not_counted=len(reg) - n, target_size=TARGET, short_by=max(0, TARGET - n),
    flags=[{k: r[k] for k in ("theme", "status", "count", "target", "reason")} for r in flags],
    table=[{k: r[k] for k in ("theme", "count", "target")} for r in sorted(rows, key=lambda r: -r["share"])],
), indent=1))
