# -*- coding: utf-8 -*-
"""
category_table 기본 규칙 로드.
category_create.md 파싱 또는 코드 기본값 반환.
domain: 'bank' | 'cash' | 'card'
"""
import os
import re

try:
    from category_constants import CATEGORY_TABLE_COLUMNS
except ImportError:
    CATEGORY_TABLE_COLUMNS = ['분류', '키워드', '카테고리']

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, '.'))
CATEGORY_CREATE_MD = os.path.join(PROJECT_ROOT, '.source', 'category_create.md')

# md 파싱 실패 시 사용할 코드 기본값
_DEFAULT_PREPOST = [
    {'분류': '전처리', '키워드': 'NH', '카테고리': '농협'},
    {'분류': '전처리', '키워드': 'KB', '카테고리': '국민'},
    {'분류': '전처리', '키워드': '한국주택은행', '카테고리': '국민은행'},
    {'분류': '전처리', '키워드': '주금공', '카테고리': '주택금융공사'},
    {'분류': '후처리', '키워드': '((', '카테고리': '('},
    {'분류': '후처리', '키워드': '))', '카테고리': ')'},
    {'분류': '후처리', '키워드': '[]', '카테고리': 'space'},
]

_DEFAULT_ACCOUNT_RULES = [
    {'분류': '계정과목', '키워드': '파리바게뜨/베이커리', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '씨유/CU', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '(주)이마트/롯데마트/식자재/이마트', '카테고리': '주식비/부식비'},
    {'분류': '계정과목', '키워드': '가전/의류/가구/023/나눔과어울림', '카테고리': '가전/가구/의류/생필품'},
    {'분류': '계정과목', '키워드': '비와이씨/삼성전자/현대아울렛/나무다움/어패럴', '카테고리': '가전/가구/의류/생필품'},
    {'분류': '계정과목', '키워드': '스퀘어/자라/공영쇼핑/에이비씨/이랜드', '카테고리': '가전/가구/의류/생필품'},
    {'분류': '계정과목', '키워드': '몰테일/이케아/버킷/신세계/올리브영', '카테고리': '가전/가구/의류/생필품'},
    {'분류': '계정과목', '키워드': '버스/택시/차량유지/자동차/지하철/칼텍스/자동차보험/차량보험', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '북서울에너지/피킹/도로공사/티머니/에이티씨', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '인천30/인천32/시설공단/문학터널/문학개발/주유소', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '만월산/선학현대/후불교통/로드801/에너지/시설안전', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '파킹/현대오일/태리/코레일/철도', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '시설관리/기아오토큐/시설공단/국민오일', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '금은방/귀금속/거래소', '카테고리': '귀금속'},
    {'분류': '계정과목', '키워드': '클락에이/CU/GS/마트/쿠팡/네이버/후이즈/타이거', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '토스/쇼핑몰/쇼핑/보타나/공공기관/결재대행/결제대행', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': 'NICE/SMS/면세점/에이치/제이디/라프/씨유/플라워', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '엠에스/세탁소/세븐일레븐/법원/미앤미/헤어/지에스', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '예스이십사/코리아세븐/건설기술/티몬/에이스', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '다온나/아이지/미니스톱/우체국/월드/이투유/나이스', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '더에덴/옥션/나래/로그인/메트로/홈엔/ARS/카카오', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '와이에스/다날/홈마트/슈퍼/로웰/유니윌/코페이', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '스테이지/이마트24/부경/에스씨/목욕탕/구글', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '다이소/빈티지/마이리얼/홈쇼핑/올댓/그릇/로스', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '컬리페이/키오스크/에스지씨/에델/크린토피아/미성', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '블랙벤자민/LIVING/슬립/세탁/만물/그릇/유진/두찜', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '티무/황실/KICC/KCP/마이/플래티넘/몽실/가위', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '이니시스/메머드', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '오락/취미/레저/휴양/교보문고', '카테고리': '레저/휴양/취미/오락'},
    {'분류': '계정과목', '키워드': '중국동방/CGV', '카테고리': '레저/휴양/취미/오락'},
    {'분류': '계정과목', '키워드': '외식/회식/간식/호치킨/콩닭/모밀방/상회/필/삼계탕', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '제주도/애월/바이/해장국/족발/연쭈/모미락/도미노', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '맛있는죽/맥도날드/새록/칼국수/순대/식당/롯데리아', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '오구본가/연탄/파리바게뜨/타이거/김치/수산/국수', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '선학사골/천상/메가/스타벅스/엔제리너스/리너스/추어탕', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '더달달/컴포즈/닭집/할매/동태촌/왕냉면/통닭/아구', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '추어탕/부대/부대찌게/보리밥/본죽/카페/안스/식당/이학', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '아방궁/돈풀/카페온/부원집/능허대/옹진/상사/국밥', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '뜰아래/솔도갈매기/미두야/소바/포베이/10월/조개', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '오케이/웨이업/산자락에/막국수/공간븟/굴사냥', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '닭곰탕/메밀국수/저푸른/닭소리/사계절/두루담채', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '콩세알/지에스/바로/손만두/멕시카나/청량산/연어', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '빽다방/패류/씨푸드/해장국/김밥/이디야/어시장', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '장수마을/어부장/동춘옥/푸드/공차/이학/두부/모밀', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '반점/닭강정/생오리/떡방아/마장동/자판기/민영', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '조개/불닭발/직화/던킨/얼음/다정이네/올댓/메고', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '미스터/스마일/투썸/대신기업/손만두/휴게소/매반', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '만강홍/페리카나/최부자네/부대/부대찌게/공간븟/야래향/송도갈매기', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '엔제리너스/리너스/물고기/낙지', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '병원/의원/치과/약국/건강보험/나사렛/레푸스/메디컬', '카테고리': '의료비'},
    {'분류': '계정과목', '키워드': '이비인후과/신경외과/정형외과/엄마손/워너독', '카테고리': '의료비'},
    {'분류': '계정과목', '키워드': '견생냥품/동물의료/안과', '카테고리': '의료비'},
    {'분류': '계정과목', '키워드': '국세/지방세/세외/주민세/행정안전부/연수구청', '카테고리': '제세공과금'},
    {'분류': '계정과목', '키워드': '소득세/교육청/소액합산/행정복지/자동차세/취득세', '카테고리': '제세공과금'},
    {'분류': '계정과목', '키워드': '지자체/곡공기관/인천광역시/부가가치세/전몰', '카테고리': '제세공과금'},
    {'분류': '계정과목', '키워드': '수도/전기/한국전력/가스/통신/관리비/케이티/SK/수신료', '카테고리': '주거비/통신비'},
    {'분류': '계정과목', '키워드': '주식/부식/반찬/농산물/SSG/건어물/씨푸드/웅이/과일/야채/코스트코/홈플러스', '카테고리': '주식비/부식비'},
    {'분류': '계정과목', '키워드': '정육점/세계로/생선/푸줏간/우아한/성필립보', '카테고리': '주식비/부식비'},
    {'분류': '계정과목', '키워드': '현금/서비스/대출', '카테고리': '현금처리'},
    {'분류': '계정과목', '키워드': '신한은행/하나은행/신한카드/리볼빙', '카테고리': '현금처리'},
]

# 업종분류: 카테고리테이블에서 미사용(linkage_table.json으로만 적용). 기본값 제거.

# 가상자산 거래소 (분류=가상자산, 키워드=회사명/서비스명, 카테고리=사업자번호)
_DEFAULT_VIRTUAL_ASSET_RULES = [
    {'분류': '가상자산', '키워드': '두나무(주)/업비트', '카테고리': '119-86-54968'},
    {'분류': '가상자산', '키워드': '(주)코빗/코빗', '카테고리': '220-88-61399'},
    {'분류': '가상자산', '키워드': '(주)코인원/코인원', '카테고리': '261-81-07437'},
    {'분류': '가상자산', '키워드': '(주)빗썸/빗썸', '카테고리': '220-88-71844'},
    {'분류': '가상자산', '키워드': '(주)한국디지털거래소/플라이빗', '카테고리': '194-87-00761'},
    {'분류': '가상자산', '키워드': '(주)스트리미/고팍스', '카테고리': '432-87-00120'},
    {'분류': '가상자산', '키워드': '차일들리(주)/BTX', '카테고리': '729-86-01268'},
    {'분류': '가상자산', '키워드': '(주)포블게이트/포블', '카테고리': '136-87-01478'},
    {'분류': '가상자산', '키워드': '㈜코어닥스/코어닥스', '카테고리': '894-86-01183'},
    {'분류': '가상자산', '키워드': '(주)그레이브릿지/비블록', '카테고리': '155-86-01720'},
    {'분류': '가상자산', '키워드': '(주)포리스닥스코리아리미티드/오케이비트', '카테고리': '885-88-00694'},
    {'분류': '가상자산', '키워드': '(주)골든퓨쳐스/빗크몬', '카테고리': '791-81-00992'},
    {'분류': '가상자산', '키워드': '(주)프라뱅/프라뱅', '카테고리': '681-81-01205'},
    {'분류': '가상자산', '키워드': '(주)보라비트/보라비트', '카테고리': '280-88-00977'},
    {'분류': '가상자산', '키워드': '(주)한국디지털에셋/코다(KODA)', '카테고리': '618-81-36254'},
    {'분류': '가상자산', '키워드': '(주)한국디지털자산수탁/케이닥(KDAC)', '카테고리': '809-86-01583'},
    {'분류': '가상자산', '키워드': '(주)월렛원/오하이월렛', '카테고리': '636-88-00831'},
    {'분류': '가상자산', '키워드': '하이퍼리즘유한책임회사/하이퍼리즘', '카테고리': '477-86-01090'},
    {'분류': '가상자산', '키워드': '㈜가디언홀딩스/오아시스거래소', '카테고리': '826-81-00997'},
    {'분류': '가상자산', '키워드': '(주)마인드시프트/커스텔라', '카테고리': '634-86-01747'},
    {'분류': '가상자산', '키워드': '(주)인피닛블록/인피닛블록', '카테고리': '306-88-02374'},
    {'분류': '가상자산', '키워드': '㈜디에스알브이랩스/디에스알브이랩스', '카테고리': '659-87-01307'},
    {'분류': '가상자산', '키워드': '비댁스(주)/비댁스', '카테고리': '376-88-02126'},
    {'분류': '가상자산', '키워드': '㈜인피니티익스체인지코리아/INEX(인엑스)', '카테고리': '783-81-02738'},
    {'분류': '가상자산', '키워드': '㈜웨이브릿지/웨이브릿지프라임', '카테고리': '767-88-01245'},
    {'분류': '가상자산', '키워드': '㈜해피블록/바우맨', '카테고리': '712-86-02691'},
    {'분류': '가상자산', '키워드': '㈜블로세이프/로빗', '카테고리': '741-86-02855'},
]

# 금전대부(대부중개/P2P연계대부) — 종합의견 위험도 5.0
_DEFAULT_LOAN_RULES = [
    {'분류': '금전대부', '키워드': '대부중개/P2P/P2P연계대부/채권추심/대부중개사이트', '카테고리': '금전대부'},
]

# 증권거래(선물/투자운용) — 종합의견 위험도 5.0
_DEFAULT_SECURITIES_RULES = [
    {'분류': '증권투자', '키워드': '선물/옵션/투자운용/증권/펀드', '카테고리': '증권거래'},
]


def _parse_md_table(lines):
    """마크다운 테이블 파싱. | col1 | col2 | col3 | 형태."""
    rows = []
    cols = None
    for line in lines:
        line = line.strip()
        if not line or not line.startswith('|'):
            continue
        parts = [p.strip() for p in line.split('|') if p.strip()]
        if not parts:
            continue
        if cols is None:
            if parts[0] == '분류' or '분류' in parts:
                cols = parts
                continue
            cols = CATEGORY_TABLE_COLUMNS
        # 구분선 행 스킵 (|---|-----| 형태)
        if parts[0] and all(c in '-:' for c in str(parts[0])):
            continue
        if len(parts) >= 3:
            rows.append({'분류': parts[0], '키워드': parts[1], '카테고리': parts[2]})
        elif len(parts) == 2:
            rows.append({'분류': parts[0], '키워드': parts[1], '카테고리': ''})
        elif len(parts) == 1:
            rows.append({'분류': parts[0], '키워드': '', '카테고리': ''})
    return rows


def _parse_category_create_md(path=None):
    """category_create.md 파싱. 섹션별 {section_name: [dict, ...]} 반환."""
    path = path or CATEGORY_CREATE_MD
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return {}
    sections = {}
    current_section = None
    current_lines = []
    for line in content.split('\n'):
        if line.strip().startswith('## '):
            if current_section is not None and current_lines:
                rows = _parse_md_table(current_lines)
                if rows:
                    sections[current_section] = rows
            m = re.match(r'^##\s+(.+?)(?:\s*\(|$)', line.strip())
            current_section = m.group(1).strip() if m else line.replace('##', '').strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_section and current_lines:
        rows = _parse_md_table(current_lines)
        if rows:
            sections[current_section] = rows
    return sections


def sync_category_create_from_xlsx(category_xlsx_path, md_path=None):
    """category_table.json(.xlsx) 내용을 category_create.md에 반영. 입력/수정/삭제 후 호출."""
    try:
        import pandas as pd
        path = md_path or CATEGORY_CREATE_MD
        if not category_xlsx_path or not os.path.exists(category_xlsx_path):
            return False
        if str(category_xlsx_path).lower().endswith('.json'):
            import json
            with open(category_xlsx_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            df = pd.DataFrame(data) if data else pd.DataFrame()
        else:
            df = pd.read_excel(category_xlsx_path, engine='openpyxl')
        if df is None or df.empty:
            return False
        for c in CATEGORY_TABLE_COLUMNS:
            if c not in df.columns:
                df[c] = ''
        df = df.fillna('').astype(str)
        # 카테고리테이블에서는 업종분류 미사용 — md에 반영하지 않음
        df = df[df['분류'].astype(str).str.strip() != '업종분류'].copy()
        # 섹션 매핑: 분류 -> md 헤더
        section_map = {
            '전처리': '전처리/후처리 (bank, cash 공통)',
            '후처리': '전처리/후처리 (bank, cash 공통)',
            '계정과목': '계정과목 (bank, card)',
            '가상자산': '가상자산',
            '증권투자': '증권투자',
            '해외송금': '해외송금',
            '심야구분': '심야구분',
        }
        sections = {}
        for _, row in df.iterrows():
            분류 = str(row.get('분류', '')).strip()
            키워드 = str(row.get('키워드', '')).strip()
            카테고리 = str(row.get('카테고리', '')).strip()
            if not 분류 and not 키워드 and not 카테고리:
                continue
            if not 분류:
                분류 = '계정과목'
            header = section_map.get(분류, 분류)
            if header not in sections:
                sections[header] = []
            sections[header].append({'분류': 분류, '키워드': 키워드, '카테고리': 카테고리})
        # 전처리/후처리: 전처리와 후처리 병합 (순서: 전처리 먼저)
        if '전처리/후처리 (bank, cash 공통)' in sections:
            rows = sections['전처리/후처리 (bank, cash 공통)']
            rows.sort(key=lambda r: (0 if r['분류'] == '전처리' else 1, r['키워드']))
            sections['전처리/후처리 (bank, cash 공통)'] = rows
        # md 생성
        lines = [
            '# category_table 기본 규칙',
            '',
            '은행거래·금융정보·신용카드 공통 category_table.json 생성 시 사용.',
            'create_category_table(bank/cash/card) 호출 시 이 파일 또는 코드 기본값을 참조.',
            '',
            '---',
            '',
        ]
        order = [
            '전처리/후처리 (bank, cash 공통)',
            '계정과목 (bank, card)',
            '가상자산', '증권투자', '해외송금', '심야구분',
        ]
        for header in order:
            if header not in sections or not sections[header]:
                continue
            lines.append(f'## {header}')
            lines.append('')
            lines.append('| 분류 | 키워드 | 카테고리 |')
            lines.append('|------|--------|----------|')
            for r in sections[header]:
                분류 = (r.get('분류', '') or '').replace('|', '\\|')
                키워드 = (r.get('키워드', '') or '').replace('|', '\\|')
                카테고리 = (r.get('카테고리', '') or '').replace('|', '\\|')
                lines.append(f'| {분류} | {키워드} | {카테고리} |')
            lines.append('')
            lines.append('---')
            lines.append('')
        for header, rows in sections.items():
            if header in order:
                continue
            lines.append(f'## {header}')
            lines.append('')
            lines.append('| 분류 | 키워드 | 카테고리 |')
            lines.append('|------|--------|----------|')
            for r in rows:
                분류 = (r.get('분류', '') or '').replace('|', '\\|')
                키워드 = (r.get('키워드', '') or '').replace('|', '\\|')
                카테고리 = (r.get('카테고리', '') or '').replace('|', '\\|')
                lines.append(f'| {분류} | {키워드} | {카테고리} |')
            lines.append('')
            lines.append('---')
            lines.append('')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True
    except Exception:
        return False


def get_default_rules(domain, md_path=None):
    """
    domain별 기본 규칙 반환.
    - bank: 전처리/후처리 + 계정과목
    - cash: 전처리/후처리만
    - card: 계정과목 + 가상자산/금전대부/증권투자 (업종분류는 카테고리테이블 미사용)
    """
    sections = _parse_category_create_md(md_path)
    result = []
    prepost = sections.get('전처리/후처리 (bank, cash 공통)', sections.get('전처리/후처리', []))
    account = sections.get('계정과목 (bank, card)', sections.get('계정과목', []))
    if not prepost:
        prepost = _DEFAULT_PREPOST
    if domain == 'bank':
        result.extend(prepost)
        result.extend(account if account else _DEFAULT_ACCOUNT_RULES)
    elif domain == 'cash':
        result.extend(prepost)
    elif domain == 'card':
        result.extend(account if account else _DEFAULT_ACCOUNT_RULES)
        result.extend(_DEFAULT_VIRTUAL_ASSET_RULES)
        result.extend(_DEFAULT_LOAN_RULES)
        result.extend(_DEFAULT_SECURITIES_RULES)
    if not result:
        result = list(_DEFAULT_PREPOST)
    seen = set()
    unique = []
    for r in result:
        분류 = str(r.get('분류', '')).strip()
        키워드 = str(r.get('키워드', '')).strip()
        카테고리 = str(r.get('카테고리', '')).strip()
        key = (분류, 키워드, 카테고리)
        if key not in seen:
            seen.add(key)
            unique.append({'분류': 분류, '키워드': 키워드, '카테고리': 카테고리})
    return unique
