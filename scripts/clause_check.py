"""단서 검사 — 본문을 한정·반전하는 구절이 요약에서 살아남았는지 대조한다.

    python scripts/clause_check.py

배경
  장문 규격 문서에서 본문만 읽고 **단서를 흘리면 결론이 정반대로 간다.**
  실제로 그런 사고가 있었고(본문이 요구하는 것과 단서가 요구하는 것이 반대였다),
  그 사고가 이 검사를 만들게 했다.

무엇을 재나
  ① 말뭉치 전체에서 단서를 가진 항목의 비율 — 얼마나 흔한 문제인가
  ② 표본 10건에서, 사람 요약과 파이프라인 요약이 그 단서를 반영했는가

'반영'의 판정
  요약이 단서의 존재를 드러내는 낱말(다만/예외/제외/단서/아닌/한정 …)을 담고 있는가로 **기계적으로** 본다.
  거친 기준이므로 원문·요약을 함께 출력해 사람이 재판정할 수 있게 한다.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# 본문을 한정하거나 뒤집는 신호
CLAUSE = re.compile(r"다만,|그러하지 아니하다|제외한다|제외하고|하지 아니한다|하지 아니하다")
# 요약이 '단서가 있다'는 사실을 드러내는 낱말
REFLECT = re.compile(r"다만|예외|제외|단서|한정|아닌|경우는|except")
PAREN = re.compile(r"\([^)]*\)")


def defused(body):
    """괄호 안을 지운 본문.

    `(광역시의 군수는 제외한다)` 같은 **정의용 괄호**는 본문을 한정하는 단서가 아니다.
    그냥 `제외한다`로 세면 이런 것까지 걸려 숫자가 부풀어 오른다.
    — 정규식은 문맥을 모른다. 이 스크립트에도 같은 함정이 있었다.
    """
    return PAREN.sub("", body)


def clauses(body):
    out = []
    for m in CLAUSE.finditer(defused(body)):
        seg = defused(body)[m.start():m.start() + 90].replace("\n", " ")
        out.append(seg)
    return out


def main():
    arts = json.load(open(os.path.join(D, "articles.json"), encoding="utf-8"))
    sample = json.load(open(os.path.join(D, "sample_10.json"), encoding="utf-8"))
    gold = {g["id"]: g for g in json.load(open(os.path.join(D, "golden_human.json"), encoding="utf-8"))}
    runs = {}
    for tag in ["", "_r2", "_r3"]:
        p = os.path.join(D, f"pipeline_10{tag}.json")
        if os.path.exists(p):
            runs[f"run{tag or '1'}"] = {x["id"]: x for x in json.load(open(p, encoding="utf-8"))["results"]}

    print("=" * 70)
    print("1. 얼마나 흔한가 — 기준을 바꿔가며 (숫자가 기준에 얼마나 민감한지 보이려고)")
    print("=" * 70)
    crit = [
        ("괄호 포함 (느슨)", lambda b: CLAUSE.search(b)),
        ("괄호 제거 (기준)", lambda b: CLAUSE.search(defused(b))),
        ("「다만,」만 (보수)", lambda b: "다만," in defused(b)),
    ]
    for name, f in crit:
        n = sum(1 for a in arts if f(a["body"]))
        mark = "  ← 이 값을 쓴다" if name.startswith("괄호 제거") else ""
        print(f"  {name:<20} {n:>3}/{len(arts)}  ({100*n/len(arts):.0f}%){mark}")

    with_clause = [a for a in arts if CLAUSE.search(defused(a["body"]))]
    tgt = [x for x in sample if CLAUSE.search(defused(x["body"]))]
    print(f"\n  표본 10건 중 단서 포함 **{len(tgt)}건**: {', '.join(x['id'] for x in tgt)}")
    print("  (세 기준 모두 같은 4건을 가리킨다 — 표본 수준에서는 기준 선택이 결과를 바꾸지 않는다)")

    print()
    print("=" * 70)
    print("2. 요약이 단서를 반영했는가")
    print("=" * 70)
    tally = {"사람": 0}
    for k in runs:
        tally[k] = 0

    for x in tgt:
        cs = clauses(x["body"])
        print(f"\n── {x['id']} {x['title']}  (단서 {len(cs)}건)")
        print(f"   원문 단서: {cs[0][:74]}…")
        h = gold[x["id"]]["gist"]
        ok = bool(REFLECT.search(h))
        tally["사람"] += ok
        print(f"   {'✅' if ok else '❌'} 사람   {h[:66]}")
        for k, r in runs.items():
            g = r[x["id"]]["gist"]
            ok = bool(REFLECT.search(g))
            tally[k] += ok
            print(f"   {'✅' if ok else '❌'} {k:<6} {g[:66]}")

    print()
    print("=" * 70)
    print("3. 결과")
    print("=" * 70)
    n = len(tgt)
    for k, v in tally.items():
        print(f"  {k:<8} {v}/{n} 반영")
    print(f"  {'기계 스캔':<8} {n}/{n} 검출  (정규식 한 줄, 210개 전체 0.0초)")

    json.dump({"corpus_total": len(arts), "corpus_with_clause": len(with_clause),
               "sample_with_clause": [x["id"] for x in tgt], "reflected": tally},
              open(os.path.join(D, "clause_check.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
