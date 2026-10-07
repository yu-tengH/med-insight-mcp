from mcp.server.mcpserver import MCPServer
import httpx

FHIR_BASE = "http://localhost:8080/fhir"
mcp = MCPServer("med-insight") # 建立一個 MCP Server，名字叫 med-insight
@mcp.tool() # 這一行叫「裝飾器」，作用是告訴 MCP：「下面這個函式是一個工具，開放給 AI 使用」。少了這行，Claude 就看不到這個工具

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
def get_patient(patient_id: str) -> dict:
    """查詢病人的基本資料：姓名、性別、生日。

    Args:
        patient_id: FHIR 病人 ID，例如 "5829"
    """
    resp = httpx.get(f"{FHIR_BASE}/Patient/{patient_id}", timeout=30)
    resp.raise_for_status()
    patient = resp.json()

    # 一位病人可能有多個名字（例如婚前姓），優先取 use 為 official 的那一個
    names = patient.get("name", [])
    name = next((n for n in names if n.get("use") == "official"), names[0] if names else {})
    full_name = " ".join(name.get("given", []) + [name.get("family", "")]).strip()

    return {
        "id": patient.get("id"),
        "name": full_name or None,
        "gender": patient.get("gender"),
        "birth_date": patient.get("birthDate"),
    }


@mcp.tool()
def get_conditions(patient_id: str, active_only: bool = True) -> list[dict]:
    """查詢病人的診斷紀錄，依發病日期由新到舊排列。

    Args:
        patient_id: FHIR 病人 ID，例如 "5829"
        active_only: 是否只回傳目前仍有效（active）的診斷，預設 True
    """
    params = {
        "subject": f"Patient/{patient_id}",
        "_sort": "-onset-date",
        "_count": 200,
    }
    if active_only:
        params["clinical-status"] = "active"
    resp = httpx.get(f"{FHIR_BASE}/Condition", params=params, timeout=30)
    resp.raise_for_status()
    bundle = resp.json()

    results = []
    for entry in bundle.get("entry", []):
        cond = entry["resource"]
        codings = cond.get("code", {}).get("coding", [])
        snomed = next((c for c in codings if c.get("system") == "http://snomed.info/sct"), {})
        status = cond.get("clinicalStatus", {}).get("coding", [{}])[0]
        results.append({
            "condition": snomed.get("display") or cond.get("code", {}).get("text"),
            "snomed_code": snomed.get("code"),
            "onset_date": cond.get("onsetDateTime"),
            "clinical_status": status.get("code"),
        })
    return results


@mcp.tool()
def get_medications(patient_id: str, active_only: bool = True) -> list[dict]:
    """查詢病人的開藥紀錄，依開立日期由新到舊排列。

    Args:
        patient_id: FHIR 病人 ID，例如 "5829"
        active_only: 是否只回傳目前仍有效（active）的處方，預設 True
    """
    params = {
        "subject": f"Patient/{patient_id}",
        "_sort": "-authoredon",
        "_count": 200,
        # 有些處方只寫「參照某個 Medication」，用 _include 把藥品資料一起帶回來
        "_include": "MedicationRequest:medication",
    }
    if active_only:
        params["status"] = "active"
    resp = httpx.get(f"{FHIR_BASE}/MedicationRequest", params=params, timeout=30)
    resp.raise_for_status()
    bundle = resp.json()

    entries = bundle.get("entry", [])
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


if __name__ == "__main__":
    mcp.run()