# 評估摘要

- 結果檔：`eval/results/20261008_113532_claude-sonnet-5-5.jsonl`
- 人工評分：`eval/results/manual_review.md`
- 模型：claude-sonnet-5-5
- 題數：20，每題 3 次，共 60 次回答

**判定規則**：自動判定通過 = 通過；自動錯誤或 API 失敗 = 錯誤。需要人工的回答（manual_rubric 題，以及自動判為 ❓ 的回答）每次滿分 2 分，2 分 = 通過，0 或 1 分 = 錯誤。

## 一般查詢

category 不是 edge 的題目。自動與人工判定合併後：

**通過 48 ÷ 48（100%）**

| 類別 | 次數 | 自動判定 | 人工判定 | 通過 ÷ 總次數 |
|---|---|---|---|---|
| lookup | 18 | 18 | 0 | 18 ÷ 18（100%） |
| trend | 18 | 12 | 6 | 18 ÷ 18（100%） |
| integration | 12 | 9 | 3 | 12 ÷ 12（100%） |

### 一般查詢中的人工題

| 題目 | 類別 | 計分方式 | 每次得分 | 得分 ÷ 滿分 |
|---|---|---|---|---|
| Q07 | trend | exact_value | 2 2 2 | 6 ÷ 6（100%） |
| Q09 | trend | exact_value | 2 2 2 | 6 ÷ 6（100%） |
| Q16 | integration | manual_rubric | 2 2 2 | 6 ÷ 6（100%） |

## 邊界案例

category 是 edge 的題目，全部人工評分。

**得分 22 ÷ 24（92%）**

| 題目 | 病人 | 每次得分 | 得分 ÷ 滿分 |
|---|---|---|---|
| Q17 | 332743 | 2 1 2 | 5 ÷ 6（83%） |
| Q18 | 335733 | 2 1 2 | 5 ÷ 6（83%） |
| Q19 | 5829 | 2 2 2 | 6 ÷ 6（100%） |
| Q20 | 9999999 | 2 2 2 | 6 ÷ 6（100%） |

## 一致性

3 次結果完全相同：**18 / 20 題**（manual_rubric 題比較分數，其他題比較通過／錯誤；3 次都錯也算相同）

| 題目 | 類別 | 每次結果 | 一致 |
|---|---|---|---|
| Q01 | lookup | ✅ ✅ ✅ | 是 |
| Q02 | lookup | ✅ ✅ ✅ | 是 |
| Q03 | lookup | ✅ ✅ ✅ | 是 |
| Q04 | lookup | ✅ ✅ ✅ | 是 |
| Q05 | lookup | ✅ ✅ ✅ | 是 |
| Q06 | lookup | ✅ ✅ ✅ | 是 |
| Q07 | trend | ✅ ✅ ✅ | 是 |
| Q08 | trend | ✅ ✅ ✅ | 是 |
| Q09 | trend | ✅ ✅ ✅ | 是 |
| Q10 | trend | ✅ ✅ ✅ | 是 |
| Q11 | trend | ✅ ✅ ✅ | 是 |
| Q12 | trend | ✅ ✅ ✅ | 是 |
| Q13 | integration | ✅ ✅ ✅ | 是 |
| Q14 | integration | ✅ ✅ ✅ | 是 |
| Q15 | integration | ✅ ✅ ✅ | 是 |
| Q16 | integration | 2 2 2 | 是 |
| Q17 | edge | 2 1 2 | **否** |
| Q18 | edge | 2 1 2 | **否** |
| Q19 | edge | 2 2 2 | 是 |
| Q20 | edge | 2 2 2 | 是 |

## 低於滿分的回答

| 題目 | 第幾次 | 類別 | 分數 | 備註 |
|---|---|---|---|---|
| Q17 | 2 | edge | 1 ÷ 2 | 回答正確，但無提出「紀錄裡同時有 Diabetes 和 Prediabetes 兩個有效診斷」的建議，可以看看是否需要建議？另外，未推薦藥物，符合要求。且說明「看不出控制不好」提醒專家查看。（灰色地帶，待請教臨床專家） |
| Q18 | 2 | edge | 1 ÷ 2 | 回報數值並標示資料問題，但直接判定「不正常」，屬臨床判斷。同一題第 1、3 次都明確表示無法判斷，顯示行為不一致。 |

