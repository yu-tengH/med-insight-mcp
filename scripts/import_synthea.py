import glob, time, urllib.request, urllib.error

BASE = "http://localhost:8080/fhir"
LIMIT = None  # 先測 3 位病人，成功後改成 None 匯入全部

files = sorted(glob.glob("data/raw/fhir/*.json"))
first = [f for f in files if "Information" in f]       # 醫院、醫師
patients = [f for f in files if "Information" not in f]
if LIMIT:
    patients = patients[:LIMIT]
todo = first + patients

def post(path):
    with open(path, "rb") as fh:
        req = urllib.request.Request(
            BASE, data=fh.read(), method="POST",
            headers={"Content-Type": "application/fhir+json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.status

failed = []
start = time.time()
for i, f in enumerate(todo, 1):
    try:
        post(f)
    except urllib.error.HTTPError as e:
        failed.append(f"{f} | {e.code} | {e.read()[:300]}")
    except Exception as e:
        failed.append(f"{f} | {e}")
    if i % 25 == 0 or i == len(todo) or i <= 5:
        print(f"{i}/{len(todo)}，經過 {time.time() - start:.0f} 秒，進度已達到{i/len(todo):.2%}")

print(f"失敗：{len(failed)} 筆")
with open("data/import_failures.log", "w") as out:
    out.write("\n".join(failed))