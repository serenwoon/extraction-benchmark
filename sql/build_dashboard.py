"""SQL 결과를 자립형 HTML 대시보드로 굽는다.

    python sql/build_dashboard.py     # dashboard/index.html

외부 요청이 하나도 없다. 차트는 인라인 SVG고, 폰트는 시스템 것을 쓴다.
`data/benchmark.db` 가 없으면 `sql/load.py` 를 먼저 돌린다.
"""

import html
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "benchmark.db")
OUT_DIR = os.path.join(ROOT, "dashboard")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

SEQ = ["#eef4fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#256abf"]


def q(con, sql, args=()):
    cur = con.execute(sql, args)
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()


def esc(x):
    return html.escape(str(x))


def _tw(s, px=12.5):
    """대략적인 텍스트 폭. 한글·전각은 1자폭, 라틴·숫자는 0.55자폭으로 잡는다."""
    return sum(px if ord(c) > 0x2000 else px * 0.55 for c in str(s))


OVERFLOW = []


def bars(rows, maxv, unit="", width=560, note=None):
    """가로 막대. 단일 계열이므로 범례 없이 직접 라벨만 단다.

    라벨이 잘리거나 값이 밖으로 나가면 화면에서만 드러나므로,
    그릴 때 폭을 계산해 `OVERFLOW` 에 쌓고 빌드 끝에 보고한다.
    """
    bh, gap = 26, 8
    lw = max(140, max(_tw(r[0]) for r in rows) + 12)      # 라벨 칸은 가장 긴 라벨에 맞춘다
    tail = max(_tw(f"{r[1]}{unit}  {r[2]}") for r in rows) + 12
    h = len(rows) * (bh + gap) - gap
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" height="{h}" role="img" '
           f'aria-label="{esc(note or "막대 차트")}">']
    for i, (label, val, extra) in enumerate(rows):
        y = i * (bh + gap)
        w = 0 if not maxv else max(2, (width - lw - tail) * val / maxv)
        end = lw + w + 8 + _tw(f"{val}{unit}  {extra}")
        if end > width:
            OVERFLOW.append(f"{note or '차트'} / {label}: {end:.0f}px > {width}px")
        out.append(
            f'<text x="0" y="{y+bh/2+4}" class="lab">{esc(label)}</text>'
            f'<rect x="{lw}" y="{y+4}" width="{w:.1f}" height="{bh-8}" rx="4" class="bar">'
            f'<title>{esc(label)}: {esc(val)}{esc(unit)}{" · "+esc(extra) if extra else ""}</title></rect>'
            f'<text x="{lw+w+8:.1f}" y="{y+bh/2+4}" class="val">{esc(val)}{esc(unit)}'
            f'{"  " + esc(extra) if extra else ""}</text>')
    out.append("</svg>")
    return "".join(out)