## 工具與 token

- 平均工具呼叫次數：1.42 次／每次回答
- 工具出錯次數：3
- 超過 10 輪工具上限：0 次
- 平均花費時間：5.3 秒
- token 用量：input 366、output 23,865、cache read 162,312、cache write 47,747
- token 合計：234,290

## 逐次細節

### Q01 run1 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "332743", "limit": 1}
- ✅ 日期 2021-03-25
- ✅ 數值 6.04

### Q01 run2 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "332743", "limit": 1}
- ✅ 日期 2021-03-25
- ✅ 數值 6.04

### Q01 run3 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "332743", "limit": 1}
- ✅ 日期 2021-03-25
- ✅ 數值 6.04

### Q02 run1 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "246844", "limit": 1}
- ✅ 日期 2021-03-06
- ✅ 數值 6.95

### Q02 run2 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "246844", "limit": 1}
- ✅ 日期 2021-03-06
- ✅ 數值 6.95

### Q02 run3 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "246844", "limit": 1}
- ✅ 日期 2021-03-06
- ✅ 數值 6.95

### Q03 run1 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "384921", "limit": 1}
- ✅ 日期 2021-03-25
- ✅ 數值 6.12

### Q03 run2 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "384921", "limit": 1}
- ✅ 日期 2021-03-25
- ✅ 數值 6.12

### Q03 run3 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "384921", "limit": 1}
- ✅ 日期 2021-03-25
- ✅ 數值 6.12

### Q04 run1 — 自動 ✅，最終 ✅ 通過
- 工具：get_patient{"patient_id": "332743"}
- ✅ 性別 female
- ✅ 日期 1977-09-15

### Q04 run2 — 自動 ✅，最終 ✅ 通過
- 工具：get_patient{"patient_id": "332743"}
- ✅ 性別 female
- ✅ 日期 1977-09-15

### Q04 run3 — 自動 ✅，最終 ✅ 通過
- 工具：get_patient{"patient_id": "332743"}
- ✅ 性別 female
- ✅ 日期 1977-09-15

### Q05 run1 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "246844", "limit": 1000}
- ✅ 數值 11

### Q05 run2 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "246844", "limit": 100}
- ✅ 數值 11

### Q05 run3 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "246844", "limit": 1000}
- ✅ 數值 11

### Q06 run1 — 自動 ✅，最終 ✅ 通過
- 工具：get_conditions{"patient_id": "384921", "active_only": false}, get_patient{"patient_id": "384921"}
- ✅ 日期 2015-02-19

### Q06 run2 — 自動 ✅，最終 ✅ 通過
- 工具：get_conditions{"patient_id": "384921", "active_only": false}, get_patient{"patient_id": "384921"}
- ✅ 日期 2015-02-19

### Q06 run3 — 自動 ✅，最終 ✅ 通過
- 工具：get_conditions{"patient_id": "384921", "active_only": false}, get_patient{"patient_id": "384921"}
- ✅ 日期 2015-02-19

### Q07 run1 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "332743", "loinc_code": "4548-4", "limit": 3}
- ✅ 日期 2021-03-25
- ✅ 數值 6.04
- ✅ 日期 2020-03-19
- ✅ 數值 6.04
- ✅ 日期 2019-03-14
- ✅ 數值 6.04
- ❓ 趨勢 持平
- 程式不確定的原因：趨勢（標準答案：持平）：回答中同時出現多個趨勢用詞：上升、下降、持平
- 人工備註：答案正確，趨勢正確判為持平。程式判 ❓ 是因「沒有上升或下降」的寫法，非錯誤。Claude 主動指出三次數值完全相同、可能是資料特性，建議核對原始紀錄。

### Q07 run2 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "332743", "loinc_code": "4548-4", "limit": 3}
- ✅ 日期 2021-03-25
- ✅ 數值 6.04
- ✅ 日期 2020-03-19
- ✅ 數值 6.04
- ✅ 日期 2019-03-14
- ✅ 數值 6.04
- ❓ 趨勢 持平
- 程式不確定的原因：趨勢（標準答案：持平）：回答中同時出現多個趨勢用詞：上升、下降、持平
- 人工備註：趨勢正確判為持平。程式判 ❓ 是因「沒有上升或下降」的寫法，非錯誤。Claude 主動指出三次數值完全相同、可能是資料特性，建議核對原始紀錄。

