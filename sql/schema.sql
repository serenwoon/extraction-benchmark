-- 측정 결과를 SQL로 다시 재기 위한 스키마
--
-- 설계 메모
--   · 측정 기록이 JSON 파일 일곱 개에 흩어져 있어서, "실행별로 나눠 보기"나
--     "단서가 있는 항목만 골라 보기" 같은 질문에 매번 스크립트를 새로 짜야 했다.
--     조인 한 번이면 되는 일이다.
--   · article 이 사실상 유일한 차원 테이블이고 나머지가 그 위에 붙는다.
--   · 파생값(gist_len, has_clause)은 적재할 때 계산해 넣는다.
--     쿼리마다 다시 세면 정의가 갈라진다 — 정의는 한 곳에만 둔다.

DROP TABLE IF EXISTS prediction;
DROP TABLE IF EXISTS human_label;
DROP TABLE IF EXISTS run;
DROP TABLE IF EXISTS article;
DROP TABLE IF EXISTS measurement;

-- 조문 210개. 표본 여부와 단서 유무를 함께 들고 있다.
CREATE TABLE article (
    id           TEXT PRIMARY KEY,   -- RTA-003
    label        TEXT NOT NULL,      -- 제3조
    title        TEXT NOT NULL,
    chars        INTEGER NOT NULL,   -- 본문 길이
    in_sample    INTEGER NOT NULL,   -- 표본 10건에 들어갔나 (0/1)
    clause_count INTEGER NOT NULL,   -- 본문을 한정·반전하는 단서 개수 (괄호 제거 후)
    has_clause   INTEGER NOT NULL    -- clause_count > 0
);

-- 파이프라인 실행 회차. 스모크 실행(n=1)도 관측치로 센다.
CREATE TABLE run (
    run_id            TEXT PRIMARY KEY,  -- run1 / run_r2 / run_r3 / smoke
    n_items           INTEGER NOT NULL,
    workers           INTEGER NOT NULL,
    wall_seconds      REAL    NOT NULL,  -- 벽시계 (병렬)
    sum_call_seconds  REAL    NOT NULL,  -- 호출시간 합 (순차 환산)
    counts_toward_vote INTEGER NOT NULL  -- 다수결에 포함하나. 스모크는 10건이 아니라 제외
);

-- 사람이 AI 없이 채운 답 = 골든셋
CREATE TABLE human_label (
    id       TEXT PRIMARY KEY REFERENCES article(id),
    cls      TEXT NOT NULL,
    gist     TEXT NOT NULL,
    gist_len INTEGER NOT NULL
);

-- 파이프라인 예측
CREATE TABLE prediction (
    run_id   TEXT NOT NULL REFERENCES run(run_id),
    id       TEXT NOT NULL REFERENCES article(id),
    cls      TEXT NOT NULL,
    gist     TEXT NOT NULL,
    gist_len INTEGER NOT NULL,
    seconds  REAL NOT NULL,
    PRIMARY KEY (run_id, id)
);

-- 사람 쪽 측정 등 단일 수치. 이름-값으로 둔다.
CREATE TABLE measurement (
    key   TEXT PRIMARY KEY,
    value REAL NOT NULL,
    note  TEXT
);
