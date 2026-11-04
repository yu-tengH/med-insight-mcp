"""列出糖尿病病人身上出現過的所有診斷（SNOMED），依出現人數排序，作為 ICD-10 對照的範圍。"""
import httpx
from collections import Counter

FHIR_BASE = "http://localhost:8080/fhir"

bundle = httpx.get(f"{FHIR_BASE}/Condition", params={
    "code": "http://snomed.info/sct|44054006", "_count": 200}, timeout=60).json()
patient_ids = {e["resource"]["subject"]["reference"].split("/")[1] for e in bundle.get("entry", [])}

counter, names = Counter(), {}
for pid in patient_ids:
    conds = httpx.get(f"{FHIR_BASE}/Condition", params={
        "subject": f"Patient/{pid}", "_count": 500}, timeout=60).json()
    seen = set()
    for e in conds.get("entry", []):
        for c in e["resource"].get("code", {}).get("coding", []):
            if "snomed" in c.get("system", "") and c["code"] not in seen:
                seen.add(c["code"])
                names[c["code"]] = c.get("display")
    counter.update(seen)

print(f"{len(patient_ids)} 位糖尿病病人，共 {len(counter)} 種不同診斷\n")
for code, n in counter.most_common():
    print(f"{n:>3} 人  {code:<12} {names[code]}")