"""채점 — 사람(골든셋) vs 파이프라인, 그리고 파이프라인의 자기일관성.

    python scripts/score.py
"""

import glob
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def load(p):
    return json.load(open(p, encoding="utf-8"))


def main():
    gold = {g["id"]: g for g in load(os.path.join(D, "golden_human.json"))}
    timing = load(os.path.join(D, "timing.json")) if os.path.exists(os.path.join(D, "timing.json")) else {}

    runs = []
    for p in sorted(glob.glob(os.path.join(D, "pipeline_10*.json"))):
        runs.append((os.path.basename(p).replace("pipeline_10", "run").replace(".json", "") or "run1", load(p)))
    # 1건짜리 스모크 실행도 관측치로 센다 (같은 조문, 같은 프롬프트)
    smoke = load(os.path.join(D, "pipeline_1.json")) if os.path.exists(os.path.join(D, "pipeline_1.json")) else None

    print("=" * 66)
    print("1. 분류 일치율 — 사람 답을 골든셋으로")
    print("=" * 66)
    per_run = {}
    for name, r in runs:
        hit = sum(1 for x in r["results"] if x["cls"] == gold[x["id"]]["cls"])
        per_run[name] = hit
        print(f"  {name:<6} {hit}/{len(r['results'])}  ({100*hit/len(r['results']):.0f}%)")

    print()
    print("=" * 66)
    print("2. 건별 — 사람 vs 각 실행")
    print("=" * 66)
    print(f"  {'ID':<11}{'사람':<8}" + "".join(f"{n:<9}" for n, _ in runs) + "판정")
    obs = defaultdict(list)
    for name, r in runs:
        for x in r["results"]:
            obs[x["id"]].append(x["cls"])
    if smoke:
        for x in smoke["results"]:
            obs[x["id"]].append(x["cls"])

    stable_dis, noise = [], []
    for aid in sorted(gold):
        h = gold[aid]["cls"]
        cells = [next(x["cls"] for x in r["results"] if x["id"] == aid) for _, r in runs]
        uniq = set(cells)
        if len(uniq) > 1:
            verdict = "⚠ 모델 흔들림"
            noise.append(aid)
        elif cells[0] == h:
            verdict = "✅ 일치"
        else:
            verdict = "❌ 판단 차이(일관됨)"
            stable_dis.append((aid, h, cells[0]))
        print(f"  {aid:<11}{h:<8}" + "".join(f"{c:<9}" for c in cells) + verdict)

    print()
    print("=" * 66)
    print("3. 파이프라인 자기일관성 (같은 입력·같은 프롬프트 반복)")
    print("=" * 66)
    for aid in sorted(obs):
        c = Counter(obs[aid])
        if len(c) > 1:
            print(f"  ⚠ {aid}: " + " / ".join(f"{k}×{v}" for k, v in c.most_common()) + f"   ← 관측 {sum(c.values())}회")
    unstable = [a for a in obs if len(set(obs[a])) > 1]
    print(f"  안정 {len(obs)-len(unstable)}/{len(obs)}건 · 흔들림 {len(unstable)}건")

    print()
    print("=" * 66)
    print("4. 시간")
    print("=" * 66)
    hs = timing.get("human_seconds")
    n_done = timing.get("human_items", len(gold))
    if hs:
        print(f"  사람       총 {hs//60:.0f}분 {hs%60:.0f}초 / {n_done}건  →  건당 {hs/n_done:.1f}초")
    wall = sum(r["wall_seconds"] for _, r in runs) / len(runs)
    seq = sum(r["sum_call_seconds"] for _, r in runs) / len(runs)
    n = len(gold)
    print(f"  파이프라인 벽시계 평균 {wall:.1f}초 / {n}건 (동시 {runs[0][1]['workers']})  →  건당 {wall/n:.1f}초")
    print(f"  파이프라인 순차 환산 {seq:.1f}초 / {n}건                    →  건당 {seq/n:.1f}초")
    if hs:
        print()
        print(f"  ▶ 배수(병렬 기준) {hs/n_done/(wall/n):.0f}배   ▶ 배수(순차 환산, 보수적) {hs/n_done/(seq/n):.1f}배")

    print()
    print("=" * 66)
    print("5. 요지 길이 — 규칙은 '40자 이내'였다")
    print("=" * 66)
    hl = [len(g["gist"]) for g in gold.values()]
    print(f"  사람       평균 {sum(hl)//len(hl)}자 · 최대 {max(hl)}자 · 40자 초과 {sum(1 for x in hl if x>40)}/{len(hl)}건")
    for name, r in runs:
        pl = [len(x["gist"]) for x in r["results"]]
        print(f"  {name:<10} 평균 {sum(pl)//len(pl)}자 · 최대 {max(pl)}자 · 40자 초과 {sum(1 for x in pl if x>40)}/{len(pl)}건")

    print()
    print("=" * 66)
    print("6. 일관된 판단 차이 — 라벨링 가이드가 고쳐야 할 것")
    print("=" * 66)
    for aid, h, p in stable_dis:
        print(f"  {aid} ({gold[aid]['title']})")
        print(f"      사람 {h}  vs  파이프라인 {p}")
    if not stable_dis:
        print("  없음")

    json.dump(
        {"per_run_hits": per_run, "stable_disagreements": stable_dis, "unstable_items": unstable,
         "wall_mean": wall, "seq_mean": seq},
        open(os.path.join(D, "score.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
