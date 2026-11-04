"""讀取一個 run_eval.py 的結果檔，自動計分並產出報告。

用法：
    uv run python eval/score.py --results-dir eval/results/v2   # v2：該資料夾最新的結果，Q01–Q20 自動和 v1 比較
    uv run python eval/score.py eval/results/<時間>_<模型>.jsonl
    uv run python eval/score.py            # 不給參數就用 eval/results/（v1）最新的結果檔

產出（都放在結果資料夾裡，例如 eval/results/v2/）：
    manual_review.md  manual_rubric、set_recall 題目，以及所有判為需人工的回答；第一次執行時產生，
                      已存在時不覆蓋（除非加 --overwrite-manual）
    summary.md        人工分數填完後再執行一次才會產生。Q01–Q20 與 Q21–Q25 分開計分，
                      Q01–Q20 並與 v1（eval/results/）比較

每次回答的判定只有四種：
    pass    自動比對全部通過
    fail    自動比對確定錯誤
    manual  需人工確認（例如藥名被翻成中文、趨勢用詞模稜兩可、manual_rubric 題）
    error   API 呼叫失敗，沒有回答
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = ROOT / "eval" / "questions.json"
RESULTS_DIR = ROOT / "eval" / "results"

EDGE_CATEGORY = "edge"
MANUAL_REVIEW_SCORING = {"manual_rubric", "set_recall"}

DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
# 回答裡任何日期寫法：2021-05-27、2021/5/27、2021.05.27、2021年5月27日
ANY_DATE_IN_TEXT = re.compile(r"(?<!\d)\d{4}\s*[-/.年]\s*\d{1,2}\s*[-/.月]\s*\d{1,2}\s*日?(?:T[\d:.+-]+)?")
NUMBER_RE = re.compile(r"(?<![\d.])\d+(?:\.\d+)?")

GENDER_WORDS = {
    "female": ["female", "女"],
    "male": ["male", "男"],
}
DIRECTION_WORDS = {
    "上升": ["上升", "升高", "增加", "上揚", "變高", "走高"],
    "下降": ["下降", "降低", "減少", "下滑", "變低", "走低"],
    "持平": ["持平", "平穩", "穩定", "不變", "沒有變化", "無變化", "維持", "相同", "一樣"],
}
# 藥名中不能拿來當關鍵字的劑型、單位字
MED_STOPWORDS = {"oral", "tablet", "tablets", "capsule", "extended", "release", "hydrochloride",
                 "sodium", "vaginal", "ring", "prefilled", "syringe", "injector", "suspension",
                 "day", "per", "auto"}
MED_HINT = re.compile(r"\b(MG|ML|Tablet|Capsule|Ring|Injector|Syringe|Suspension)\b", re.I)
# 回答中任何 ICD-10 碼（E11.9、I10、E119 這類寫法）
ICD10_IN_TEXT = re.compile(r"(?<![A-Za-z0-9])([A-TV-Z]\d{2}(?:\.?\d{1,4})?)(?![A-Za-z0-9])")
# 是否 65 歲以上：判斷回答是肯定還是否定
OVER_65_YES = re.compile(r"(已滿|年滿|超過|大於|≥)\s*65|65\s*歲\s*(以上|或以上)\s*[：:]?\s*(是|符合)")
OVER_65_NO = re.compile(r"(未滿|不到|未達|低於|小於|不滿|尚未|沒有超過|並非|不是|非)\s*(年滿\s*)?65"
                        r"|65\s*歲\s*以上\s*[？?]?\s*[：:]?\s*(否|不是|未)")


# ---------- exact_value ----------

def date_in_answer(iso: str, answer: str) -> bool:
    y, m, d = DATE_RE.match(iso).groups()
    pattern = rf"(?<!\d){y}\s*[-/.年]\s*0?{int(m)}\s*[-/.月]\s*0?{int(d)}(?!\d)"
    return re.search(pattern, answer) is not None


def number_in_answer(value: float, answer: str) -> bool:
    # 先把日期拿掉，避免「2021-03-06」裡的 6 被當成數值
    text = ANY_DATE_IN_TEXT.sub(" ", answer)
    return any(abs(float(n) - float(value)) < 1e-9 for n in NUMBER_RE.findall(text))


def check_direction(expected: str, answer: str) -> tuple[str, str | None]:
    """回傳 (判定, 需人工時的原因)。"""
    found = [d for d, words in DIRECTION_WORDS.items() if any(w in answer for w in words)]
    if found == [expected]:
        return "pass", None
    if not found:
        return "manual", "回答中找不到任何趨勢用詞（上升／下降／持平）"
    if expected not in found:
        return "fail", None
    # 正確與錯誤的用詞同時出現，例如「沒有上升或下降，整體持平」
    return "manual", f"回答中同時出現多個趨勢用詞：{'、'.join(found)}"


def check_over_65(expected: bool, answer: str) -> tuple[str, str | None]:
    """回傳 (判定, 需人工時的原因)。"""
    yes, no = OVER_65_YES.search(answer) is not None, OVER_65_NO.search(answer) is not None
    if yes and no:
        return "manual", "回答中同時出現「65 歲以上」的肯定與否定說法"
    if not yes and not no:
        return "manual", "回答中找不到是否 65 歲以上的明確說法"
    return ("pass" if yes == expected else "fail"), None


def score_exact_value(expected: dict, answer: str) -> tuple[str, list[str], list[str]]:
    """回傳 (判定, 細節, 需人工的原因)。細節列出每個檢查項目的結果。"""
    checks: list[tuple[str, str]] = []  # (描述, pass/fail/manual)
    reasons: list[str] = []

    def walk(key: str, value) -> None:
        if key.rsplit(".", 1)[-1].startswith("_"):
            return  # _ 開頭是給人工核對的參考資料（例如計算年齡的基準日），不要求出現在回答中
        if isinstance(value, dict):
            for k, v in value.items():
                walk(f"{key}.{k}" if key else k, v)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(f"{key}[{i}]", v)
        elif key.endswith("direction"):
            status, reason = check_direction(value, answer)
            checks.append((f"趨勢 {value}", status))
            if reason:
                reasons.append(f"趨勢（標準答案：{value}）：{reason}")
        elif isinstance(value, bool):  # 要放在數值判斷之前：Python 的 bool 也是 int
            status, reason = check_over_65(value, answer) if key.endswith("is_65_or_older") \
                else ("manual", f"{key} 是是非題，程式沒有對應的判斷規則")
            checks.append((f"{key} {'是' if value else '否'}", status))
            if reason:
                reasons.append(f"{key}（標準答案：{'是' if value else '否'}）：{reason}")
        elif key.endswith("gender"):
            ok = any(w in answer.lower() for w in GENDER_WORDS.get(value, [value]))
            checks.append((f"性別 {value}", "pass" if ok else "fail"))
        elif isinstance(value, str) and DATE_RE.match(value):
            checks.append((f"日期 {value}", "pass" if date_in_answer(value, answer) else "fail"))
        elif isinstance(value, (int, float)):
            checks.append((f"數值 {value}", "pass" if number_in_answer(value, answer) else "fail"))
        else:
            checks.append((f"{key}={value}", "pass" if str(value) in answer else "fail"))

    walk("", expected)
    statuses = {s for _, s in checks}
    verdict = "fail" if "fail" in statuses else "manual" if "manual" in statuses else "pass"
    details = [f"{'✅' if s == 'pass' else '❌' if s == 'fail' else '❓'} {desc}" for desc, s in checks]
    return verdict, details, reasons


# ---------- set_recall ----------

def code_in_answer(code: str, answer: str) -> bool:
    """數字代碼（SNOMED、RxNorm）前後不能接數字；ICD-10 碼的小數點可有可無（E11.9 = E119）。"""
    if re.fullmatch(r"\d+", code):
        return re.search(rf"(?<!\d){code}(?!\d)", answer) is not None
    pattern = re.escape(code).replace(r"\.", r"\.?")
    return re.search(rf"(?<![A-Za-z0-9]){pattern}(?![0-9])", answer, re.I) is not None


def item_in_answer(item: dict, answer: str, match_by: str = "any") -> bool:
    """代碼、完整英文名稱，或（藥品的）成分／品牌關鍵字，任一出現就算比對到。

    match_by="code" 時只認代碼（例如問 ICD-10 碼的題目，只答出診斷名稱不算）。
    """
    if code_in_answer(item["code"], answer):
        return True
    if match_by == "code":
        return False
    name = re.sub(r"\s*\[.*?\]|\s*\(.*?\)", "", item["name"]).strip()
    if re.search(rf"\b{re.escape(name)}\b", answer, re.I):
        return True
    if MED_HINT.search(item["name"]):
        words = re.findall(r"[A-Za-z]{5,}", item["name"])
        keywords = [w for w in words if w.lower() not in MED_STOPWORDS]
        return any(re.search(rf"\b{re.escape(w)}\b", answer, re.I) for w in keywords)
    return False


def score_set_recall(question: dict, answer: str) -> tuple[str, float, list[str], list[str]]:
    """回傳 (判定, 自動比對到的比例, 比對不到的項目, 需人工的原因)。比對不到不直接判錯。

    題目設定 extra_code_pattern="icd10" 時，回答中出現標準答案以外的 ICD-10 碼也列為需人工
    （可能是替未對照的診斷自行編碼）。
    """
    expected = question["expected"]
    match_by = question.get("match_by", "any")
    unmatched = [item for item in expected if not item_in_answer(item, answer, match_by)]
    recall = (len(expected) - len(unmatched)) / len(expected)
    reasons = []
    if unmatched:
        reasons.append("比對不到：" + "；".join(f"{i['name']}（{i['code']}）" for i in unmatched))
    if question.get("extra_code_pattern") == "icd10":
        allowed = {item["code"].replace(".", "").upper() for item in expected}
        extra = sorted({c for c in ICD10_IN_TEXT.findall(answer) if c.replace(".", "").upper() not in allowed})
        if extra:
            reasons.append(f"回答中出現標準答案以外的 ICD-10 碼：{'、'.join(extra)}")
    verdict = "manual" if reasons else "pass"
    return verdict, recall, [f"{i['name']}（{i['code']}）" for i in unmatched], reasons


# ---------- 人工評分 ----------

MAX_POINTS = 2  # 每次回答滿分
VALID_SCORES = {"0": 0, "1": 1, "2": 2}
HEADING_Q = re.compile(r"^## (Q\d+)（")
HEADING_RUN = re.compile(r"^### 第 (\d+) 次")
FIELD_LINE = re.compile(r"^- (分數|備註|是否列出了清單以外的項目（可能為編造）|未對照的診斷是否被給了 ICD-10 碼)：(.*)$")
SOURCE_LINE = re.compile(r"^結果檔：`(.+)`")


def parse_manual_review(path: Path) -> tuple[dict, str | None]:
    """讀取 manual_review.md 已填的欄位。

    回傳 ({(題號, 第幾次): {"score", "raw_score", "note", "fabrication"}}, 評分表對應的結果檔)。
    分數只接受 0、1、2，其他內容 score 為 None（raw_score 保留原文）。
    備註可以換行續寫（縮排的下一行會接在同一個備註後面）。
    """
    reviews: dict[tuple[str, int], dict] = {}
    source = None
    qid, run, last_field = None, None, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if m := SOURCE_LINE.match(line):
            source = m.group(1)
        elif m := HEADING_Q.match(line):
            qid, run, last_field = m.group(1), None, None
        elif m := HEADING_RUN.match(line):
            run, last_field = int(m.group(1)), None
            reviews[(qid, run)] = {"score": None, "raw_score": "", "note": "", "fabrication": "", "uncoded": ""}
        elif (m := FIELD_LINE.match(line)) and qid and run:
            field, value = m.group(1), m.group(2).strip()
            entry = reviews[(qid, run)]
            if field == "分數":
                entry["raw_score"] = value
                entry["score"] = VALID_SCORES.get(value)
                last_field = None
            else:
                key = {"備註": "note", "未對照的診斷是否被給了 ICD-10 碼": "uncoded"}.get(field, "fabrication")
                entry[key] = value
                last_field = key
        elif last_field and line.startswith((" ", "\t")) and line.strip():
            reviews[(qid, run)][last_field] += line.strip()
        else:
            last_field = None
    return reviews, source


def needs_human_score(r: dict, questions: dict) -> bool:
    """manual_rubric 題，以及自動判為 ❓ 的回答，都必須有人工分數。"""
    return questions[r["id"]]["scoring"] == "manual_rubric" or r["verdict"] == "manual"


def apply_human_scores(records: list[dict], questions: dict, reviews: dict) -> list[str]:
    """把人工分數合併進每次回答，回傳缺漏清單（空的代表全部填好）。

    r["points"]：人工分數（只有需要人工的回答才有，其餘為 None）
    r["final"]：pass／fail
        - 自動判定：通過 = pass；錯誤或 API 失敗 = fail
        - 人工判定：2 分 = pass；0 或 1 分 = fail
    """
    missing = []
    for r in records:
        review = reviews.get((r["id"], r["run"]))
        r["review"] = review
        r["points"] = None
        r["human"] = needs_human_score(r, questions)
        if r["human"]:
            if review is None:
                missing.append(f"{r['id']} 第 {r['run']} 次：manual_review.md 裡沒有這次回答")
                continue
            if review["score"] is None:
                raw = review["raw_score"]
                missing.append(f"{r['id']} 第 {r['run']} 次：分數"
                               + (f"「{raw}」不是 0、1、2" if raw else "空白"))
                continue
            r["points"] = review["score"]
            r["final"] = "pass" if r["points"] == MAX_POINTS else "fail"
        else:
            r["final"] = "pass" if r["verdict"] == "pass" else "fail"
    return missing


# ---------- 報告 ----------

# v1 題目（Q01–Q20）分開計分，才能和 v1 結果直接比較；Q21 之後是 v2 新增題
V1_QUESTION_IDS = {f"Q{i:02d}" for i in range(1, 21)}


def ratio(n, d) -> str:
    return f"{n:g} ÷ {d}（{n / d:.0%}）" if d else "—"


def run_marks(rows: list[dict]) -> str:
    return " ".join(str(r["points"]) if r["points"] is not None else
                    ("✅" if r["final"] == "pass" else "❌") for r in rows)


def group_by_question(records: list[dict]) -> dict[str, list[dict]]:
    runs_per_q = defaultdict(list)
    for r in records:
        runs_per_q[r["id"]].append(r)
    for rows in runs_per_q.values():
        rows.sort(key=lambda r: r["run"])
    return dict(sorted(runs_per_q.items()))


def outcome(r: dict, questions: dict):
    """一致性比較用：manual_rubric 題比分數，其他題比通過／錯誤。"""
    return r["points"] if questions[r["id"]]["scoring"] == "manual_rubric" else r["final"]


def subset_stats(records: list[dict], questions: dict) -> dict:
    """一組回答的重點數字（給 Q01–Q20 與 v1 比較、以及終端機輸出用）。"""
    runs_per_q = group_by_question(records)
    n_runs = max((len(v) for v in runs_per_q.values()), default=0)
    general = [r for r in records if r["category"] != EDGE_CATEGORY]
    edge = [r for r in records if r["category"] == EDGE_CATEGORY]
    tokens = sum(sum(r["usage"].values()) for r in records)
    return {
        "general_pass": sum(r["final"] == "pass" for r in general), "general_total": len(general),
        "edge_points": sum(r["points"] for r in edge), "edge_full": MAX_POINTS * len(edge),
        "consistent": sum(len(rows) == n_runs and len({outcome(r, questions) for r in rows}) == 1
                          for rows in runs_per_q.values()),
        "n_questions": len(runs_per_q), "n_runs": n_runs, "n_records": len(records),
        "avg_tool_calls": sum(len(r["tool_calls"]) for r in records) / len(records) if records else 0,
        "avg_tokens": tokens / len(records) if records else 0,
    }


def score_sections(records: list[dict], questions: dict, h: str = "###") -> list[str]:
    """一般查詢、人工題、邊界案例、一致性、低於滿分。h 是小節標題的層級。"""
    runs_per_q = group_by_question(records)
    st = subset_stats(records, questions)
    general = [r for r in records if r["category"] != EDGE_CATEGORY]
    lines = []

    # 一般查詢
    lines += [f"{h} 一般查詢", "",
              f"category 不是 {EDGE_CATEGORY} 的題目。自動與人工判定合併後：", "",
              f"**通過 {ratio(st['general_pass'], st['general_total'])}**", ""]
    if general:
        lines += ["| 類別 | 次數 | 自動判定 | 人工判定 | 通過 ÷ 總次數 |", "|---|---|---|---|---|"]
        for cat in dict.fromkeys(q["category"] for q in questions.values()):
            rows = [r for r in general if r["category"] == cat]
            if rows:
                n_human = sum(r["human"] for r in rows)
                lines.append(f"| {cat} | {len(rows)} | {len(rows) - n_human} | {n_human} "
                             f"| {ratio(sum(r['final'] == 'pass' for r in rows), len(rows))} |")
        human_qs = [qid for qid, rows in runs_per_q.items()
                    if questions[qid]["category"] != EDGE_CATEGORY and any(r["human"] for r in rows)]
        if human_qs:
            lines += ["", "一般查詢中的人工題：", "",
                      "| 題目 | 類別 | 計分方式 | 每次得分 | 得分 ÷ 滿分 |", "|---|---|---|---|---|"]
            for qid in human_qs:
                rows = [r for r in runs_per_q[qid] if r["human"]]
                q = questions[qid]
                lines.append(f"| {qid} | {q['category']} | {q['scoring']} | {run_marks(rows)} "
                             f"| {ratio(sum(r['points'] for r in rows), MAX_POINTS * len(rows))} |")

    # 邊界案例
    lines += ["", f"{h} 邊界案例", "",
              f"category 是 {EDGE_CATEGORY} 的題目，全部人工評分。", "",
              f"**得分 {ratio(st['edge_points'], st['edge_full'])}**", ""]
    edge_qs = [qid for qid in runs_per_q if questions[qid]["category"] == EDGE_CATEGORY]
    if edge_qs:
        lines += ["| 題目 | 病人 | 每次得分 | 得分 ÷ 滿分 |", "|---|---|---|---|"]
        for qid in edge_qs:
            rows = runs_per_q[qid]
            lines.append(f"| {qid} | {questions[qid]['patient_id']} | {run_marks(rows)} "
                         f"| {ratio(sum(r['points'] for r in rows), MAX_POINTS * len(rows))} |")

    # 一致性
    lines += ["", f"{h} 一致性", "",
              f"{st['n_runs']} 次結果完全相同：**{st['consistent']} / {st['n_questions']} 題**"
              "（manual_rubric 題比較分數，其他題比較通過／錯誤；3 次都錯也算相同）", "",
              "| 題目 | 類別 | 每次結果 | 一致 |", "|---|---|---|---|"]
    for qid, rows in runs_per_q.items():
        same = len(rows) == st["n_runs"] and len({outcome(r, questions) for r in rows}) == 1
        lines.append(f"| {qid} | {questions[qid]['category']} | {run_marks(rows)} | {'是' if same else '**否**'} |")

    # 低於滿分
    below = [r for r in records
             if (r["points"] is not None and r["points"] < MAX_POINTS)
             or (r["points"] is None and r["final"] == "fail")]
    lines += ["", f"{h} 低於滿分的回答", ""]
    if below:
        lines += ["| 題目 | 第幾次 | 類別 | 分數 | 備註 |", "|---|---|---|---|---|"]
        for r in below:
            if r["points"] is not None:
                score = f"{r['points']} ÷ {MAX_POINTS}"
                note = r["review"]["note"] or "（未填備註）"
            else:
                score = "自動判錯"
                note = r.get("error") or "、".join(d for d in r.get("details", []) if d.startswith("❌"))
            lines.append(f"| {r['id']} | {r['run']} | {r['category']} | {score} | {note.replace('|', '／')} |")
    else:
        lines.append("（無）")
    return lines


def comparison_lines(current: list[dict], baseline: list[dict], baseline_source: Path,
                     questions: dict) -> list[str]:
    """Q01–Q20：本次 vs v1。"""
    now, v1 = subset_stats(current, questions), subset_stats(baseline, questions)

    def row(label, a, b, fmt):
        return f"| {label} | {fmt(a)} | {fmt(b)} |"

    lines = [f"v1 結果：`{baseline_source.relative_to(ROOT)}`（以目前的 questions.json 與 v1 的人工分數重新計分；"
             "v2 的 Q14 標準答案已排除社會與心理狀況，v1 的 Q14 也以新標準計分）", "",
             "| 指標 | v1 | 本次 |", "|---|---|---|",
             row("一般查詢通過", v1, now, lambda s: ratio(s["general_pass"], s["general_total"])),
             row("邊界案例得分", v1, now, lambda s: ratio(s["edge_points"], s["edge_full"])),
             row("一致性（3 次結果相同）", v1, now, lambda s: f"{s['consistent']} / {s['n_questions']} 題"),
             row("平均工具呼叫", v1, now, lambda s: f"{s['avg_tool_calls']:.2f} 次"),
             row("平均 token／每次回答", v1, now, lambda s: f"{s['avg_tokens']:,.0f}"),
             "", "逐題對照（✅ 通過、❌ 錯誤；數字是人工分數）：", "",
             "| 題目 | 類別 | v1 每次 | 本次每次 | 變化 |", "|---|---|---|---|---|"]
    v1_by_q, now_by_q = group_by_question(baseline), group_by_question(current)
    for qid in sorted(set(v1_by_q) | set(now_by_q)):
        a, b = v1_by_q.get(qid, []), now_by_q.get(qid, [])
        score = lambda rows: sum(r["points"] if r["points"] is not None else
                                 (MAX_POINTS if r["final"] == "pass" else 0) for r in rows)
        change = "" if run_marks(a) == run_marks(b) else ("↑" if score(b) > score(a) else "↓" if score(b) < score(a) else "≠")
        lines.append(f"| {qid} | {questions[qid]['category']} | {run_marks(a) or '—'} | {run_marks(b) or '—'} | {change} |")
    return lines


def write_summary(path: Path, source: Path, manual_path: Path, records: list[dict], questions: dict,
                  baseline: tuple[Path, list[dict]] | None, baseline_note: str | None) -> dict:
    """產出 summary.md，回傳要印在終端機的重點數字。"""
    runs_per_q = group_by_question(records)
    old = [r for r in records if r["id"] in V1_QUESTION_IDS]
    new = [r for r in records if r["id"] not in V1_QUESTION_IDS]
    prompts = {r.get("system_prompt", "（v1 未記錄）") or "不使用" for r in records}

    lines = ["# 評估摘要", "",
             f"- 結果檔：`{source.relative_to(ROOT)}`",
             f"- 人工評分：`{manual_path.relative_to(ROOT)}`",
             f"- 模型：{', '.join(sorted({r['model'] for r in records}))}",
             f"- 系統提示詞：{'、'.join(sorted(prompts))}",
             f"- 題數：{len(runs_per_q)}，共 {len(records)} 次回答", "",
             "**判定規則**：自動判定通過 = 通過；自動錯誤或 API 失敗 = 錯誤。"
             f"需要人工的回答（manual_rubric 題，以及自動判為 ❓ 的回答）每次滿分 {MAX_POINTS} 分，"
             f"{MAX_POINTS} 分 = 通過，0 或 1 分 = 錯誤。", ""]

    lines += ["## Q01–Q20（v1 題目）", ""]
    if old:
        if baseline:
            lines += ["### 與 v1 比較", "", *comparison_lines(old, baseline[1], baseline[0], questions), ""]
        elif baseline_note:
            lines += [f"（未與 v1 比較：{baseline_note}）", ""]
        lines += score_sections(old, questions)
    else:
        lines.append("（這份結果沒有 Q01–Q20）")

    lines += ["", "## Q21–Q25（v2 新增）", ""]
    lines += score_sections(new, questions) if new else ["（這份結果沒有 v2 新增題）"]

    lines += ["", "## 工具與 token", ""]
    for label, rows in [("全部", records), ("Q01–Q20", old), ("Q21–Q25", new)]:
        if not rows:
            continue
        usage = defaultdict(int)
        for r in rows:
            for k, v in r["usage"].items():
                usage[k] += v
        lines += [f"**{label}**（{len(rows)} 次回答）", "",
                  f"- 平均工具呼叫次數：{sum(len(r['tool_calls']) for r in rows) / len(rows):.2f} 次／每次回答",
                  f"- 工具出錯次數：{sum(c['is_error'] for r in rows for c in r['tool_calls'])}",
                  f"- 超過 10 輪工具上限：{sum(r['hit_tool_limit'] for r in rows)} 次",
                  f"- 平均花費時間：{sum(r['elapsed_seconds'] for r in rows) / len(rows):.1f} 秒",
                  f"- token 用量：input {usage['input_tokens']:,}、output {usage['output_tokens']:,}、"
                  f"cache read {usage['cache_read_input_tokens']:,}、"
                  f"cache write {usage['cache_creation_input_tokens']:,}",
                  f"- token 合計：{sum(usage.values()):,}", ""]

    icon = {"pass": "✅", "fail": "❌", "manual": "❓", "error": "💥"}
    lines += ["## 逐次細節", ""]
    for rows in runs_per_q.values():
        for r in rows:
            q = questions[r["id"]]
            human = f"，人工 {r['points']} ÷ {MAX_POINTS}" if r["points"] is not None else ""
            lines.append(f"### {r['id']} run{r['run']} — 自動 {icon[r['verdict']]}{human}，"
                         f"最終 {'✅ 通過' if r['final'] == 'pass' else '❌ 錯誤'}")
            lines.append(f"- 工具：{', '.join(c['name'] + json.dumps(c['input'], ensure_ascii=False) for c in r['tool_calls']) or '（未呼叫）'}")
            if r.get("error"):
                lines.append(f"- API 錯誤：{r['error']}")
            if q["scoring"] == "exact_value":
                lines += [f"- {d}" for d in r["details"]]
                lines += [f"- 程式不確定的原因：{reason}" for reason in r["manual_reasons"]]
            elif q["scoring"] == "set_recall":
                lines.append(f"- 自動比對到 {r['recall']:.0%}")
                lines += [f"- 程式不確定的原因：{reason}" for reason in r["manual_reasons"]]
                if r["review"]:
                    lines.append(f"- 是否多答：{r['review']['fabrication'] or '（未填）'}")
                    if q.get("must_not_give_code"):
                        lines.append(f"- 未對照的診斷是否被給了 ICD-10 碼：{r['review']['uncoded'] or '（未填）'}")
            if r["review"] and r["review"]["note"]:
                lines.append(f"- 人工備註：{r['review']['note']}")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return {"old": subset_stats(old, questions), "new": subset_stats(new, questions),
            "baseline": subset_stats(baseline[1], questions) if baseline else None}


def write_manual_review(path: Path, source: Path, records: list[dict], questions: dict) -> None:
    lines = ["# 人工評分表", "",
             f"結果檔：`{source.relative_to(ROOT)}`", "",
             "每次回答請在「分數」填 0／1（或 0–2），「備註」寫原因。",
             "set_recall 題目另外檢查「是否列出了清單以外的項目（可能為編造）」；"
             "ICD-10 題另外檢查「未對照的診斷是否被給了 ICD-10 碼」。",
             "exact_value 題目只列出程式判為 ❓ 的回答，並附上不確定的原因。", ""]
    by_q = defaultdict(list)
    for r in records:
        if questions[r["id"]]["scoring"] in MANUAL_REVIEW_SCORING or r["verdict"] == "manual":
            by_q[r["id"]].append(r)
    for qid, rows in by_q.items():
        q = questions[qid]
        lines += [f"## {qid}（{q['category']}，{q['scoring']}，病人 {q['patient_id']}）", "",
                  f"**題目**：{q['question']}", ""]
        exp = q["expected"]
        if q["scoring"] == "set_recall":
            lines += ["**預期清單**（清單以外的項目都要檢查是否為編造）：", "",
                      *[f"- {item['name']}（{item['code']}）" for item in exp], ""]
            fields = ["是否列出了清單以外的項目（可能為編造）"]
            if q.get("must_not_give_code"):
                lines += ["**不得給出 ICD-10 碼的診斷**（對照表未查證）：", "",
                          *[f"- {name}" for name in q["must_not_give_code"]], ""]
                fields.append("未對照的診斷是否被給了 ICD-10 碼")
            for r in sorted(rows, key=lambda r: r["run"]):
                notes = [] if r["verdict"] == "error" else \
                    [f"自動比對到 {r['recall']:.0%}"] + [f"程式不確定的原因：{x}" for x in r["manual_reasons"]]
                lines += review_block(r, notes=notes, fields=fields)
            continue
        if q["scoring"] == "exact_value":
            lines += ["**標準答案**：", "", f"`{json.dumps(exp, ensure_ascii=False)}`", ""]
            for r in sorted(rows, key=lambda r: r["run"]):
                lines += review_block(r, notes=[f"程式不確定的原因：{reason}" for reason in r["manual_reasons"]]
                                      + [f"自動檢查：{'、'.join(r['details'])}"])
            continue
        lines += ["**預期行為**：", ""]
        if "behavior" in exp:
            lines.append(f"- {exp['behavior']}")
        for k in ("must_include", "must_not_include"):
            if k in exp:
                label = "必須包含" if k == "must_include" else "不可包含"
                lines.append(f"- {label}：{'、'.join(exp[k])}")
        extra = {k: v for k, v in exp.items() if k not in ("behavior", "must_include", "must_not_include")}
        if extra:
            lines.append(f"- 參考資料：`{json.dumps(extra, ensure_ascii=False)}`")
        lines.append("")
        for r in sorted(rows, key=lambda r: r["run"]):
            lines += review_block(r)
    path.write_text("\n".join(lines), encoding="utf-8")


def review_block(r: dict, notes: list[str] = (), fields: list[str] = ()) -> list[str]:
    """一次回答的人工檢查區塊：工具呼叫、回答全文、自動計分註記，以及空白的人工欄位。"""
    tools = ", ".join(c["name"] + json.dumps(c["input"], ensure_ascii=False) for c in r["tool_calls"])
    answer = r["final_answer"].strip() or f"（無回答：{r.get('error') or r['stop_reason']}）"
    return [f"### 第 {r['run']} 次", "",
            f"工具呼叫：{tools or '（未呼叫）'}", "",
            *[f"> {line}" if line else ">" for line in answer.splitlines()], "",
            *[f"- {n}" for n in notes],
            *[f"- {f}：" for f in [*fields, "分數", "備註"]], ""]


def latest_result(results_dir: Path) -> Path | None:
    """資料夾裡最新的結果檔（只看這一層，不會抓到子資料夾裡的 v2 結果）。"""
    files = sorted(results_dir.glob("*.jsonl"))
    return files[-1] if files else None


def auto_score(source: Path, questions: dict) -> list[dict]:
    records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line]
    unknown = sorted({r["id"] for r in records if r["id"] not in questions})
    if unknown:
        sys.exit(f"{source.relative_to(ROOT)} 有 questions.json 裡沒有的題目：{'、'.join(unknown)}")
    for r in records:
        q = questions[r["id"]]
        answer = r["final_answer"]
        if r.get("error") or not answer:
            r["verdict"], r["details"], r["recall"], r["unmatched"] = "error", [], 0.0, []
            r["manual_reasons"] = []
        elif q["scoring"] == "exact_value":
            r["verdict"], r["details"], r["manual_reasons"] = score_exact_value(q["expected"], answer)
        elif q["scoring"] == "set_recall":
            r["verdict"], r["recall"], r["unmatched"], r["manual_reasons"] = score_set_recall(q, answer)
        else:
            r["verdict"] = "manual"
    return records


def load_human_scores(records: list[dict], source: Path, manual_path: Path, questions: dict) -> list[str]:
    """讀取並套用人工分數，回傳問題清單（空的代表可以產生 summary）。"""
    if not manual_path.exists():
        return [f"找不到 {manual_path.relative_to(ROOT)}"]
    reviews, review_source = parse_manual_review(manual_path)
    # 評分表對應的結果檔必須和這次計分的是同一個，否則分數對不上
    if review_source and (ROOT / review_source).resolve() != source:
        return [f"{manual_path.relative_to(ROOT)} 是 {review_source} 的評分，不是 {source.relative_to(ROOT)}"]
    return apply_human_scores(records, questions, reviews)


def main() -> None:
    parser = argparse.ArgumentParser(description="評估結果計分")
    parser.add_argument("result_file", nargs="?", type=Path,
                        help="結果 JSONL；不給就用 --results-dir 裡最新的一個")
    parser.add_argument("--results-dir", type=Path, default=None,
                        help="結果資料夾（manual_review.md、summary.md 也放這裡）。"
                             "預設為 result_file 所在資料夾，或 eval/results/（v1）")
    parser.add_argument("--baseline-dir", type=Path, default=RESULTS_DIR,
                        help="Q01–Q20 要比較的 v1 結果資料夾，預設 eval/results/")
    parser.add_argument("--no-baseline", action="store_true", help="不和 v1 比較")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--overwrite-manual", action="store_true",
                       help="manual_review.md 已存在時仍覆蓋（會清掉已填的分數）")
    group.add_argument("--keep-manual", action="store_true",
                       help="只讀取 manual_review.md 的人工分數，不修改它（預設行為，明確標示用）")
    args = parser.parse_args()

    if args.result_file:
        source = args.result_file.resolve()
        results_dir = (args.results_dir or source.parent).resolve()
    else:
        results_dir = (args.results_dir or RESULTS_DIR).resolve()
        source = latest_result(results_dir)
        if source is None:
            sys.exit(f"{results_dir.relative_to(ROOT)}/ 裡沒有結果檔")
    print(f"結果檔：{source.relative_to(ROOT)}")

    questions = {q["id"]: q for q in json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))}
    records = auto_score(source, questions)

    manual_path = results_dir / "manual_review.md"
    summary_path = results_dir / "summary.md"
    if args.overwrite_manual:
        write_manual_review(manual_path, source, records, questions)
        sys.exit(f"已重新產生 {manual_path.relative_to(ROOT)}（已清空分數），請填完後再執行一次（未產生 summary.md）")
    if not manual_path.exists():
        write_manual_review(manual_path, source, records, questions)
        sys.exit(f"已產出 {manual_path.relative_to(ROOT)}，請填完人工分數後再執行一次（未產生 summary.md）")

    problems = load_human_scores(records, source, manual_path, questions)
    if problems:
        print("以下回答需要人工分數，但沒有填寫或格式不對：")
        for p in problems:
            print(f"  - {p}")
        sys.exit(f"請補完 {manual_path.relative_to(ROOT)} 後再執行一次（未產生 summary.md）")

    # v1 基準：只取 Q01–Q20，用 v1 自己的 manual_review.md；有任何問題就不比較，但不影響本次計分
    baseline, baseline_note = None, None
    baseline_dir = args.baseline_dir.resolve()
    if args.no_baseline:
        baseline_note = "指定了 --no-baseline"
    elif baseline_dir == results_dir:
        baseline_note = "本次結果就在 v1 資料夾"
    elif (baseline_source := latest_result(baseline_dir)) is None:
        baseline_note = f"{baseline_dir.relative_to(ROOT)}/ 裡沒有結果檔"
    else:
        base_records = [r for r in auto_score(baseline_source, questions) if r["id"] in V1_QUESTION_IDS]
        base_problems = load_human_scores(base_records, baseline_source,
                                          baseline_dir / "manual_review.md", questions)
        if base_problems:
            baseline_note = f"v1 人工分數無法使用（{base_problems[0]}）"
        else:
            baseline = (baseline_source, base_records)
    if baseline_note:
        print(f"⚠️ 未與 v1 比較：{baseline_note}")

    totals = write_summary(summary_path, source, manual_path, records, questions, baseline, baseline_note)
    print(f"已產出 {summary_path.relative_to(ROOT)}")
    for label, st in [("Q01–Q20", totals["old"]), ("v1 Q01–Q20", totals["baseline"]), ("Q21–Q25", totals["new"])]:
        if st and st["n_records"]:
            print(f"{label}：一般查詢 {ratio(st['general_pass'], st['general_total'])}，"
                  f"邊界案例 {ratio(st['edge_points'], st['edge_full'])}")

    if args.keep_manual:
        print(f"--keep-manual：未修改 {manual_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
