# 2호(심야폐업지표) 적용 흐름과 관련 코드

## 1. 폐업 123건이 2호에 분류되지 않은 이유(가능성)

- **현재 코드상** `구분 == '폐업'`인 행은 반드시 2호(심야폐업지표)로 설정되도록 되어 있습니다.
- 그런데도 `cash_after.json`에서 `위험도분류 == '심야폐업지표'`가 0건이고, `구분 == '폐업'`이 123건이라면 아래를 의심할 수 있습니다.

1. **과거 버전으로 생성된 파일**  
   `cash_after.json`이 2호 로직이 들어가기 전, 또는 1호/2호 상수(분류제외지표, 심야폐업지표)가 도입되기 전에 생성된 경우, 당시에는 `위험도분류`가 비어 있거나 linkage만 적용된 상태로 저장되었을 수 있습니다.

2. **apply_risk_indicators 예외**  
   `merge_bank_card_to_cash_after()` 안에서 `apply_risk_indicators()` 실행 중 예외가 나면, 예외만 로그하고 **그 시점까지 변경된 df**로 저장이 이어질 수 있습니다. 2호 루프 전에 오류가 나면 폐업 행이 2호로 덮어씌워지지 않을 수 있습니다.

3. **해결 방법**  
   **금융정보 병합작업**에서 **「병합작업 다시 실행」**을 한 번 더 실행해 `cash_after`를 **현재 코드로 다시 생성**하면, 폐업 123건이 2호(심야폐업지표)로 나와야 합니다.

---

## 2. 2호 적용 관련 코드 위치

### 2.1 2호 적용 로직 (폐업 + 심야구분)

- **파일**: `MyCash/risk_indicators.py`
- **함수**: `apply_risk_indicators(df, category_table_path=None)`
- **위치**: 2호 블록 주석 `# ---------- 2호: 심야폐업지표 ...` 부근

```text
# 2호: 구분=='폐업' 이거나, 거래시간이 category_table의 "심야구분" 구간이면
# 위험도분류 = '심야폐업지표', 위험도 = 0.5 로 설정.
# '구분' 컬럼은 병합 시 카드 쪽에서만 '폐업'이 내려옴(은행은 '').
```

- **폐업 판단**: `_str(df.at[i, '구분']).strip() == '폐업'`
- **심야 판단**: `_is_simya(df.at[i, '거래시간'], simya_range)`  
  - `simya_range`는 **category_table**의 **분류='심야구분'** 행에서 로드.

### 2.2 심야구분 시간 구간 로드 (category_table)

- **파일**: `MyCash/risk_indicators.py`
- **함수**: `_load_simya_range(category_table_path)`
  - **역할**: `category_table.json`에서 **분류가 "심야구분"**인 행을 찾고, 그 행의 **키워드**에서 `시작시간/종료시간`(예: `22:00:00/06:00:00`)을 읽어 (시작분, 종료분) 튜플로 반환.
  - **조건**: `item.get('분류') == '심야구분'`, `키워드`에 `/`가 있어 두 부분으로 나뉨.
  - **넘침 구간**: 예) 22:00~06:00 → (1320, 360)처럼 자정을 넘는 구간도 처리.

### 2.3 심야 여부 판단 (거래시간이 구간 안인지)

- **파일**: `MyCash/risk_indicators.py`
- **함수**: `_is_simya(거래시간_str, simya_range)`
  - **역할**: `거래시간_str`을 0~1439(분)으로 파싱하고, `simya_range` 구간 안에 있으면 True.
  - **거래시간 파싱**: `_parse_time_to_minutes(t)` (HH:MM, HHMM 등 지원).

### 2.4 cash_after 생성 시 호출

- **파일**: `MyCash/cash_app.py`
- **함수**: `merge_bank_card_to_cash_after()`
  - **(5/6)** 단계에서 `apply_risk_indicators(df, category_table_path=CATEGORY_TABLE_PATH)` 호출.
- **category_table 경로**: `PROJECT_ROOT/.source/category_table.json` (`CATEGORY_TABLE_PATH`).

### 2.5 병합 시 '구분' 채우기 (폐업만 유지)

- **파일**: `MyCash/cash_app.py`
- **함수**: `_dataframe_to_cash_after_creation(df_bank, df_card)`
  - 카드 행: `'구분': _safe_구분(r.get('구분'))` → `_safe_구분()`은 값이 `'폐업'`일 때만 `'폐업'`, 그 외는 `''`.
  - 은행 행: `'구분': ''` (은행은 폐업 없음).

---

## 3. category_table에서 심야구분 설정 예시

- **분류**: `심야구분`
- **키워드**: 시간 구간 문자열, 예: `22:00:00/06:00:00` (22시~06시)

이렇게 되어 있으면 `_load_simya_range()`가 해당 구간을 읽어 2호 적용 시 **해당 시간대 거래**를 심야로 간주해 2호(심야폐업지표)로 분류합니다.
