"""위키문헌 「대한민국 도로교통법」 HTML에서 조문을 뽑아 JSON으로 만든다.

재현:
    curl -sL -A "<UA>" "https://ko.wikisource.org/wiki/대한민국_도로교통법" -o data/raw.html
    python scripts/parse_law.py data/raw.html data/articles.json
"""

import html
import json
import re
import sys

ART_RE = re.compile(r"^제(\d+)조(?:의(\d+))?\s*\(([^)]{1,60})\)", re.M)

# 부칙 절의 시작. 목차에도 "부칙"이 나오므로 `[편집]` 이 붙은 실제 절 머리로 판정한다.
SUPPL_RE = re.compile(r"^\s*부\s*칙\s*\n\s*\[편집\]", re.M)


def to_text(raw_html: str) -> str:
    m = re.search(r'(?is)<div class="mw-parser-output">(.*?)<!--\s*NewPP', raw_html) or re.search(
        r'(?is)<div class="mw-parser-output">(.*)', raw_html
    )
    body = m.group(1) if m else raw_html
    body = re.sub(r"(?is)<(script|style|table).*?</\1>", "", body)
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = re.sub(r"(?i)</(p|div|li|h[1-6]|dd|dt)>", "\n", body)
    text = html.unescape(re.sub(r"<[^>]+>", "", body))
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text)


def parse(text: str):
    hits = list(ART_RE.finditer(text))
    out = []
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        num, sub, title = m.group(1), m.group(2), m.group(3)
        label = f"제{num}조" + (f"의{sub}" if sub else "")
        body = text[m.end():end].strip()
        out.append(
            {
                "id": f"RTA-{int(num):03d}" + (f"-{int(sub)}" if sub else ""),
                "label": label,
                "title": title.strip(),
                "body": body,
                "chars": len(body),
            }
        )
    return out


def main():
    src, dst = sys.argv[1], sys.argv[2]
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    text = to_text(open(src, encoding="utf-8").read())

    # 🔴 부칙을 잘라낸다.
    #   부칙은 조 번호가 1부터 다시 시작한다(시행일·경과조치). 본칙과 같이 세면
    #   "제3조"가 여러 개가 되고, 조문 수도 부풀어 오른다.
    m = SUPPL_RE.search(text)
    if m:
        dropped = len(parse(text[m.start():]))
        text = text[:m.start()]
        print(f"부칙 {dropped}개 조문 제외 (조 번호가 1부터 다시 시작한다)")
    else:
        print("⚠ 부칙 절을 못 찾았다. 본칙만인지 확인할 것.")

    arts = [a for a in parse(text) if a["chars"] >= 40]

    # 같은 조가 개정 전·후 판본으로 두 번 실린 경우가 있다. 마지막(최신)을 쓴다.
    # 조용히 버리지 않고 무엇을 버렸는지 찍는다.
    seen = {}
    for a in arts:
        if a["id"] in seen:
            print(f"  중복 {a['id']} ({a['title']}) — {seen[a['id']]['chars']}자 버리고 {a['chars']}자 채택")
        seen[a["id"]] = a
    arts = list(seen.values())

    json.dump(arts, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(arts)}개 조문 -> {dst}")


if __name__ == "__main__":
    main()
