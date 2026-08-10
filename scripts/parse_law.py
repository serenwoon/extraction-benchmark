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
    arts = parse(to_text(open(src, encoding="utf-8").read()))
    # 본문이 사실상 비어 있는 항목(삭제된 조문 등)은 제외한다
    arts = [a for a in arts if a["chars"] >= 40]
    json.dump(arts, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(arts)}개 조문 -> {dst}")


if __name__ == "__main__":
    main()
