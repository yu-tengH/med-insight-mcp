"""讀取一個 run_eval.py 的結果檔，自動計分並產出報告。

用法：
    uv run python eval/score.py eval/results/<時間>_<模型>.jsonl
    uv run python eval/score.py            # 不給檔名就用最新的結果檔

產出：
    eval/results/summary.md        各類別正確率、一般查詢 vs 邊界案例、一致性、工具與 token 統計
    eval/results/manual_review.md  manual_rubric、set_recall 題目，以及所有判為需人工的回答
                                   填好分數後再跑一次（加 --keep-manual），summary.md 會改用人工分數（已存在時不覆蓋，除非加 --overwrite-manual）

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


def score_exact_value(expected: dict, answer: str) -> tuple[str, list[str], list[str]]:
    """回傳 (判定, 細節, 需人工的原因)。細節列出每個檢查項目的結果。"""
    checks: list[tuple[str, str]] = []  # (描述, pass/fail/manual)
    reasons: list[str] = []

    def walk(key: str, value) -> None:
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

def item_in_answer(item: dict, answer: str) -> bool:
    """代碼、完整英文名稱，或（藥品的）成分／品牌關鍵字，任一出現就算比對到。"""
    if re.search(rf"(?<!\d){re.escape(item['code'])}(?!\d)", answer):
        return True
    name = re.sub(r"\s*\[.*?\]|\s*\(.*?\)", "", item["name"]).strip()
    if re.search(rf"\b{re.escape(name)}\b", answer, re.I):
        return True
    if MED_HINT.search(item["name"]):
        words = re.findall(r"[A-Za-z]{5,}", item["name"])
        keywords = [w for w in words if w.lower() not in MED_STOPWORDS]
        return any(re.search(rf"\b{re.escape(w)}\b", answer, re.I) for w in keywords)
    return False


def score_set_recall(expected: list[dict], answer: str) -> tuple[str, float, list[str]]:
    """回傳 (判定, 自動比對到的比例, 比對不到需人工確認的項目)。比對不到不直接判錯。"""
    unmatched = [item["name"] for item in expected if not item_in_answer(item, answer)]
    recall = (len(expected) - len(unmatched)) / len(expected)
    return ("pass" if not unmatched else "manual"), recall, unmatched


# ---------- 人工評分 ----------

MAX_POINTS = 2  # 每次回答滿分
FABRICATION_FIELD = "是否列出了清單以外的項目（可能為編造）"
HEADING_Q = re.compile(r"^## (Q\d+)（")
HEADING_RUN = re.compile(r"^### 第 (\d+) 次")
FIELD_LINE = re.compile(r"^- (分數|備註|是否列出了清單以外的項目（可能為編造）)：(.*)$")
SOURCE_LINE = re.compile(r"^結果檔：`(.+)`")


def parse_manual_review(path: Path) -> tuple[dict, str | None, list[str]]:
    """讀取 manual_review.md 已填的欄位。

    回傳 ({(題號, 第幾次): {"score", "note", "fabrication"}}, 評分表對應的結果檔, 警告)。
    備註可以換行續寫（縮排的下一行會接在同一個備註後面）。
    """
    reviews: dict[tuple[str, int], dict] = {}
    warnings: list[str] = []
    source = None
    qid, run, last_field = None, None, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if m := SOURCE_LINE.match(line):
            source = m.group(1)
        elif m := HEADING_Q.match(line):
            qid, run, last_field = m.group(1), None, None
        elif m := HEADING_RUN.match(line):
            run, last_field = int(m.group(1)), None
            reviews[(qid, run)] = {"score": None, "note": "", "fabrication": ""}
        elif (m := FIELD_LINE.match(line)) and qid and run:
            field, value = m.group(1), m.group(2).strip()
            entry = reviews[(qid, run)]
            if field == "分數":
                if value:
                    try:
                        score = float(value)
                    except ValueError:
                        score = None
                    if score is None or not 0 <= score <= MAX_POINTS:
                        warnings.append(f"{qid} 第 {run} 次的分數「{value}」不是 0–{MAX_POINTS}，視為未評分")
                    else:
                        entry["score"] = int(score) if score.is_integer() else score
                last_field = None
            else:
                key = "note" if field == "備註" else "fabrication"
                entry[key] = value
                last_field = key
        elif last_field and line.startswith((" ", "\t")) and line.strip():
            reviews[(qid, run)][last_field] += line.strip()
        else:
            last_field = None
    return reviews, source, warnings


def apply_points(records: list[dict], questions: dict, reviews: dict) -> None:
    """決定每次回答的最終得分（滿分 2）。

    有人工分數就以人工為準；否則自動通過 = 2、自動錯誤或 API 失敗 = 0；
    需人工但還沒填分數 = 未評分（不列入得分與滿分）。
    """
    for r in records:
        review = reviews.get((r["id"], r["run"]))
        r["review"] = review
        if review and review["score"] is not None:
            r["points"], r["points_source"] = review["score"], "人工"
        elif r["verdict"] == "pass":
            r["points"], r["points_source"] = MAX_POINTS, "自動"
        elif r["verdict"] in ("fail", "error"):
            r["points"], r["points_source"] = 0, "自動"
        else:
            r["points"], r["points_source"] = None, "未評分"


# ---------- 報告 ----------

def fmt_points(p) -> str:
    return "—" if p is None else f"{p:g}"


def stats_row(label: str, rows: list[dict]) -> str:
    scored = [r for r in rows if r["points"] is not None]
    got = sum(r["points"] for r in scored)
    full = MAX_POINTS * len(scored)
    n_auto = sum(r["points_source"] == "自動" for r in rows)
    n_human = sum(r["points_source"] == "人工" for r in rows)
    rate = f"{got / full:.0%}" if full else "—"
    return (f"| {label} | {len(rows)} | {n_auto} | {n_human} | {len(rows) - len(scored)} "
            f"| {got:g} ÷ {full} | {rate} |")


STATS_HEADER = ("| 分組 | 次數 | 自動計分 | 人工評分 | 未評分 | 得分 ÷ 滿分 | 得分率 |\n"
                "|---|---|---|---|---|---|---|")
POINT_ICON = {2: "✅", 1: "🟡", 0: "❌", None: "⬜"}


def write_summary(path: Path, source: Path, records: list[dict], questions: dict,
                  review_info: list[str]) -> None:
    runs_per_q = defaultdict(list)
    for r in records:
        runs_per_q[r["id"]].append(r)
    for rows in runs_per_q.values():
        rows.sort(key=lambda r: r["run"])
    n_runs = max(len(v) for v in runs_per_q.values())

    lines = ["# 評估摘要", "",
             f"- 結果檔：`{source.relative_to(ROOT)}`",
             f"- 模型：{', '.join(sorted({r['model'] for r in records}))}",
             f"- 題數：{len(runs_per_q)}，每題 {n_runs} 次，共 {len(records)} 次回答",
             *[f"- {info}" for info in review_info], "",
             "**計分方式**：每次回答滿分 2 分。有人工分數以人工為準；"
             "其餘自動通過 = 2、自動錯誤或 API 失敗 = 0；需人工但未填分數的列為「未評分」，不列入得分與滿分。", ""]

    lines += ["## 各類別", "", STATS_HEADER]
    for cat in dict.fromkeys(q["category"] for q in questions.values()):
        rows = [r for r in records if r["category"] == cat]
        if rows:
            lines.append(stats_row(cat, rows))
    lines.append(stats_row("**全部**", records))

    lines += ["", "## 一般查詢 vs 邊界案例", "",
              f"category 為 {EDGE_CATEGORY} 的題目歸為邊界案例，其餘歸為一般查詢。", "",
              STATS_HEADER,
              stats_row("一般查詢", [r for r in records if r["category"] != EDGE_CATEGORY]),
              stats_row("邊界案例", [r for r in records if r["category"] == EDGE_CATEGORY])]

    full_marks = [qid for qid, rows in runs_per_q.items()
                  if len(rows) == n_runs and all(r["points"] == MAX_POINTS for r in rows)]
    lines += ["", "## 一致性", "",
              f"{n_runs} 次都拿滿分：**{len(full_marks)} / {len(runs_per_q)} 題**", "",
              "✅ 2 分　🟡 1 分　❌ 0 分　⬜ 未評分", "",
              "| 題目 | 類別 | 計分方式 | 每次得分 | 得分 ÷ 滿分 |", "|---|---|---|---|---|"]
    for qid, rows in runs_per_q.items():
        q = questions[qid]
        marks = " ".join(f"{POINT_ICON.get(r['points'], '🟡')}{fmt_points(r['points'])}" for r in rows)
        scored = [r for r in rows if r["points"] is not None]
        lines.append(f"| {qid} | {q['category']} | {q['scoring']} | {marks} "
                     f"| {sum(r['points'] for r in scored):g} ÷ {MAX_POINTS * len(scored)} |")

    below = [r for r in records if r["points"] is not None and r["points"] < MAX_POINTS]
    lines += ["", "## 低於滿分的回答", ""]
    if below:
        lines += ["| 題目 | 第幾次 | 類別 | 得分 | 來源 | 備註 |", "|---|---|---|---|---|---|"]
        for r in below:
            if r["points_source"] == "人工":
                note = r["review"]["note"] or "（未填備註）"
            else:
                note = r.get("error") or "、".join(d for d in r.get("details", []) if d.startswith("❌"))
            lines.append(f"| {r['id']} | {r['run']} | {r['category']} | {fmt_points(r['points'])} ÷ {MAX_POINTS} "
                         f"| {r['points_source']} | {note.replace('|', '／')} |")
    else:
        lines.append("（無）")

    unscored = [r for r in records if r["points"] is None]
    if unscored:
        lines += ["", "## 未評分的回答", "",
                  "這些回答需要人工評分，但 manual_review.md 的「分數」是空的：", ""]
        for r in unscored:
            note = r["review"]["note"] if r["review"] else ""
            lines.append(f"- {r['id']} 第 {r['run']} 次" + (f"（備註：{note}）" if note else ""))

    recall_rows = [r for r in records if questions[r["id"]]["scoring"] == "set_recall"]
    if recall_rows:
        answers = defaultdict(list)
        for r in recall_rows:
            value = (r["review"] or {}).get("fabrication", "").strip()
            answers[value or "（未填）"].append(f"{r['id']}-{r['run']}")
        lines += ["", "## set_recall 是否多答（可能為編造）", "",
                  "| 填寫內容 | 次數 | 回答 |", "|---|---|---|"]
        for value, ids in answers.items():
            lines.append(f"| {value} | {len(ids)} | {'、'.join(ids)} |")

    total_calls = sum(len(r["tool_calls"]) for r in records)
    usage = defaultdict(int)
    for r in records:
        for k, v in r["usage"].items():
            usage[k] += v
    lines += ["", "## 工具與 token", "",
              f"- 平均工具呼叫次數：{total_calls / len(records):.2f} 次／每次回答",
              f"- 工具出錯次數：{sum(c['is_error'] for r in records for c in r['tool_calls'])}",
              f"- 超過 10 輪工具上限：{sum(r['hit_tool_limit'] for r in records)} 次",
              f"- 平均花費時間：{sum(r['elapsed_seconds'] for r in records) / len(records):.1f} 秒",
              f"- token 用量：input {usage['input_tokens']:,}、output {usage['output_tokens']:,}、"
              f"cache read {usage['cache_read_input_tokens']:,}、"
              f"cache write {usage['cache_creation_input_tokens']:,}",
              f"- token 合計：{sum(usage.values()):,}"]

    icon = {"pass": "✅", "fail": "❌", "manual": "❓", "error": "💥"}
    lines += ["", "## 逐次細節", ""]
    for r in records:
        q = questions[r["id"]]
        lines.append(f"### {r['id']} run{r['run']} — 自動判定 {icon[r['verdict']]} {r['verdict']}，"
                     f"最終得分 {fmt_points(r['points'])} ÷ {MAX_POINTS}（{r['points_source']}）")
        lines.append(f"- 工具：{', '.join(c['name'] + json.dumps(c['input'], ensure_ascii=False) for c in r['tool_calls']) or '（未呼叫）'}")
        if r.get("error"):
            lines.append(f"- API 錯誤：{r['error']}")
        if q["scoring"] == "exact_value":
            lines += [f"- {d}" for d in r["details"]]
            lines += [f"- 程式不確定的原因：{reason}" for reason in r["manual_reasons"]]
        elif q["scoring"] == "set_recall":
            lines.append(f"- 自動比對到 {r['recall']:.0%}")
            if r["unmatched"]:
                lines.append(f"- 自動比對不到：{'；'.join(r['unmatched'])}")
        if r["review"]:
            if q["scoring"] == "set_recall":
                lines.append(f"- 是否多答：{r['review']['fabrication'] or '（未填）'}")
            lines.append(f"- 人工備註：{r['review']['note'] or '（未填）'}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def write_manual_review(path: Path, source: Path, records: list[dict], questions: dict) -> None:
    lines = ["# 人工評分表", "",
             f"結果檔：`{source.relative_to(ROOT)}`", "",
             "每次回答請在「分數」填 0／1（或 0–2），「備註」寫原因。",
             "set_recall 題目另外檢查「是否列出了清單以外的項目（可能為編造）」。",
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
            for r in sorted(rows, key=lambda r: r["run"]):
                auto = f"自動比對到 {r['recall']:.0%}"
                if r["unmatched"]:
                    auto += f"，比對不到：{'；'.join(r['unmatched'])}"
                lines += review_block(r, notes=[auto] if r["verdict"] != "error" else [],
                                      fields=["是否列出了清單以外的項目（可能為編造）"])
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


def main() -> None:
    parser = argparse.ArgumentParser(description="評估結果計分")
    parser.add_argument("result_file", nargs="?", help="結果 JSONL，預設為最新的一個")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--overwrite-manual", action="store_true",
                       help="manual_review.md 已存在時仍覆蓋（會清掉已填的分數）")
    group.add_argument("--keep-manual", action="store_true",
                       help="完全不寫 manual_review.md，只讀取裡面的人工分數更新 summary.md")
    args = parser.parse_args()

    if args.result_file:
        source = Path(args.result_file).resolve()
    else:
        files = sorted(RESULTS_DIR.glob("*.jsonl"))
        if not files:
            sys.exit("eval/results/ 裡沒有結果檔")
        source = files[-1]

    questions = {q["id"]: q for q in json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))}
    records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line]

    for r in records:
        q = questions[r["id"]]
        answer = r["final_answer"]
        if r.get("error") or not answer:
            r["verdict"], r["details"], r["recall"], r["unmatched"] = "error", [], 0.0, []
            r["manual_reasons"] = []
        elif q["scoring"] == "exact_value":
            r["verdict"], r["details"], r["manual_reasons"] = score_exact_value(q["expected"], answer)
        elif q["scoring"] == "set_recall":
            r["verdict"], r["recall"], r["unmatched"] = score_set_recall(q["expected"], answer)
        else:
            r["verdict"] = "manual"

    # 讀取人工分數；評分表對應的結果檔必須和這次計分的是同一個，否則分數不套用
    manual_path = RESULTS_DIR / "manual_review.md"
    reviews, review_info = {}, ["人工評分：無（找不到 manual_review.md）"]
    if manual_path.exists():
        parsed, review_source, warnings = parse_manual_review(manual_path)
        for w in warnings:
            print(f"⚠️ {w}")
        if review_source and Path(ROOT / review_source).resolve() != source:
            print(f"⚠️ manual_review.md 是 {review_source} 的評分，不是這次的結果檔，人工分數不套用")
            review_info = [f"人工評分：未套用（manual_review.md 對應 `{review_source}`）"]
        else:
            reviews = parsed
            n_filled = sum(v["score"] is not None for v in parsed.values())
            review_info = [f"人工評分：`{manual_path.relative_to(ROOT)}`，"
                           f"{len(parsed)} 次回答中已填分數 {n_filled} 次"]
    apply_points(records, questions, reviews)

    summary_path = RESULTS_DIR / "summary.md"
    write_summary(summary_path, source, records, questions, review_info)
    print(f"已產出 {summary_path.relative_to(ROOT)}")

    if args.keep_manual:
        print(f"--keep-manual：未修改 {manual_path.relative_to(ROOT)}")
    elif any(questions[r["id"]]["scoring"] in MANUAL_REVIEW_SCORING or r["verdict"] == "manual"
           for r in records):
        if manual_path.exists() and not args.overwrite_manual:
            print(f"{manual_path.relative_to(ROOT)} 已存在，未覆蓋（避免清掉已填的分數；要覆蓋請加 --overwrite-manual）")
        else:
            write_manual_review(manual_path, source, records, questions)
            print(f"已產出 {manual_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