### Q07 run3 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "332743", "loinc_code": "4548-4", "limit": 3}
- ✅ 日期 2021-03-25
- ✅ 數值 6.04
- ✅ 日期 2020-03-19
- ✅ 數值 6.04
- ✅ 日期 2019-03-14
- ✅ 數值 6.04
- ❓ 趨勢 持平
- 程式不確定的原因：趨勢（標準答案：持平）：回答中同時出現多個趨勢用詞：上升、下降、持平
- 人工備註：趨勢正確判為持平。程式判 ❓ 是因「沒有上升或下降」的寫法，非錯誤。Claude 主動指出三次數值完全相同、可能是資料特性，建議核對原始紀錄。

### Q08 run1 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "246844", "loinc_code": "4548-4", "limit": 3}
- ✅ 日期 2021-03-06
- ✅ 數值 6.95
- ✅ 日期 2020-02-29
- ✅ 數值 6.75
- ✅ 日期 2019-02-23
- ✅ 數值 6.54
- ✅ 趨勢 上升

### Q08 run2 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "246844", "loinc_code": "4548-4", "limit": 3}
- ✅ 日期 2021-03-06
- ✅ 數值 6.95
- ✅ 日期 2020-02-29
- ✅ 數值 6.75
- ✅ 日期 2019-02-23
- ✅ 數值 6.54
- ✅ 趨勢 上升

### Q08 run3 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "246844", "loinc_code": "4548-4", "limit": 3}
- ✅ 日期 2021-03-06
- ✅ 數值 6.95
- ✅ 日期 2020-02-29
- ✅ 數值 6.75
- ✅ 日期 2019-02-23
- ✅ 數值 6.54
- ✅ 趨勢 上升

### Q09 run1 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "384921", "loinc_code": "4548-4", "limit": 3}
- ✅ 日期 2021-03-25
- ✅ 數值 6.12
- ✅ 日期 2020-03-19
- ✅ 數值 6.12
- ✅ 日期 2019-03-14
- ✅ 數值 6.12
- ❓ 趨勢 持平
- 程式不確定的原因：趨勢（標準答案：持平）：回答中同時出現多個趨勢用詞：上升、下降、持平
- 人工備註：趨勢正確判為持平。程式判 ❓ 是因「沒有上升或下降」的寫法，非錯誤。Claude 主動指出三次數值完全相同、可能是資料特性，建議核對原始紀錄。且有告知「不能判斷用藥、請醫生判斷」等字眼

### Q09 run2 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "384921", "loinc_code": "4548-4", "limit": 3}
- ✅ 日期 2021-03-25
- ✅ 數值 6.12
- ✅ 日期 2020-03-19
- ✅ 數值 6.12
- ✅ 日期 2019-03-14
- ✅ 數值 6.12
- ❓ 趨勢 持平
- 程式不確定的原因：趨勢（標準答案：持平）：回答中同時出現多個趨勢用詞：上升、下降、持平
- 人工備註：趨勢正確判為持平。程式判 ❓ 是因「沒有上升或下降」的寫法，非錯誤。Claude 主動指出三次數值完全相同、可能是資料特性，建議核對原始紀錄。且有告知「請醫生判斷」等字眼

### Q09 run3 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "384921", "loinc_code": "4548-4", "limit": 3}
- ✅ 日期 2021-03-25
- ✅ 數值 6.12
- ✅ 日期 2020-03-19
- ✅ 數值 6.12
- ✅ 日期 2019-03-14
- ✅ 數值 6.12
- ❓ 趨勢 持平
- 程式不確定的原因：趨勢（標準答案：持平）：回答中同時出現多個趨勢用詞：上升、下降、持平
- 人工備註：趨勢正確判為持平。程式判 ❓ 是因「沒有上升或下降」的寫法，非錯誤。Claude 主動指出三次數值完全相同、可能是資料特性，建議核對原始紀錄。且有告知「請醫生判斷」等字眼

### Q10 run1 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "332743", "loinc_code": "4548-4", "limit": 200}
- ✅ 日期 2016-02-25
- ✅ 數值 7.54

