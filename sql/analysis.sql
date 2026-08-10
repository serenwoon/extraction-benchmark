-- 측정 결과를 SQL로 다시 재기
--
-- 파일 하나에 질문 일곱 개. 각 블록은 독립 실행 가능하다.
-- 쿼리 3과 7은 문서에만 있던 설계 판단(반복 실행 다수결 / 확신도)을 실제로 구현한 것이다.

-- ─────────────────────────────────────────────────────────────
-- Q1. 실행별 일치율 — 파이프라인이 골든셋과 몇 건이나 같았나
-- ─────────────────────────────────────────────────────────────
SELECT
    p.run_id,
    count(*)                                   AS 채점건수,
    sum(p.cls = g.cls)                         AS 일치,
    round(100.0 * sum(p.cls = g.cls) / count(*), 1) AS 일치율,
    round(avg(p.seconds), 1)                   AS 평균초,
    sum(p.gist_len > m.value)                  AS 글자수규칙_위반
FROM prediction p
JOIN human_label g USING (id)
CROSS JOIN (SELECT value FROM measurement WHERE key = 'gist_limit') m
WHERE p.run_id <> 'smoke'
GROUP BY p.run_id
ORDER BY p.run_id;

-- ─────────────────────────────────────────────────────────────
-- Q2. 자기일관성 — 같은 입력에 매번 같은 답을 내나
--     스모크 실행까지 관측치로 센다(같은 조문·같은 프롬프트였다).
-- ─────────────────────────────────────────────────────────────
SELECT
    p.id,
    a.title,
    count(*)                  AS 관측횟수,
    count(DISTINCT p.cls)     AS 서로다른답,
    group_concat(p.cls)       AS 관측값,
    CASE WHEN count(DISTINCT p.cls) > 1 THEN '흔들림' ELSE '안정' END AS 판정
FROM prediction p
JOIN article a USING (id)
GROUP BY p.id, a.title
ORDER BY 서로다른답 DESC, p.id;

-- ─────────────────────────────────────────────────────────────
-- Q3. 다수결을 적용하면 일치율이 오르나  ← D-14 구현
--     단발 실행을 믿지 말자는 결론을 실제로 계산해 본다.
-- ─────────────────────────────────────────────────────────────
WITH votes AS (
    SELECT p.id, p.cls, count(*) AS n
    FROM prediction p
    JOIN run r USING (run_id)
    WHERE r.counts_toward_vote = 1
    GROUP BY p.id, p.cls
),
ranked AS (
    SELECT id, cls, n,
           row_number() OVER (PARTITION BY id ORDER BY n DESC, cls) AS rk,
           count(*)     OVER (PARTITION BY id)                      AS 후보수
    FROM votes
)
SELECT
    sum(r.cls = g.cls)                              AS 다수결_일치,
    count(*)                                        AS 전체,
    round(100.0 * sum(r.cls = g.cls) / count(*), 1) AS 일치율,
    sum(r.후보수 > 1)                                AS 표가갈린_항목
FROM ranked r
JOIN human_label g USING (id)
WHERE r.rk = 1;

-- ─────────────────────────────────────────────────────────────
-- Q4. 혼동 행렬 — 사람이 X라 한 것을 기계는 무엇이라 했나
-- ─────────────────────────────────────────────────────────────
SELECT
    g.cls AS 사람,
    sum(p.cls = '의무')     AS 의무,
    sum(p.cls = '금지')     AS 금지,
    sum(p.cls = '권한절차') AS 권한절차,
    sum(p.cls = '정의목적') AS 정의목적,
    sum(p.cls = '제재')     AS 제재
FROM human_label g
JOIN prediction p USING (id)
WHERE p.run_id <> 'smoke'
GROUP BY g.cls
ORDER BY g.cls;

-- ─────────────────────────────────────────────────────────────
-- Q5. 단서가 있는 항목이 더 어려웠나
--     말뭉치 전체의 단서 비율과, 표본에서의 일치율을 같이 본다.
-- ─────────────────────────────────────────────────────────────
SELECT '말뭉치 전체' AS 구분,
       count(*) AS 항목수,
       sum(has_clause) AS 단서있음,
       round(100.0 * sum(has_clause) / count(*), 0) AS 비율
FROM article
UNION ALL
SELECT '표본 10건',
       count(*), sum(has_clause),
       round(100.0 * sum(has_clause) / count(*), 0)
FROM article WHERE in_sample = 1;

SELECT
    CASE a.has_clause WHEN 1 THEN '단서 있음' ELSE '단서 없음' END AS 구분,
    count(DISTINCT a.id)                            AS 항목수,
    round(100.0 * sum(p.cls = g.cls) / count(*), 1) AS 일치율,
    round(avg(g.gist_len), 0)                       AS 사람_요지길이,
    round(avg(p.gist_len), 0)                       AS 기계_요지길이
FROM article a
JOIN human_label g USING (id)
JOIN prediction p ON p.id = a.id AND p.run_id <> 'smoke'
WHERE a.in_sample = 1
GROUP BY a.has_clause;

-- ─────────────────────────────────────────────────────────────
-- Q6. 본문이 길면 호출도 오래 걸리나
-- ─────────────────────────────────────────────────────────────
WITH b AS (
    SELECT a.id, a.chars,
           ntile(2) OVER (ORDER BY a.chars) AS 길이구간,
           avg(p.seconds) AS 평균초
    FROM article a
    JOIN prediction p ON p.id = a.id AND p.run_id <> 'smoke'
    WHERE a.in_sample = 1
    GROUP BY a.id, a.chars
)
SELECT CASE 길이구간 WHEN 1 THEN '짧은 절반' ELSE '긴 절반' END AS 구간,
       count(*) AS 항목수,
       round(avg(chars), 0) AS 평균글자,
       round(avg(평균초), 1) AS 평균초
FROM b GROUP BY 길이구간;

-- ─────────────────────────────────────────────────────────────
-- Q7. 위험 항목 랭킹 — 확신도 칸이 없어도 위험한 항목을 뽑을 수 있나  ← D-15 대리
--     신호 셋: 모델이 흔들렸나 / 사람 요지가 길어졌나 / 단서가 있나
-- ─────────────────────────────────────────────────────────────
WITH sig AS (
    SELECT
        a.id, a.title,
        (SELECT count(DISTINCT cls) FROM prediction WHERE id = a.id) - 1 AS 흔들림,
        CASE WHEN g.gist_len > (SELECT value FROM measurement WHERE key='gist_limit')
             THEN 1 ELSE 0 END                                          AS 길이초과,
        a.has_clause                                                    AS 단서,
        max(p.cls <> g.cls)                                             AS 불일치있음
    FROM article a
    JOIN human_label g USING (id)
    JOIN prediction p ON p.id = a.id AND p.run_id <> 'smoke'
    WHERE a.in_sample = 1
    GROUP BY a.id, a.title, g.gist_len, a.has_clause
)
SELECT
    rank() OVER (ORDER BY 흔들림 + 길이초과 + 단서 DESC) AS 순위,
    id, title,
    흔들림, 길이초과, 단서,
    흔들림 + 길이초과 + 단서 AS 위험점수,
    CASE 불일치있음 WHEN 1 THEN '불일치' ELSE '' END AS 실제결과
FROM sig
ORDER BY 위험점수 DESC, id;
