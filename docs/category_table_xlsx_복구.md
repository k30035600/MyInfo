# category_table을 xlsx로 복구(내보내기)

**category_table.json** 내용을 **category_table.xlsx**로 내보내는 방법입니다.  
엑셀에서 편집·백업·공유할 때 사용합니다.

---

## 1. 요약

| 항목 | 내용 |
|------|------|
| **원본** | `MyInfo/.source/category_table.json` (앱은 이 파일만 사용) |
| **복구 결과** | `MyInfo/.source/category_table.xlsx` (동일 폴더에 생성) |
| **용도** | 백업, 엑셀에서 편집, 구버전 도구와 호환 |

- 앱(은행/카드/금융정보)은 **JSON만** 읽고 씁니다. xlsx는 **참고·백업·엑셀 편집용**입니다.
- xlsx를 수정한 뒤 다시 앱에 반영하려면, JSON으로 옮기거나 카테고리 화면에서 입력/수정해야 합니다.

---

## 2. 방법: 스크립트 실행

프로젝트 루트에서 다음을 실행합니다.

```powershell
cd MyInfo
python export_category_table_to_xlsx.py
```

- 성공 시: `저장됨: ...\.source\category_table.xlsx` 출력.
- 실패 시: 오류 메시지 출력 후 종료 코드 1.

---

## 3. 방법: Python에서 직접 호출

```python
import sys
import os
sys.path.insert(0, 'MyInfo')  # 프로젝트 루트 기준

from category_table_io import export_category_table_to_xlsx, get_category_table_path

ok, xlsx_path, err = export_category_table_to_xlsx(get_category_table_path())
if ok:
    print("저장됨:", xlsx_path)
else:
    print("실패:", err)
```

- **경로 지정**: `export_category_table_to_xlsx("C:/경로/.source/category_table.json")` 처럼 인자로 넘길 수 있습니다.

---

## 4. xlsx 컬럼

| 컬럼 | 설명 |
|------|------|
| **분류** | 전처리, 후처리, 계정과목, 신용카드, 가상자산 등 |
| **키워드** | 매칭에 쓰는 키워드 (복수일 때 `/`로 구분) |
| **카테고리** | 매칭 시 넣을 값 |

- **업종분류**는 카테고리 테이블에서 사용하지 않습니다. (신용카드 가맹점 등은 linkage 등 별도 처리.)

---

## 5. xlsx 수정 후 JSON에 반영하려면

1. **카테고리 화면 사용**: 웹 앱의 카테고리 페이지에서 항목 추가/수정/삭제하면 **JSON에만** 저장됩니다.  
   → 필요 시 위 방법으로 다시 **JSON → xlsx** 내보내기만 하면 됩니다.

2. **xlsx만 수정한 경우**:  
   - 현재 앱은 **xlsx → JSON** 자동 반영 기능을 제공하지 않습니다.  
   - xlsx에서 편집한 내용을 쓰려면, 카테고리 화면에서 같은 내용을 입력하거나,  
     JSON 파일을 직접 편집(또는 별도 스크립트로 xlsx → JSON 변환)해야 합니다.

---

## 6. 관련 파일

| 파일 | 역할 |
|------|------|
| `category_table_io.py` | `export_category_table_to_xlsx()` 함수 제공 |
| `export_category_table_to_xlsx.py` | 위 함수를 호출하는 실행 스크립트 |
| `.source/category_table.json` | 앱이 사용하는 카테고리 원본 |
| `.source/category_table.xlsx` | 위 스크립트 실행 시 생성되는 엑셀 파일 |