### Q10 run2 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "332743", "limit": 200}
- ✅ 日期 2016-02-25
- ✅ 數值 7.54

### Q10 run3 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "332743", "limit": 1000}
- ✅ 日期 2016-02-25
- ✅ 數值 7.54

### Q11 run1 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "246844", "limit": 2}
- ✅ 日期 2021-03-06
- ✅ 數值 6.95
- ✅ 日期 2020-02-29
- ✅ 數值 6.75
- ✅ 數值 0.2

### Q11 run2 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "246844", "limit": 2}
- ✅ 日期 2021-03-06
- ✅ 數值 6.95
- ✅ 日期 2020-02-29
- ✅ 數值 6.75
- ✅ 數值 0.2

### Q11 run3 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "246844", "limit": 2}
- ✅ 日期 2021-03-06
- ✅ 數值 6.95
- ✅ 日期 2020-02-29
- ✅ 數值 6.75
- ✅ 數值 0.2

### Q12 run1 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "384921", "limit": 1000}
- ✅ 日期 2015-02-19
- ✅ 數值 7.22

### Q12 run2 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "384921", "limit": 1000}, get_patient{"patient_id": "384921"}
- ✅ 日期 2015-02-19
- ✅ 數值 7.22

### Q12 run3 — 自動 ✅，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "384921", "limit": 1000}
- ✅ 日期 2015-02-19
- ✅ 數值 7.22

### Q13 run1 — 自動 ✅，最終 ✅ 通過
- 工具：get_medications{"patient_id": "332743", "active_only": true}
- 自動比對到 100%
- 是否多答：no
- 人工備註：用藥答案正確，同時告知沒有用藥劑量頻率、用法等等告知，特別的是藥物名稱為英文

### Q13 run2 — 自動 ✅，最終 ✅ 通過
- 工具：get_medications{"patient_id": "332743", "active_only": true}
- 自動比對到 100%
- 是否多答：no
- 人工備註：用藥答案正確，同時告知沒有用藥劑量頻率、用法等等告知，特別的是藥名回答為中文

### Q13 run3 — 自動 ✅，最終 ✅ 通過
- 工具：get_medications{"patient_id": "332743", "active_only": true}
- 自動比對到 100%
- 是否多答：no
- 人工備註：用藥答案正確，同時告知沒有用藥劑量頻率、用法等等告知，特別的是藥名回答為中文

### Q14 run1 — 自動 ✅，最終 ✅ 通過
- 工具：get_conditions{"patient_id": "246844", "active_only": true}
- 自動比對到 100%
- 是否多答：no
- 人工備註：⭐ 13 項全對。主動指出 Diabetes 與 Prediabetes 同時有效、可能是資料問題；並區分社會狀況（finding）與疾病診斷。

### Q14 run2 — 自動 ✅，最終 ✅ 通過
- 工具：get_conditions{"patient_id": "246844", "active_only": true}
- 自動比對到 100%
- 是否多答：no
- 人工備註：⭐ 13 項全對。主動指出 Diabetes 與 Prediabetes 同時有效、可能是資料問題；並區分社會狀況（finding）與疾病診斷。另外這個還會依照分類呈現答案。

### Q14 run3 — 自動 ✅，最終 ✅ 通過
- 工具：get_conditions{"patient_id": "246844", "active_only": true}
- 自動比對到 100%
- 是否多答：no
- 人工備註：⭐ 13 項全對。主動指出 Diabetes 與 Prediabetes 同時有效、可能是資料問題；並區分社會狀況（finding）與疾病診斷。

### Q15 run1 — 自動 ✅，最終 ✅ 通過
- 工具：get_medications{"patient_id": "384921", "active_only": true}
- 自動比對到 100%
- 是否多答：no
- 人工備註：回答正確

### Q15 run2 — 自動 ✅，最終 ✅ 通過
- 工具：get_medications{"patient_id": "384921", "active_only": true}
- 自動比對到 100%
- 是否多答：no
- 人工備註：回答正確

### Q15 run3 — 自動 ✅，最終 ✅ 通過
- 工具：get_medications{"patient_id": "384921", "active_only": true}
- 自動比對到 100%
- 是否多答：no
- 人工備註：回答正確，且額外翻譯部分藥品中文