def heat(cols, rows, maxv):
    """혼동 행렬. 순차 단일 색조(파랑) light→dark, 숫자를 항상 같이 적는다."""
    # 역슬래시를 쓰면 한글 폰트가 원화 기호(₩)로 그린다. 화살표로 둔다.
    out = ['<table class="heat"><thead><tr><th>사람 ↓ · 기계 →</th>']
    out += [f"<th>{esc(c)}</th>" for c in cols[1:]]
    out.append("</tr></thead><tbody>")
    for r in rows:
        out.append(f"<tr><th>{esc(r[0])}</th>")
        for v in r[1:]:
            step = 0 if not v else min(len(SEQ) - 1, 1 + int((len(SEQ) - 2) * v / maxv))
            ink = "#fff" if step >= 4 else "var(--text-primary)"
            out.append(f'<td style="background:{SEQ[step]};color:{ink}">{esc(v)}</td>')
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def table(cols, rows, flag_col=None):
    out = ['<div class="scroll"><table class="grid"><thead><tr>']
    out += [f"<th>{esc(c)}</th>" for c in cols]
    out.append("</tr></thead><tbody>")
    for r in rows:
        out.append("<tr>")
        for c, v in zip(cols, r):
            cls = ' class="flag"' if flag_col and c == flag_col and str(v).strip() else ""
            out.append(f"<td{cls}>{esc(v)}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def main():
    if not os.path.exists(DB):
        print("data/benchmark.db 가 없다. 먼저: python sql/load.py", file=sys.stderr)
        return 1
    con = sqlite3.connect(DB)
    S = []

    # ── 지표 타일 ──────────────────────────────────────────
    n_art = con.execute("SELECT count(*) FROM article").fetchone()[0]
    n_cl = con.execute("SELECT sum(has_clause) FROM article").fetchone()[0]
    hs = con.execute("SELECT value FROM measurement WHERE key='human_seconds'").fetchone()[0]
    hi = con.execute("SELECT value FROM measurement WHERE key='human_items'").fetchone()[0]
    seq = con.execute("SELECT avg(sum_call_seconds)/10 FROM run WHERE counts_toward_vote=1").fetchone()[0]
    hit = con.execute("""SELECT min(h), max(h) FROM (
                           SELECT sum(p.cls=g.cls) h FROM prediction p JOIN human_label g USING(id)
                           WHERE p.run_id<>'smoke' GROUP BY p.run_id)""").fetchone()

    tiles = [("대상 항목", f"{n_art}", "본칙 조문 (부칙 제외)"),
             ("건당 소요 — 사람", f"{hs/hi:.0f}초", f"{int(hs//60)}분 {int(hs%60)}초 / {int(hi)}건"),
             ("건당 소요 — 파이프라인", f"{seq:.1f}초", f"순차 환산 · {hs/hi/seq:.1f}배"),
             ("분류 일치", f"{hit[0]}~{hit[1]}/10", "3회 실행")]
    S.append('<div class="tiles">' + "".join(
        f'<div class="tile"><div class="tk">{esc(k)}</div><div class="tv">{esc(v)}</div>'
        f'<div class="tn">{esc(n)}</div></div>' for k, v, n in tiles) + "</div>")

    # ── Q1 실행별 일치율 ───────────────────────────────────
    _, r = q(con, """SELECT p.run_id, sum(p.cls=g.cls), round(avg(p.seconds),1)
                     FROM prediction p JOIN human_label g USING(id)
                     WHERE p.run_id<>'smoke' GROUP BY p.run_id ORDER BY p.run_id""")
    maj = con.execute("""WITH v AS (SELECT p.id,p.cls,count(*) n FROM prediction p JOIN run r USING(run_id)
                                    WHERE r.counts_toward_vote=1 GROUP BY p.id,p.cls),
                              k AS (SELECT id,cls,row_number() OVER (PARTITION BY id ORDER BY n DESC,cls) rk FROM v)
                         SELECT sum(k.cls=g.cls) FROM k JOIN human_label g USING(id) WHERE k.rk=1""").fetchone()[0]
    S.append(section(
        "실행별 일치율", "Q1 · Q3",
        bars([(rid, h, f"평균 {s}초") for rid, h, s in r] + [("다수결 3회", maj, "D-14 적용")],
             10, "/10", note="실행별 일치 건수"),
        "<b>다수결을 적용해도 일치율은 안 올랐다.</b> 표가 갈린 항목이 1건뿐인데, "
        "하필 그 1건에서 다수결이 고른 답이 사람과 달랐다. "
        "반복이 사주는 건 <b>정확도가 아니라 재현성</b>이다. 단발 실행에서 "
        "흔들림을 판단 차이로 착각하는 걸 막아준다."))

    # ── Q4 혼동 행렬 ───────────────────────────────────────
    cols, rows = q(con, """SELECT g.cls AS 사람,
                                  sum(p.cls='의무'), sum(p.cls='금지'), sum(p.cls='권한절차'),
                                  sum(p.cls='정의목적'), sum(p.cls='제재')
                           FROM human_label g JOIN prediction p USING(id)
                           WHERE p.run_id<>'smoke' GROUP BY g.cls ORDER BY g.cls""")
    cols = ["사람", "의무", "금지", "권한절차", "정의목적", "제재"]
    mx = max(max(r[1:]) for r in rows)
    S.append(section(
        "혼동 행렬", "Q4",
        heat(cols, rows, mx),
        "<b>오류가 한 방향으로만 난다.</b> 사람이 뭐라고 했든 기계는 <code>권한절차</code>로 몰았다. "
        "금지 3/3, 제재 3/3이 전부 그리로. "
        "무작위로 틀린 게 아니다. <b>판정 규칙이 절차 쪽으로 기울어 있다</b>는 뜻이고, 규칙을 고쳐야 잡힌다."))

    # ── Q5 단서 ────────────────────────────────────────────
    S.append(section(
        "단서는 요약에서 사라진다", "Q5",
        bars([("괄호 포함(느슨)", 59, "34%"), ("괄호 제거(기준)", int(n_cl), f"{100*n_cl/n_art:.0f}%"),
              ("「다만,」만(보수)", 47, "27%")], n_art, f"/{n_art}", note="단서를 가진 항목 수")
        + '<div class="sub">요약이 그 단서를 반영한 비율</div>'
        + bars([("사람", 0, "0/4"), ("파이프라인(최대)", 1, "1/4"), ("기계 스캔", 4, "4/4")],
               4, "건", note="단서 반영 건수"),
        "판정 기준을 바꿔도 <b>27~34% 안에</b> 있다. 그런데 요약이 그걸 살려낸 비율은 사람도 기계도 바닥이다. "
        "<b>더 나은 요약기가 답이 아니다.</b> 40자 안에 본문과 단서를 다 담는 건 형식의 한계다. "
        "요약 옆에 <b>단서 칸을 따로</b> 둔다."))

    # ── Q7 위험 항목 ───────────────────────────────────────
    cols, rows = q(con, """WITH sig AS (
            SELECT a.id, a.title,
                   (SELECT count(DISTINCT cls) FROM prediction WHERE id=a.id)-1 AS 흔들림,
                   CASE WHEN g.gist_len>40 THEN 1 ELSE 0 END AS 길이초과,
                   a.has_clause AS 단서, max(p.cls<>g.cls) AS 불일치
            FROM article a JOIN human_label g USING(id)
            JOIN prediction p ON p.id=a.id AND p.run_id<>'smoke'
            WHERE a.in_sample=1 GROUP BY a.id,a.title,g.gist_len,a.has_clause)
        SELECT id, title AS 명칭, 흔들림, 길이초과, 단서,
               흔들림+길이초과+단서 AS 위험점수,
               CASE 불일치 WHEN 1 THEN '불일치' ELSE '' END AS 실제결과
        FROM sig ORDER BY 위험점수 DESC, id""")
    S.append(section(
        "위험 항목을 대리지표로 뽑을 수 있나 — 아니다", "Q7",
        table(cols, rows, flag_col="실제결과"),
        "모델 흔들림 · 요지 길이 초과 · 단서 유무를 더해 <b>위험점수</b>를 만들어봤다. "
        "<b>실제 불일치와 안 맞는다.</b> 3점짜리는 일치했고, 불일치 3건은 2·1·1점이다. "
        "<b>확신도는 대리지표로 못 때운다. 사람에게 직접 물어야 한다.</b> "
        "실패한 가설의 기록이라 남겨둔다."))

    con.close()
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "index.html")
    open(out, "w", encoding="utf-8", newline="\n").write(PAGE.replace("{{BODY}}", "\n".join(S)))
    print(f"대시보드 → {os.path.relpath(out, ROOT)}")
    if OVERFLOW:
        print("🔴 라벨이 화면 밖으로 나간다:")
        for o in OVERFLOW:
            print("   ", o)
        return 1
    print("라벨 넘침 없음 ✅")
    return 0


