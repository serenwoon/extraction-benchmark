"""파이프라인 쪽 측정 — 조문 하나당 claude CLI 를 독립 호출해 분류·요지를 뽑는다.

    python scripts/run_pipeline.py [--limit N] [--workers K]

설계 메모
  · 호출을 **조문 단위로 분리**한다. 한 번에 10건을 주면 모델이 서로를 보고 판단이 섞이는데,
    사람은 한 건씩 봤으므로 그 조건을 맞춘다.
  · 프롬프트의 분류 정의·판정 규칙은 `manual/worksheet.md` 와 **글자 그대로 같다.**
    사람과 다른 지침을 주면 일치율이 지침 차이인지 능력 차이인지 알 수 없다.
  · 사람 답은 이 스크립트에 들어오지 않는다. 별도 프로세스라 컨텍스트도 공유하지 않는다.
"""

import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

RUBRIC = """다음 5종 중 하나로 분류한다.

- `의무`: 특정 주체가 무엇을 해야 한다고 정한 것
- `금지`: 하면 안 된다 / 통행·행위를 제한하는 것
- `권한절차`: 행정청·기관이 무엇을 할 수 있다, 또는 지정·신고·발급·교육 등의 절차를 정한 것
- `정의목적`: 용어·개념·목적을 규정한 것
- `제재`: 벌칙·과태료·통고처분·면허 정지취소 등 불이익 처분

판정 규칙
1. 주된 것 하나만 고른다. 여러 성격이 섞여 있어도 복수 선택하지 않는다
2. 갈리면 그 조문이 없으면 무엇이 불가능해지는가로 정한다
3. 의무와 제재가 같이 있으면 의무가 주된 것이다 (제재는 그 의무의 담보다)
4. 절차 안에 의무가 들어 있으면 권한절차다 (절차가 조문의 뼈대이므로)"""

PROMPT = """너는 법령 조문을 읽고 요구사항 추적표를 만드는 작업을 한다.

{rubric}

아래 조문을 읽고 두 가지를 정하라.
- cls: 위 5종 중 하나
- gist: 40자 이내 한 줄 요약. "무엇을 어떻게 하라고 정한 조문인가"를 쓴다

조문 {label} ({title})
---
{body}
---

JSON 한 줄로만 답하라. 다른 설명은 쓰지 마라.
{{"cls": "...", "gist": "..."}}"""


def one(art):
    p = PROMPT.format(rubric=RUBRIC, label=art["label"], title=art["title"], body=art["body"])
    t0 = time.time()
    r = subprocess.run(
        ["claude", "-p", p],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
    )
    el = time.time() - t0
    out = (r.stdout or "").strip()
    m = re.search(r"\{.*\}", out, re.S)
    parsed = {}
    if m:
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {
        "id": art["id"], "title": art["title"],
        "cls": str(parsed.get("cls", "")).strip().strip("`"),
        "gist": str(parsed.get("gist", "")).strip(),
        "seconds": round(el, 1),
        "ok": bool(parsed),
        "raw": out[:400] if not parsed else "",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--tag", default="", help="출력 파일 접미사. 반복 실행 비교용")
    a = ap.parse_args()

    arts = json.load(open(os.path.join(ROOT, "data", "sample_10.json"), encoding="utf-8"))
    if a.limit:
        arts = arts[: a.limit]

    wall0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        res = list(ex.map(one, arts))
    wall = time.time() - wall0
    res.sort(key=lambda x: x["id"])

    out = {
        "wall_seconds": round(wall, 1),
        "n": len(res),
        "workers": a.workers,
        "per_item_wall": round(wall / len(res), 1),
        "sum_call_seconds": round(sum(r["seconds"] for r in res), 1),
        "results": res,
    }
    dst = os.path.join(ROOT, "data", f"pipeline_{len(res)}{a.tag}.json")
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"벽시계 {wall:.1f}초 / {len(res)}건 · 동시 {a.workers} · 건당 {wall/len(res):.1f}초")
    print(f"호출시간 합 {out['sum_call_seconds']}초 (순차였다면 이만큼)")
    for r in res:
        flag = "" if r["ok"] else "  ❌파싱실패"
        print(f"  {r['id']:<11}{r['cls']:<9}{r['seconds']:>5}s  {r['gist'][:44]}{flag}")
    print(f"\n-> {dst}")


if __name__ == "__main__":
    main()
