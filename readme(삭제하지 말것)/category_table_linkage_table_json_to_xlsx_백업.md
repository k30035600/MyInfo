# category_table / linkage_table JSON → xlsx 백업

**category_table.json**과 **linkage_table.json**을 각각 xlsx 파일로 내보내 백업·엑셀 편집용으로 사용하는 방법입니다.

---

## 1. 요약

| 항목 | category_table | linkage_table |
|------|----------------|---------------|
| **원본 JSON** | `MyInfo/.source/category_table.json` | `MyInfo/.source/linkage_table.json` |
| **내보내기 결과** | `MyInfo/.source/category_table.xlsx` | `MyInfo/.source/linkage_table.xlsx` |
| **용도** | 백업, 엑셀 편집, 구버전 도구 호환 | 백업, 엑셀 편집, json 없을 때 json 재생성용 |

- 앱(은행/카드/금융정보)은 **JSON만** 읽고 씁니다. xlsx는 **백업·참고·엑셀 편집용**입니다.
- linkage_table은 json이 없을 때 xlsx를 읽어 json을 만들 수 있으므로, xlsx를 주기적으로 내보내 두면 복구에 유리합니다.

---

## 2. 한 번에 두 테이블 백업 (권장)

프로젝트 루트(MyInfo)에서 다음을 실행하면 **category_table**과 **linkage_table** JSON이 각각 xlsx로 저장됩니다.

```powershell
cd MyInfo
python scripts/json_to_xlsx_backup.py
```

- **성공 시**: `[OK] category_table.xlsx`, `[OK] linkage_table.xlsx` 출력.
- **실패 시**: 해당 파일 오류 메시지 출력 후 종료 코드 1.

---

## 3. 개별 실행

### 3.1 category_table만 xlsx로

```powershell
cd MyInfo
python "readme(삭제하지 말것)/export_category_table_to_xlsx.py"
```

- 상세: [category_table_xlsx_복구.md](category_table_xlsx_복구.md)

### 3.2 linkage_table만 xlsx로

```python
# 프로젝트 루트에서
from linkage_table_io import export_linkage_table_to_xlsx

ok, path, err = export_linkage_table_to_xlsx()
if ok:
    print("저장됨:", path)
else:
    print("실패:", err)
```

---

## 4. xlsx 컬럼

### category_table.xlsx

| 컬럼 | 설명 |
|------|------|
| 분류 | 전처리, 후처리, 계정과목 등 |
| 키워드 | 매칭 키워드 (복수 시 `/` 구분) |
| 카테고리 | 매칭 시 넣을 값 |

### linkage_table.xlsx

| 컬럼 | 설명 |
|------|------|
| 업종분류 | 자료소명지표, 비정형지표, 투기성지표 등 |
| 업종리스크 | 위험도 수치 (소수점 1자리, 예: 1.0, 3.5) |
| 업종코드 | 업종 코드 (숫자일 경우 소수점 없이 문자) |
| 업종코드세세분류 | 세세 분류 설명 |

---

## 5. 관련 파일

| 파일 | 역할 |
|------|------|
| `scripts/json_to_xlsx_backup.py` | 두 JSON을 한 번에 xlsx로 내보내는 스크립트 |
| `category_table_io.py` | `export_category_table_to_xlsx()` 제공 |
| `linkage_table_io.py` | `export_linkage_table_to_xlsx()` 제공 |
| `readme(삭제하지 말것)/export_category_table_to_xlsx.py` | category_table만 xlsx로 내보내는 스크립트 |
| [category_table_xlsx_복구.md](category_table_xlsx_복구.md) | category_table xlsx 복구 상세 |