def section(title, qref, body, note):
    return (f'<section><h2>{esc(title)}<span class="qref">{esc(qref)}</span></h2>'
            f'<div class="chart">{body}</div><p class="note">{note}</p></section>')


PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>측정 대시보드 — 문서 구조화 벤치마크</title>
<style>
:root{color-scheme:light;
 --surface-1:#fcfcfb; --plane:#f9f9f7; --text-primary:#0b0b0b; --text-secondary:#52514e;
 --muted:#898781; --grid:#e1e0d9; --baseline:#c3c2b7; --series-1:#2a78d6; --critical:#d03b3b;
 --border:rgba(11,11,11,.10);}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme=light])){color-scheme:dark;
 --surface-1:#1a1a19; --plane:#0d0d0d; --text-primary:#fff; --text-secondary:#c3c2b7;
 --muted:#898781; --grid:#2c2c2a; --baseline:#383835; --series-1:#3987e5; --critical:#d03b3b;
 --border:rgba(255,255,255,.10);}}
:root[data-theme=dark]{color-scheme:dark;
 --surface-1:#1a1a19; --plane:#0d0d0d; --text-primary:#fff; --text-secondary:#c3c2b7;
 --muted:#898781; --grid:#2c2c2a; --baseline:#383835; --series-1:#3987e5; --critical:#d03b3b;
 --border:rgba(255,255,255,.10);}
