'''uv run python -c "from server.fhir_server import get_lab_results; get_lab_results('5829')"
cat logs/tool_calls.jsonl'''
from mcp.server.mcpserver import MCPServer
import httpx
import inspect
import json
import time
import csv
from datetime import datetime
from functools import wraps
from pathlib import Path
from datetime import date


FHIR_BASE = "http://localhost:8080/fhir"
mcp = MCPServer("med-insight") # 建立一個 MCP Server，名字叫 med-insight
# @mcp.tool()  叫「裝飾器」，作用是告訴 MCP：「下面這個函式是一個工具，開放給 AI 使用」。少了這行，Claude 就看不到這個工具

# 診斷分組與 ICD-10 對照表（只有 status 為「已查證」的 ICD-10 碼會提供給 AI）
with open(Path(__file__).parent / "condition_map.csv", encoding="utf-8") as f:
    CONDITION_MAP = {row["snomed_code"]: row for row in csv.DictReader(f)}

GROUP_LABEL = {"A": "糖尿病相關與慢性病", "B": "其他疾病", "C": "社會與心理狀況（非疾病診斷）"}


# 紀錄檔放在專案的 logs 資料夾
LOG_FILE = Path(__file__).parent.parent / "logs" / "tool_calls.jsonl"


def log_tool_call(func):
    """包在工具外面，每次被呼叫都自動寫一筆紀錄。"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        record = {
            "time": datetime.now().astimezone().isoformat(),
            "tool": func.__name__,
            "params": dict(inspect.signature(func).bind(*args, **kwargs).arguments),
        }
        try:
            result = func(*args, **kwargs)
            record["status"] = "ok"
            record["result_count"] = len(result) if isinstance(result, list) else 1
            return result
        except Exception as e:
            record["status"] = "error"
            record["error"] = str(e)
            raise
        finally:
            record["duration_ms"] = round((time.time() - start) * 1000)
            LOG_FILE.parent.mkdir(exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return wrapper



# FHIR 的 Patient 有一個欄位叫 active：
# 沒寫或 true：一般病人
# false：這筆病歷已不再使用，剛好對應副院長說的「封存」
#「確認病人」
def check_patient(patient_id: str) -> dict:
    """確認病人存在且未封存，回傳病人資料；否則丟出清楚的錯誤訊息。"""
    resp = httpx.get(f"{FHIR_BASE}/Patient/{patient_id}", timeout=30)
    if resp.status_code in (404, 410):
        raise ValueError(
            f"查無病人 {patient_id} 的資料。可能是 ID 輸入錯誤，"
            "或病歷已封存，請至院內系統確認。"
        )
    resp.raise_for_status()
    patient = resp.json()
    if patient.get("active") is False:
        raise ValueError(
            f"病人 {patient_id} 的病歷已封存，無法查詢。如需調閱，請依院內流程申請解除封存。"
        )
    return patient

# 下方主要是因為v1.0.0的MCP Server還沒有提供「自動分頁抓全部」的功能，都只有道200筆，所以自己寫一個函式來做這件事
def fetch_all(resource: str, params: dict, max_items: int = 2000) -> list[dict]:
    """跟著 FHIR 的「下一頁」連結把結果全部抓回來；超過上限時明確回報，不默默截斷。"""
    url, query = f"{FHIR_BASE}/{resource}", params
    entries = []
    while url:
        resp = httpx.get(url, params=query, timeout=60)
        resp.raise_for_status()
        bundle = resp.json()
        entries.extend(bundle.get("entry", []))
        if len(entries) > max_items:
            raise ValueError(
                f"查詢結果超過 {max_items} 筆，請縮小範圍（例如只查目前有效的項目）。"
            )
        url = next((l["url"] for l in bundle.get("link", []) if l.get("relation") == "next"), None)
        query = None  # 下一頁的連結已經包含所有查詢條件
    return entries

def calc_age(birth_date: str | None, deceased: str | None) -> int | None:
    """依生日計算年齡；已過世的病人算到過世當天。"""
    if not birth_date:
        return None
    born = date.fromisoformat(birth_date[:10])
    end = date.fromisoformat(deceased[:10]) if deceased else date.today()
    return end.year - born.year - ((end.month, end.day) < (born.month, born.day))


@mcp.tool()
@log_tool_call

def get_lab_results(patient_id: str, loinc_code: str = "4548-4", limit: int = 3) -> list[dict]:
    # loinc_code: str = "4548-4"：選填，沒給就預設查糖化血色素
    # limit: int = 3：選填，沒給就預設只回傳 3 筆
    # patient_id: str: FHIR 病人 ID，例如 "5829"，必填
    """查詢病人的檢驗結果，依日期由新到舊排列。

    Args:
        patient_id: FHIR 病人 ID，例如 "5829"
        loinc_code: 檢驗項目的 LOINC 代碼，預設 4548-4（糖化血色素 HbA1c）
        limit: 最多回傳幾筆，預設 3 筆
    """
    check_patient(patient_id)
    params = {
        "subject": f"Patient/{patient_id}",
        "code": f"http://loinc.org|{loinc_code}",
        "_sort": "-date",
        "_count": limit,
    }
    resp = httpx.get(f"{FHIR_BASE}/Observation", params=params, timeout=30)
    resp.raise_for_status()
    bundle = resp.json()

    results = []
    for entry in bundle.get("entry", []):
        obs = entry["resource"]
        quantity = obs.get("valueQuantity", {})
        results.append({
            "date": obs.get("effectiveDateTime"),
            "test": obs["code"]["coding"][0].get("display"),
            "value": quantity.get("value"),
            "unit": quantity.get("unit"),
        })
    return results


@mcp.tool()
@log_tool_call
def get_patient(patient_id: str) -> dict:
    """查詢病人的基本資料：姓名、性別、生日。

    Args:
        patient_id: FHIR 病人 ID，例如 "5829"
    """
    patient = check_patient(patient_id)

    # 一位病人可能有多個名字（例如婚前姓），優先取 use 為 official 的那一個
    names = patient.get("name", [])
    name = next((n for n in names if n.get("use") == "official"), names[0] if names else {})
    full_name = " ".join(name.get("given", []) + [name.get("family", "")]).strip()

    deceased = patient.get("deceasedDateTime")
    age = calc_age(patient.get("birthDate"), deceased)
    return {
        "id": patient.get("id"),
        "name": full_name or None,
        "gender": patient.get("gender"),
        "birth_date": patient.get("birthDate"),
        "age": age,
        "is_65_or_older": age is not None and age >= 65,
        "deceased_date": deceased,
    }



@mcp.tool()
@log_tool_call
def get_conditions(patient_id: str, active_only: bool = True, include_social: bool = False) -> dict:
    """查詢病人的診斷紀錄，依發病日期由新到舊排列，並附 ICD-10 對照與分組。

    分組：糖尿病相關與慢性病、其他疾病、社會與心理狀況（非疾病診斷）。
    社會與心理狀況預設不列出，只回報筆數；需要時將 include_social 設為 True。
    標示為 sensitive 的項目屬敏感資訊，摘要時不應主動列出。
    資料來源未標示主診斷，請勿自行推測。

    Args:
        patient_id: FHIR 病人 ID，例如 "5829"
        active_only: 是否只回傳目前仍有效（active）的診斷，預設 True
        include_social: 是否列出社會與心理狀況，預設 False
    """
    check_patient(patient_id)
    params = {"subject": f"Patient/{patient_id}", "_sort": "-onset-date", "_count": 200}
    if active_only:
        params["clinical-status"] = "active"
    entries = fetch_all("Condition", params)

    results, hidden_social = [], 0
    for entry in entries:
        cond = entry["resource"]
        codings = cond.get("code", {}).get("coding", [])
        snomed = next((c for c in codings if c.get("system") == "http://snomed.info/sct"), {})
        info = CONDITION_MAP.get(snomed.get("code"), {})
        group = info.get("group", "B")
        if group == "C" and not include_social:
            hidden_social += 1
            continue
        verified = info.get("status") == "已查證"
        status = cond.get("clinicalStatus", {}).get("coding", [{}])[0]
        results.append({
            "condition": snomed.get("display") or cond.get("code", {}).get("text"),
            "snomed_code": snomed.get("code"),
            "icd10_code": info.get("icd10_code") if verified else None,
            "icd10_name": info.get("icd10_name_zh") if verified else "未對照",
            "group": GROUP_LABEL[group],
            "sensitive": info.get("sensitive") == "Y",
            "onset_date": cond.get("onsetDateTime"),
            "clinical_status": status.get("code"),
        })
    return {
        "primary_diagnosis": "資料來源未標示主診斷",
        "conditions": results,
        "hidden_social_count": hidden_social,
    }


@mcp.tool()
@log_tool_call
def get_medications(patient_id: str, active_only: bool = True) -> list[dict]:
    """查詢病人的開藥紀錄，依開立日期由新到舊排列。

    Args:
        patient_id: FHIR 病人 ID，例如 "5829"
        active_only: 是否只回傳目前仍有效（active）的處方，預設 True
    """
    check_patient(patient_id)
    params = {
        "subject": f"Patient/{patient_id}",
        "_sort": "-authoredon",
        "_count": 200,
        # 有些處方只寫「參照某個 Medication」，用 _include 把藥品資料一起帶回來
        "_include": "MedicationRequest:medication",
    }
    if active_only:
        params["status"] = "active"
    
    entries = fetch_all("MedicationRequest", params)
    
    medications = {
        f"Medication/{e['resource'].get('id')}": e["resource"]
        for e in entries
        if e["resource"].get("resourceType") == "Medication"
    }

    results = []
    for entry in entries:
        req = entry["resource"]
        if req.get("resourceType") != "MedicationRequest":
            continue
        # 藥品資訊可能直接寫在處方內，也可能放在另一筆 Medication 資源
        concept = req.get("medicationCodeableConcept")
        if concept is None:
            ref = req.get("medicationReference", {}).get("reference")
            concept = medications.get(ref, {}).get("code", {})
        codings = concept.get("coding", [])
        rxnorm = next((c for c in codings if "rxnorm" in c.get("system", "")), {})
        results.append({
            "medication": rxnorm.get("display") or concept.get("text"),
            "rxnorm_code": rxnorm.get("code"),
            "authored_on": req.get("authoredOn"),
            "status": req.get("status"),
        })
    return results


# 依臨床專家建議，糖尿病回診常看的檢驗項目（LOINC 代碼）
DIABETES_PANEL = {
    "糖化血色素 HbA1c": "4548-4",
    "血糖（資料未標示空腹或飯後）": "2339-0",
    "飯後兩小時血糖": "1521-4",
    "尿素氮 BUN": "6299-2",
    "肌酸酐 Creatinine": "38483-4",
    "腎絲球過濾率 eGFR": "33914-3",
    "總膽固醇": "2093-3",
    "三酸甘油脂": "2571-8",
    "低密度膽固醇 LDL": "18262-6",
    "高密度膽固醇 HDL": "2085-9",
    "血紅素 Hemoglobin": "718-7",
}


@mcp.tool()
@log_tool_call
def get_diabetes_panel(patient_id: str) -> list[dict]:
    """一次查詢糖尿病回診常看的檢驗組合，每一項回傳最近一次結果。

    包含：糖化血色素、血糖、飯後血糖、腎功能（BUN、Creatinine、eGFR）、
    血脂（總膽固醇、三酸甘油脂、LDL、HDL）、血紅素。
    資料庫沒有的項目會標示「查無紀錄」，不會省略。

    Args:
        patient_id: FHIR 病人 ID，例如 "5829"
    """
    check_patient(patient_id)
    results = []
    for item, code in DIABETES_PANEL.items():
        resp = httpx.get(f"{FHIR_BASE}/Observation", params={
            "subject": f"Patient/{patient_id}",
            "code": f"http://loinc.org|{code}",
            "_sort": "-date",
            "_count": 1,
        }, timeout=30)
        resp.raise_for_status()
        entries = resp.json().get("entry", [])
        if not entries:
            results.append({"item": item, "loinc": code, "status": "查無紀錄"})
            continue
        obs = entries[0]["resource"]
        quantity = obs.get("valueQuantity", {})
        results.append({
            "item": item,
            "loinc": code,
            "status": "ok",
            "date": obs.get("effectiveDateTime"),
            "value": quantity.get("value"),
            "unit": quantity.get("unit"),
        })
    return results

if __name__ == "__main__":
    mcp.run()