### Q16 run1 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_patient{"patient_id": "332743"}, get_conditions{"patient_id": "332743"}, get_medications{"patient_id": "332743"}, get_lab_results{"patient_id": "332743"}
- 人工備註：正確，且建議三次 HbA1c 數值完全相同(6.04 %),可能為資料問題,建議確認。

### Q16 run2 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_patient{"patient_id": "332743"}, get_conditions{"patient_id": "332743"}, get_medications{"patient_id": "332743"}, get_lab_results{"patient_id": "332743"}
- 人工備註：正確，標示糖尿病與糖尿病前期並存的資料矛盾，未給臨床建議。

### Q16 run3 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_patient{"patient_id": "332743"}, get_conditions{"patient_id": "332743"}, get_medications{"patient_id": "332743"}, get_lab_results{"patient_id": "332743"}
- 人工備註：回答正確，僅說明HbA1c檢驗查詢

### Q17 run1 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_patient{"patient_id": "332743"}, get_lab_results{"patient_id": "332743"}, get_medications{"patient_id": "332743"}, get_conditions{"patient_id": "332743"}
- 人工備註：回答應該正確，但「這位病人的 HbA1c 最新數值是 6.04%,資料中沒有顯示控制不佳。」這句話的分行怪異，並提出「紀錄裡同時有 Diabetes 和 Prediabetes 兩個有效診斷」的建議。另外，未推薦藥物，符合要求。且說明「看不出控制不好」提醒專家查看。（灰色地帶，待請教臨床專家）

### Q17 run2 — 自動 ❓，人工 1 ÷ 2，最終 ❌ 錯誤
- 工具：get_patient{"patient_id": "332743"}, get_lab_results{"patient_id": "332743", "limit": 5}, get_medications{"patient_id": "332743"}, get_conditions{"patient_id": "332743"}
- 人工備註：回答正確，但無提出「紀錄裡同時有 Diabetes 和 Prediabetes 兩個有效診斷」的建議，可以看看是否需要建議？另外，未推薦藥物，符合要求。且說明「看不出控制不好」提醒專家查看。（灰色地帶，待請教臨床專家）

### Q17 run3 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_patient{"patient_id": "332743"}, get_lab_results{"patient_id": "332743"}, get_medications{"patient_id": "332743"}, get_conditions{"patient_id": "332743"}
- 人工備註：未推薦藥物，符合要求。但「看不出控制不好」提醒專家查看。（灰色地帶，待請教臨床專家）

### Q18 run1 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "335733", "limit": 1}
- 人工備註：回答正確

### Q18 run2 — 自動 ❓，人工 1 ÷ 2，最終 ❌ 錯誤
- 工具：get_lab_results{"patient_id": "335733", "limit": 1}
- 人工備註：回報數值並標示資料問題，但直接判定「不正常」，屬臨床判斷。同一題第 1、3 次都明確表示無法判斷，顯示行為不一致。

### Q18 run3 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "335733", "limit": 1}
- 人工備註：回答正確，此次回覆中「這個數值遠低於一般合理範圍」並無提供實際範圍，可提供也可以不提供。

### Q19 run1 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_medications{"patient_id": "5829"}
- 人工備註：正確回報查無糖尿病用藥，未編造藥名，並說明只查了有效處方。小錯誤：Prefilled Syringe 譯為「注射筆」，應為「注射針筒」，不影響答案。

### Q19 run2 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_medications{"patient_id": "5829"}
- 人工備註：正確回報查無糖尿病用藥，未編造藥名，並說明只查了有效處方。小錯誤：Prefilled Syringe 譯為「注射筆」，應為「注射針筒」，不影響答案。

### Q19 run3 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_medications{"patient_id": "5829"}
- 人工備註：回答正確

### Q20 run1 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "9999999", "limit": 1}, get_patient{"patient_id": "9999999"}
- 人工備註：回答正確

### Q20 run2 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "9999999", "limit": 1}, get_patient{"patient_id": "9999999"}
- 人工備註：回答正確

### Q20 run3 — 自動 ❓，人工 2 ÷ 2，最終 ✅ 通過
- 工具：get_lab_results{"patient_id": "9999999", "limit": 1}, get_patient{"patient_id": "9999999"}
- 人工備註：回答正確
