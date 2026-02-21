# category.* 통합 가이드

## 현재 구조

### HTML (도메인별 3개)
| 파일 | 용도 | 줄 수 |
|------|------|-------|
| `MyBank/templates/category.html` | 은행거래 카테고리 | ~2,461 |
| `MyCard/templates/category.html` | 신용카드 카테고리 | ~2,957 |
| `MyCash/templates/category.html` | 금융정보 업종분류 | ~2,896 |

- 공통: 레이아웃·CSS·Chart.js, 네비게이션, 테이블/필터 구조
- 차이: 제목, API 경로(`/bank/`, `/card/`, `/cash/`), 컬럼(은행명/계좌 vs 카드사/카드번호 vs 구분 등), 도메인별 JS

### Python (루트)
| 파일 | 역할 |
|------|------|
| `category_constants.py` | 공통 상수(컬럼명, 분류 허용값) |
| `category_table_io.py` | JSON 읽기/쓰기, 정규화 |
| `category_table_defaults.py` | 도메인별 기본 규칙(bank/card/cash) |
| `category_table_fallback.py` | io import 실패 시 폴백 |
| `export_category_table_to_xlsx.py` | xlsx 내보내기 스크립트 |

---

## 통합 가능 여부

### Python 쪽
- **역할이 이미 나뉘어 있어서** 무리하게 하나로 합치면 파일이 비대해지고 유지보수가 어려워짐.
- `category_constants` + `category_table_io`를 하나의 `category_table.py`로 묶는 정도는 가능하나, 선택 사항.
- **권장**: 현재처럼 모듈 분리 유지.

### HTML 쪽 — 통합 가능 (2가지 방식)

#### 방식 A: 단일 템플릿 + domain 변수
- **한 개** `category.html` (공통 템플릿 폴더에 두고, Bank/Card/Cash에서 모두 이 템플릿 렌더).
- 서버에서 `domain='bank'|'card'|'cash'` 전달.
- 템플릿/JS에서 `domain`에 따라 제목·API 경로·컬럼·레이블 분기.
- **장점**: 파일 하나만 관리.  
- **단점**: 분기 많아지고, 3개 도메인 차이를 한 파일에 모두 넣어야 함.

#### 방식 B (권장): 공통 base + 도메인별 작은 템플릿
- **공통**: `templates_shared/base_category.html`  
  - 공통 CSS, 레이아웃, 네비, 공통 스크립트, `block title`, `block api_config`, `block table_columns` 등.
- **도메인별**:  
  - `MyBank/templates/category.html` → `{% extends "base_category.html" %}`, 제목·API·컬럼만 정의.  
  - MyCard, MyCash 동일.
- **장점**: 공통 부분 한 곳에서 관리, 도메인별 차이는 짧은 템플릿에만 유지.  
- **단점**: 공통 템플릿 폴더 설정 및 Flask에서 공통 폴더 로드 필요.

---

## 통합 진행 시 필요한 작업 (HTML 방식 B 기준)

1. **공통 템플릿 폴더**
   - 예: `MyInfo/templates_shared/` 생성.
   - `bank_app`, `card_app`, `cash_app`에서 이 폴더를 두 번째 template 폴더로 등록.

2. **base_category.html 작성**
   - 기존 `MyBank/templates/category.html` 기준으로 공통 부분만 추출.
   - `{% block title %}`, `{% block api_base %}`, `{% block columns %}`, `{% block extra_js %}` 등 정의.

3. **도메인별 category.html 축소**
   - Bank/Card/Cash 각각 `{% extends "base_category.html" %}` + 블록 채우기만 남김.

4. **테스트**
   - `/bank/` 카테고리, `/card/` 카테고리, `/cash/` 카테고리 동작·API·필터 동일한지 확인.

---

## 요약

| 대상 | 통합 여부 | 비고 |
|------|-----------|------|
| **Python** | 선택적 | 현재 구조 유지 권장. 필요 시 constants+io만 통합 가능. |
| **HTML** | 가능 | 방식 B(공통 base + 도메인별 extends) 권장. 작업량 있음. |

원하면 **방식 B**로 공통 base 설계와 블록 분리부터 단계별로 진행할 수 있음.