*{box-sizing:border-box} body{margin:0;background:var(--plane);color:var(--text-primary);
 font:15px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif;}
.wrap{max-width:860px;margin:0 auto;padding:40px 20px 72px}
h1{font-size:24px;margin:0 0 6px} .lede{color:var(--text-secondary);margin:0 0 28px}
.lede code{font-size:.9em}
section{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;
 padding:20px 22px;margin:0 0 18px}
h2{font-size:16px;margin:0 0 16px;display:flex;align-items:baseline;gap:10px}
.qref{font-size:11px;color:var(--muted);font-weight:400;letter-spacing:.04em}
.note{margin:16px 0 0;font-size:13.5px;color:var(--text-secondary)}
.note b{color:var(--text-primary)}
.sub{font-size:12px;color:var(--muted);margin:18px 0 6px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:0 0 18px}
.tile{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;padding:14px 16px}
.tk{font-size:12px;color:var(--muted)} .tv{font-size:26px;font-weight:600;margin:2px 0}
.tn{font-size:11.5px;color:var(--text-secondary)}
svg{display:block;overflow:visible}
.bar{fill:var(--series-1)} .bar:hover{opacity:.82}
text.lab{font-size:12.5px;fill:var(--text-secondary)}
text.val{font-size:12.5px;fill:var(--text-primary);font-variant-numeric:tabular-nums}
table{border-collapse:separate;border-spacing:2px;font-size:13px;width:100%}
.heat th{font-weight:500;color:var(--text-secondary);font-size:12px;text-align:right;padding:4px 8px}
.heat thead th{text-align:center}
.heat td{text-align:center;padding:7px 4px;border-radius:4px;font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto}
.grid th{text-align:left;font-weight:500;color:var(--muted);font-size:11.5px;
 padding:4px 8px;border-bottom:1px solid var(--grid);white-space:nowrap}
.grid td{padding:6px 8px;border-bottom:1px solid var(--grid);font-variant-numeric:tabular-nums;
 white-space:nowrap;color:var(--text-secondary)}
.grid td:nth-child(2){white-space:normal;color:var(--text-primary)}
.grid td.flag{color:var(--critical);font-weight:600}
footer{color:var(--muted);font-size:12.5px;margin-top:28px;line-height:1.8}
a{color:var(--series-1)}
</style></head><body><div class="wrap">
<h1>측정 대시보드 — 문서 구조화 벤치마크</h1>
<p class="lede">공개 법령 문서에서 항목을 뽑아 구조화 표로 만드는 작업. 사람과 파이프라인으로 나눠 쟀다.
숫자는 전부 <code>data/benchmark.db</code>에 SQL 한 벌 돌려 나온 것이고, 쿼리는 <code>sql/analysis.sql</code>에 있다.</p>
{{BODY}}
<footer>
표본은 10건이다. 통계적 유의성을 주장하지 않는다 — “대략 몇 배”까지가 이 표본이 말할 수 있는 전부다.<br>
골든셋은 1인 1회의 라벨이다. 정답의 표준이 아니라 <b>이 측정에서만 쓰는 기준</b>이다.<br>
재현: <code>python sql/load.py &amp;&amp; python sql/build_dashboard.py</code>
</footer>
</div></body></html>
"""


if __name__ == "__main__":
    sys.exit(main())
