from mcp.server.mcpserver import MCPServer
import httpx

FHIR_BASE = "http://localhost:8080/fhir"
mcp = MCPServer("med-insight") # 建立一個 MCP Server，名字叫 med-insight
# @mcp.tool() 這一行叫「裝飾器」，作用是告訴 MCP：「下面這個函式是一個工具，開放給 AI 使用」。少了這行，Claude 就看不到這個工具

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


if __name__ == "__main__":
    mcp.run()