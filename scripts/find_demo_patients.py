'''uv run python scripts/find_demo_patients.py'''
"""掃描所有糖尿病病人，找出資料最豐富、數值合理，適合當展示和評估用的病人。"""
import httpx

FHIR_BASE = "http://localhost:8080/fhir"
DIABETES_CODE = "http://snomed.info/sct|44054006"
HBA1C_CODE = "http://loinc.org|4548-4"
# 常見糖尿病用藥關鍵字，只用來挑展示病人，不做臨床判斷
DM_MED_KEYWORDS = ["metformin", "insulin", "glipizide", "liraglutide",
                   "sitagliptin", "canagliflozin", "glyburide"]


def get_json(path, params):
    resp = httpx.get(f"{FHIR_BASE}/{path}", params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


# 第 1 步：找出所有有糖尿病診斷的病人 ID
bundle = get_json("Condition", {"code": DIABETES_CODE, "_count": 200})
patient_ids = sorted({
    e["resource"]["subject"]["reference"].split("/")[1]
    for e in bundle.get("entry", [])
})
print(f"找到 {len(patient_ids)} 位糖尿病病人，開始逐一檢查...\n")

# 第 2 步：每位病人算指標，並檢查糖化血色素數值是否合理
rows = []
for pid in patient_ids:
    obs = get_json("Observation", {
        "subject": f"Patient/{pid}", "code": HBA1C_CODE,
        "_count": 200, "_elements": "valueQuantity",
    })
    values = [
        e["resource"]["valueQuantity"]["value"]
        for e in obs.get("entry", [])
        if "valueQuantity" in e["resource"]
    ]
    # 糖化血色素合理範圍約 4%–15%，超出視為資料品質問題
    plausible = bool(values) and all(4 <= v <= 15 for v in values)

    meds_bundle = get_json("MedicationRequest", {
        "subject": f"Patient/{pid}", "_count": 200,
    })
    med_names = [
        c.get("display", "").lower()
        for e in meds_bundle.get("entry", [])
        for c in e["resource"].get("medicationCodeableConcept", {}).get("coding", [])
    ]
    dm_meds = sorted({k for k in DM_MED_KEYWORDS if any(k in m for m in med_names)})

    rows.append({
        "id": pid, "hba1c": len(values),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "plausible": plausible, "dm_meds": dm_meds, "total_meds": len(med_names),
    })

# 第 3 步：排序，數值合理優先，再看有沒有糖尿病藥、驗了幾次
rows.sort(key=lambda r: (r["plausible"], len(r["dm_meds"]) > 0, r["hba1c"]), reverse=True)

print(f"{'病人ID':<8}{'次數':<6}{'最低':<7}{'最高':<7}{'合理':<6}{'用藥數':<7}糖尿病用藥")
for r in rows[:15]:
    print(f"{r['id']:<8}{r['hba1c']:<6}{str(r['min']):<7}{str(r['max']):<7}"
          f"{'是' if r['plausible'] else '否':<6}{r['total_meds']:<7}{', '.join(r['dm_meds']) or '無'}")

# 額外統計：數值不合理的比例，之後寫進 README
bad = sum(1 for r in rows if r["hba1c"] > 0 and not r["plausible"])
measured = sum(1 for r in rows if r["hba1c"] > 0)
print(f"\n有糖化血色素紀錄的 {measured} 位病人中，{bad} 位有數值超出合理範圍")