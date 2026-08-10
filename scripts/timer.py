"""사람 작업 시간을 기록한다.  python scripts/timer.py start|stop|show"""

import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "data", "timing.json")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def load():
    return json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else {}


def save(d):
    json.dump(d, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    d = load()
    now = datetime.datetime.now()

    if cmd == "start":
        d["manual_start"] = now.isoformat(timespec="seconds")
        d.pop("manual_end", None)
        save(d)
        print(f"⏱  시작 {now:%H:%M:%S}  — 20분 뒤 {now + datetime.timedelta(minutes=20):%H:%M:%S} 에는 멈춘다")

    elif cmd == "stop":
        if "manual_start" not in d:
            print("먼저 start 를 실행하세요.")
            return
        d["manual_end"] = now.isoformat(timespec="seconds")
        save(d)
        el = (now - datetime.datetime.fromisoformat(d["manual_start"])).total_seconds()
        print(f"⏹  종료 {now:%H:%M:%S}  — 소요 {int(el // 60)}분 {int(el % 60)}초")

    else:
        if "manual_start" not in d:
            print("아직 시작 전입니다.")
            return
        s = datetime.datetime.fromisoformat(d["manual_start"])
        e = datetime.datetime.fromisoformat(d["manual_end"]) if "manual_end" in d else now
        el = (e - s).total_seconds()
        state = "완료" if "manual_end" in d else "진행 중"
        print(f"{state}: {int(el // 60)}분 {int(el % 60)}초")


if __name__ == "__main__":
    main()
