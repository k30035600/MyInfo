# 말풍선: 카테고리 조회 vs 업종분류 조회 — 속성·차이점

비교 대상:
- **은행거래/신용카드 전처리 페이지**의 **"카테고리 조회"** 말풍선  
  (은행 `/bank`, 신용카드 `/card` — 전처리 메인 화면의 "카테고리 조회" 테이블)
- **금융정보 통합작업 페이지**의 **"업종분류 조회"** 말풍선  
  (금융정보 `/cash` — 전처리 메인 화면의 "업종분류 조회" 테이블)

---

## 1. 말풍선 속성 (공통)

두 말풍선은 **동일한 속성**으로 구현되어 있습니다.

### CSS

| 항목 | 값 |
|------|-----|
| Overlay | `#row-tooltip-overlay` · `position: fixed; inset: 0; z-index: 2147483647; pointer-events: none` |
| Bubble | `#row-tooltip-bubble` · `position: fixed; z-index: 2147483647; max-width: 480px; max-height: 70vh; min-width: 220px; min-height: 80px; overflow: auto` |
| 배경/테두리 | `background: rgb(255, 204, 128); border: 1px solid #ddd; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.15)` |
| 패딩/폰트 | `padding: 10px; font-size: 11px; line-height: 1.2; font-family: 'Malgun Gothic', sans-serif` |
| 제목 | `.tooltip-title` · 굵게, 하단 구분선 |
| 행 | `.tooltip-row` · flex, 키-값 한 줄 |
| 키 | `.tooltip-key` · flex: 0 0 100px, opacity 0.8 |
| 값 | `.tooltip-val` · flex: 1, word-break: break-all |
| 선택 행 강조 | `.row-tooltip-selected` · 배경 #bbb |

### 동작

- **표시**: `showRowTooltip(obj, targetEl, columnOrder)` — `obj`를 JSON 컬럼 순서(`columnOrder` 또는 `Object.keys(obj)`)로 키-값 나열.
- **위치**: 클릭한 행 아래·가운데 기준, 화면 밖이 되지 않도록 보정.
- **레이어**: 표시 시 `document.body.appendChild(overlay)` 로 overlay를 body 직계로 두어 최상위 노출.
- **닫기**: 말풍선 밖 클릭 시 `hideRowTooltip()`, ESC 키로도 닫기.

---

## 2. 차이점

속성·동작은 같고, **어느 페이지·어느 테이블·어떤 데이터를 쓰는지**만 다릅니다.

| 구분 | 은행/신용카드 전처리 — 카테고리 조회 | 금융정보 통합작업 — 업종분류 조회 |
|------|--------------------------------------|----------------------------------|
| **페이지** | 은행 `/bank`, 신용카드 `/card` | 금융정보 `/cash` |
| **테이블 제목** | 카테고리 조회 | 업종분류 조회 |
| **컨테이너** | `#category-query-content` | `#linkage-query-content` |
| **행 선택자** | `.category-query-row` | `.linkage-query-row` |
| **행 인덱스 속성** | `data-i` | `data-tx-index` |
| **데이터 변수** | `categoryQueryTableData` | `linkageTableData` |
| **데이터 소스** | 은행: bank_after / 신용카드: card_after (카테고리 적용 **거래** 목록) | linkage_table.json (**업종** 목록) |
| **말풍선 내용** | **거래 1건** (거래일, 입금액, 출금액, 카테고리, 적요 등) | **업종 1건** (업종분류, 업종리스크, 업종코드 등) |

---

## 3. 요약

- **속성**: 두 말풍선 모두 같은 CSS·같은 `showRowTooltip`/`hideRowTooltip`·같은 overlay/bubble 구조.
- **차이**: 사용하는 **페이지·테이블·데이터**만 다름.  
  - 카테고리 조회 → 거래 1건 상세  
  - 업종분류 조회 → 업종 1건 상세  

금융정보 통합작업 페이지의 "금융정보 통합조회(은행+카드)" 테이블에는 말풍선을 사용하지 않습니다.

---

## 4. 은행/신용카드에서 말풍선이 안 보이던 경우 (조치 내용)

- **가능 원인**: 은행/신용카드 전처리 페이지는 DOM/레이아웃이 금융정보와 달라, overlay를 `display: block`으로만 두면 **스택/리플로우 타이밍** 때문에 말풍선이 그려지지 않을 수 있음.
- **조치**:  
  - 말풍선 표시 시 `bubble.style.position = 'fixed'`, `visibility = 'visible'` 명시.  
  - `overlay.style.display = 'block'`, `bubble.style.display = 'block'` 은 **requestAnimationFrame** 안에서 한 프레임 뒤에 설정해, body에 붙은 뒤 다음 페인트에서 보이도록 함.
- 이렇게 하면 금융정보 "업종분류 조회"와 동일하게 은행/신용카드 "카테고리 조회" 말풍선도 보이도록 맞춤.
