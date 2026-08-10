"""측정 기록 JSON을 SQLite 로 적재한다.

    python sql/load.py            # data/benchmark.db 생성

단서 판정은 `scripts/clause_check.py` 에서 **가져다 쓴다.** 여기서 다시 구현하면
같은 정의가 두 곳에 생기고, 한쪽만 고치는 순간 숫자가 갈라진다.
"""

import importlib.util
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
DB = os.path.join(D, "benchmark.db")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def _clause_module():
    spec = importlib.util.spec_from_file_location(
        "clause_check", os.path.join(ROOT, "scripts", "clause_check.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load_json(name):
    return json.load(open(os.path.join(D, name), encoding="utf-8"))


def main():
    cc = _clause_module()
    articles = load_json("articles.json")
    sample_ids = {x["id"] for x in load_json("sample_10.json")}
    gold = load_json("golden_human.json")
    timing = load_json("timing.json")

    runs = [("run1", "pipeline_10.json", 1), ("run_r2", "pipeline_10_r2.json", 1),
            ("run_r3", "pipeline_10_r3.json", 1), ("smoke", "pipeline_1.json", 0)]

    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    con.executescript(open(os.path.join(ROOT, "sql", "schema.sql"), encoding="utf-8").read())

    con.executemany(
        "INSERT INTO article VALUES (?,?,?,?,?,?,?)",
        [(a["id"], a["label"], a["title"], a["chars"],
          1 if a["id"] in sample_ids else 0,
          len(cc.clauses(a["body"])),
          1 if cc.CLAUSE.search(cc.defused(a["body"])) else 0) for a in articles])

    con.executemany(
        "INSERT INTO human_label VALUES (?,?,?,?)",
        [(g["id"], g["cls"], g["gist"], len(g["gist"])) for g in gold])

    for run_id, fname, votes in runs:
        r = load_json(fname)
        con.execute("INSERT INTO run VALUES (?,?,?,?,?,?)",
                    (run_id, r["n"], r["workers"], r["wall_seconds"],
                     r["sum_call_seconds"], votes))
        con.executemany(
            "INSERT INTO prediction VALUES (?,?,?,?,?,?)",
            [(run_id, x["id"], x["cls"], x["gist"], len(x["gist"]), x["seconds"])
             for x in r["results"]])

    con.executemany(
        "INSERT INTO measurement VALUES (?,?,?)",
        [("human_seconds", timing["human_seconds"], "사람이 10건을 채운 총 소요"),
         ("human_items", timing["human_items"], "사람이 완료한 건수"),
         ("gist_limit", 40, "요지 글자수 규칙")])

    con.commit()

    print(f"적재 완료 → {os.path.relpath(DB, ROOT)}")
    for t in ("article", "run", "human_label", "prediction", "measurement"):
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"  {t:<14} {n:>4} 행")
    con.close()


if __name__ == "__main__":
    main()
