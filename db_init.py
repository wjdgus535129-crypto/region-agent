import requests
import sqlite3
import os
import sys
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ===== 인증키 (.env 또는 Streamlit Cloud Secrets에서 읽어옴) =====
MOLIT_KEY = os.environ.get("MOLIT_KEY", "")
DATA_KEY = os.environ.get("DATA_KEY", "")
KOSIS_KEY = os.environ.get("KOSIS_KEY", "")  # kosis.kr/openapi 발급 키 (노후도 지역코드 목록 조회 전용)

# ===== 전월 기준 =====
def get_month_range(months=12):
    now = datetime.now()
    base = datetime(now.year, now.month, 1) - timedelta(days=1)
    result = []
    for i in range(months):
        d = datetime(base.year, base.month, 1) - timedelta(days=30*i)
        result.append(d.strftime("%Y%m"))
    result = sorted(set(result))
    return result[0], result[-1]

# ===== 전전월 기준 =====
def get_month_range_stable(months=12):
    now = datetime.now()
    end = datetime(now.year, now.month, 1) - timedelta(days=60)
    start = datetime(end.year, end.month, 1) - timedelta(days=30*(months-1))
    return start.strftime("%Y%m"), end.strftime("%Y%m")

# ===== DB 초기화 =====
def init_db():
    conn = sqlite3.connect("pf_data.db")
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS 미분양 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, sigungu TEXT, sido TEXT, value INTEGER, updated_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS 인허가 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, sido TEXT, value INTEGER, updated_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS 착공 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, sido TEXT, value INTEGER, updated_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS 준공 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, sido TEXT, value INTEGER, updated_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS 인구 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, sido TEXT, sigungu TEXT,
        pop INTEGER, household INTEGER, updated_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS 노후도 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year TEXT, sigungu TEXT,
        built_before_1990 INTEGER, built_1990_2000 INTEGER,
        built_2000_2010 INTEGER, built_after_2010 INTEGER,
        total INTEGER, updated_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS 청약경쟁률 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, region TEXT, supply_rate REAL, special_rate REAL,
        supply_cnt INTEGER, req_cnt INTEGER, updated_at TEXT)""")
    conn.commit()
    conn.close()
    print("✅ DB 초기화 완료")

# ===== 통계누리 API =====
def fetch_molit(form_id, style_num, start_dt, end_dt):
    url = "http://stat.molit.go.kr/portal/openapi/service/rest/getList.do"
    params = {"key": MOLIT_KEY, "form_id": form_id, "style_num": style_num,
              "start_dt": start_dt, "end_dt": end_dt}
    res = requests.get(url, params=params)
    try:
        return res.json()["result_data"]["formList"]
    except (KeyError, ValueError) as e:
        print(f"  ⚠ fetch_molit 응답 이상 (form_id={form_id}, {start_dt}~{end_dt}): {e}")
        print(f"  응답 원문: {res.text[:1000]}")
        raise

# ===== 미분양 =====
def save_미분양(start_dt, end_dt):
    items = fetch_molit(2082, 128, start_dt, end_dt)
    conn = sqlite3.connect("pf_data.db")
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    for item in items:
        if item.get("시군구") == "계":
            continue
        cur.execute("INSERT INTO 미분양 (date, sigungu, sido, value, updated_at) VALUES (?,?,?,?,?)",
            (item.get("date"), item.get("시군구"), item.get("구분"),
             int(item.get("미분양현황", 0) or 0), now))
        count += 1
    conn.commit()
    conn.close()
    print(f"✅ 미분양 {count}건 저장 완료")

# ===== 인허가 =====
def save_인허가(start_dt, end_dt):
    items = fetch_molit(1952, 1, start_dt, end_dt)
    conn = sqlite3.connect("pf_data.db")
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    for item in items:
        if item.get("규모") != "계":
            continue
        sido = item.get("시도별", "")
        if not sido or sido in ["전국", ""]:
            continue
        cur.execute("INSERT INTO 인허가 (date, sido, value, updated_at) VALUES (?,?,?,?)",
            (item.get("date"), sido, int(item.get("인허가실적", 0) or 0), now))
        count += 1
    conn.commit()
    conn.close()
    print(f"✅ 인허가 {count}건 저장 완료")

# ===== 착공 =====
def save_착공(start_dt, end_dt):
    items = fetch_molit(5386, 1, start_dt, end_dt)
    conn = sqlite3.connect("pf_data.db")
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    for item in items:
        if item.get("부문명") != "총계":
            continue
        if item.get("구  분") != "총계":
            continue
        sido = item.get("시도별", "")
        if not sido or sido == "전국":
            continue
        cur.execute("INSERT INTO 착공 (date, sido, value, updated_at) VALUES (?,?,?,?)",
            (item.get("date"), sido, int(item.get("착공실적", 0) or 0), now))
        count += 1
    conn.commit()
    conn.close()
    print(f"✅ 착공 {count}건 저장 완료")

# ===== 준공 =====
def save_준공(start_dt, end_dt):
    items = fetch_molit(5372, 1, start_dt, end_dt)
    conn = sqlite3.connect("pf_data.db")
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    for item in items:
        if item.get("부문명") != "총계":
            continue
        if item.get("구  분") != "총계":
            continue
        sido = item.get("시도별", "")
        if not sido or sido == "전국":
            continue
        cur.execute("INSERT INTO 준공 (date, sido, value, updated_at) VALUES (?,?,?,?)",
            (item.get("date"), sido, int(item.get("사용검사실적", 0) or 0), now))
        count += 1
    conn.commit()
    conn.close()
    print(f"✅ 준공 {count}건 저장 완료")

# ===== 인구 =====
def save_인구(start_dt, end_dt):
    url = "https://apis.data.go.kr/1741000/admmPpltnHhStus/selectAdmmPpltnHhStus"
    conn = sqlite3.connect("pf_data.db")
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0

    # 신코드 반영: 강원=5100000000, 전북=5200000000
    sido_codes = [
        ("1100000000", "서울특별시"),
        ("2600000000", "부산광역시"),
        ("2700000000", "대구광역시"),
        ("2800000000", "인천광역시"),
        ("2900000000", "광주광역시"),
        ("3000000000", "대전광역시"),
        ("3100000000", "울산광역시"),
        ("4100000000", "경기도"),
        ("5100000000", "강원특별자치도"),
        ("4300000000", "충청북도"),
        ("4400000000", "충청남도"),
        ("5200000000", "전북특별자치도"),
        ("4600000000", "전라남도"),
        ("4700000000", "경상북도"),
        ("4800000000", "경상남도"),
        ("5000000000", "제주특별자치도"),
    ]

    # 3개월씩 분할
    start = datetime.strptime(start_dt, "%Y%m")
    end = datetime.strptime(end_dt, "%Y%m")
    periods = []
    cur_start = start
    while cur_start <= end:
        cur_end = datetime(cur_start.year, cur_start.month, 1) + timedelta(days=89)
        if cur_end > end:
            cur_end = end
        periods.append((cur_start.strftime("%Y%m"), cur_end.strftime("%Y%m")))
        cur_start = datetime(cur_end.year, cur_end.month, 1) + timedelta(days=32)
        cur_start = datetime(cur_start.year, cur_start.month, 1)

    for admmCd, sido_name in sido_codes:
        print(f"  → {sido_name} 수집 중...")
        for fr, to in periods:
            params = {
                "serviceKey": DATA_KEY, "admmCd": admmCd,
                "srchFrYm": fr, "srchToYm": to,
                "lv": "2", "regSeCd": "1", "type": "json",
                "numOfRows": "900", "pageNo": "1"
            }
            try:
                res = requests.get(url, params=params, timeout=10)
                data = res.json()
                items = data.get("Response", {}).get("items", {})
                if not items or isinstance(items, str):
                    continue
                item_list = items.get("item", [])
                if isinstance(item_list, dict):
                    item_list = [item_list]
                for item in item_list:
                    sigungu = item.get("sggNm", "").strip()
                    sido = item.get("ctpvNm", "").strip()
                    if not sigungu or not sido:
                        continue
                    cur.execute("""INSERT INTO 인구 (date, sido, sigungu, pop, household, updated_at)
                        VALUES (?,?,?,?,?,?)""",
                        (item.get("statsYm"), sido, sigungu,
                         int(item.get("totNmprCnt", 0) or 0),
                         int(item.get("hhCnt", 0) or 0), now))
                    count += 1
            except Exception as e:
                print(f"    ⚠ 오류: {e}")
                continue

    # 세종 별도 처리 (lv=1로 호출하면 전국 시도 단위 데이터가 통째로 오므로,
    # 응답 안에서 실제로 세종에 해당하는 항목만 걸러내야 함)
    print(f"  → 세종특별자치시 수집 중...")
    for fr, to in periods:
        params = {
            "serviceKey": DATA_KEY, "admmCd": "3600000000",
            "srchFrYm": fr, "srchToYm": to,
            "lv": "1", "regSeCd": "1", "type": "json",
            "numOfRows": "50", "pageNo": "1"
        }
        try:
            res = requests.get(url, params=params, timeout=10)
            data = res.json()
            items = data.get("Response", {}).get("items", {})
            if not items or isinstance(items, str):
                continue
            item_list = items.get("item", [])
            if isinstance(item_list, dict):
                item_list = [item_list]
            for item in item_list:
                # lv=1 응답의 지역명은 sggNm 또는 ctpvNm에 들어있을 수 있으므로 둘 다 확인해서 세종만 필터링
                ctpv = item.get("ctpvNm", "").strip()
                sgg = item.get("sggNm", "").strip()
                if "세종" not in ctpv and "세종" not in sgg:
                    continue
                cur.execute("""INSERT INTO 인구 (date, sido, sigungu, pop, household, updated_at)
                    VALUES (?,?,?,?,?,?)""",
                    (item.get("statsYm"), "세종특별자치시", "세종시",
                     int(item.get("totNmprCnt", 0) or 0),
                     int(item.get("hhCnt", 0) or 0), now))
                count += 1
        except Exception as e:
            print(f"    ⚠ 세종 오류: {e}")
            continue

    conn.commit()
    conn.close()
    print(f"✅ 인구 {count}건 저장 완료")

# ===== 노후도 =====
# DT_1JU1520 테이블은 지역(C1)/연면적(C2)/주택종류(C3) 축만 있고,
# 건축연도는 itmId(항목) 쪽에 들어있음이 확인됨:
#   T000=주택_계, T070=2005~2009, T080=2000~2004, T090=1990~1999,
#   T100=1980~1989, T110=1979년 이전, T2010~T2024=해당 연도(개별)
# 지역(objL1)은 5자리 시군구 코드를 하나씩 넣어야 값이 나오므로,
# PublicDataReader 패키지로 전국 시군구 코드 목록을 받아와 순회 호출한다.
def save_노후도():
    url = "https://apis.data.go.kr/1240000/statisticsData/getStatisticsData"
    conn = sqlite3.connect("pf_data.db")
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0

    if not KOSIS_KEY:
        print("[ERROR] KOSIS_KEY가 .env 파일에 설정되어 있지 않습니다. KOSIS_KEY=... 를 .env에 추가해주세요.")
        conn.close()
        return

    try:
        import PublicDataReader as pdr
    except ImportError:
        print("[ERROR] PublicDataReader 패키지가 없습니다. `pip install PublicDataReader` 실행 후 다시 시도해주세요.")
        conn.close()
        return

    # 행정안전부 법정동코드가 아니라, 이 통계표(DT_1JU1520)가 실제로 쓰는
    # KOSIS 내부 지역코드를 메타정보 API로 직접 받아온다 (둘은 서로 다른 코드체계임)
    try:
        kosis_api = pdr.Kosis(KOSIS_KEY)
        meta_df = kosis_api.get_data(
            "통계표설명", "분류항목",
            orgId="101", tblId="DT_1JU1520",
        )
    except Exception as e:
        print(f"[ERROR] KOSIS 지역코드 목록 조회 실패(예외): {e}")
        conn.close()
        return

    if meta_df is None:
        print("[ERROR] KOSIS 지역코드 목록 조회 실패: 응답이 비어있습니다(None).")
        print("   -> KOSIS_KEY가 잘못되었거나 만료되었거나 일일 호출 한도를 초과했을 수 있습니다.")
        print("   -> https://kosis.kr/openapi/ 에서 키 상태를 확인해주세요.")
        conn.close()
        return

    sigungu_df = meta_df[meta_df["분류값ID"].astype(str).str.match(r"^\d{5}$")].drop_duplicates(subset=["분류값ID"])

    print(f"  → 전국 시군구 {len(sigungu_df)}개 노후도 수집 시작 (시간이 다소 걸릴 수 있음)...")

    for i, row in sigungu_df.iterrows():
        code5 = str(row["분류값ID"]).strip()
        sigungu_name = (row["분류값명"] or "").strip()
        if not sigungu_name:
            continue

        params = {
            "serviceKey": DATA_KEY, "pageNo": "1", "numOfRows": "30",
            "orgId": "101", "tblId": "DT_1JU1520",
            "objL1": code5, "objL2": "00", "objL3": "00",
            "itmId": "ALL", "prdSe": "Y", "newEstPrdCnt": "1", "format": "json"
        }
        try:
            res = requests.get(url, params=params, timeout=15)
            data = res.json()
            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            if isinstance(items, dict):
                items = [items]
            if not items:
                continue

            bucket = {"total": 0, "before_1990": 0, "y1990_2000": 0, "y2000_2010": 0, "after_2010": 0}
            year = ""
            for it in items:
                itm_id = it.get("ITM_ID", "")
                try:
                    val = int(it.get("DT", 0) or 0)
                except:
                    val = 0
                year = it.get("PRD_DE", year)
                if itm_id == "T000":
                    bucket["total"] = val
                elif itm_id in ("T100", "T110"):
                    bucket["before_1990"] += val
                elif itm_id == "T090":
                    bucket["y1990_2000"] += val
                elif itm_id in ("T070", "T080"):
                    bucket["y2000_2010"] += val
                elif itm_id.startswith("T20"):
                    bucket["after_2010"] += val

            cur.execute("""INSERT INTO 노후도
                (year, sigungu, built_before_1990, built_1990_2000,
                 built_2000_2010, built_after_2010, total, updated_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (year, sigungu_name, bucket["before_1990"], bucket["y1990_2000"],
                 bucket["y2000_2010"], bucket["after_2010"], bucket["total"], now))
            count += 1
        except Exception as e:
            print(f"    ⚠ {sigungu_name} 오류: {e}")
            continue

    conn.commit()
    conn.close()
    print(f"✅ 노후도 {count}건 저장 완료")

# ===== 청약경쟁률 =====
def save_청약경쟁률(start_dt, end_dt):
    url = "https://api.odcloud.kr/api/ApplyhomeStatSvc/v1/getAPTCmpetrtAreaStat"
    conn = sqlite3.connect("pf_data.db")
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0

    def to_float(val):
        try:
            return float(val)
        except:
            return 0.0

    def to_int(val):
        try:
            return int(val)
        except:
            return 0

    params = {
        "serviceKey": DATA_KEY, "page": "1", "perPage": "1000",
        "returnType": "json",
        "cond[STAT_DE::GTE]": start_dt,
        "cond[STAT_DE::LTE]": end_dt,
    }

    res = requests.get(url, params=params)
    data = res.json()
    items = data.get("data", [])

    for item in items:
        cur.execute("""INSERT INTO 청약경쟁률
            (date, region, supply_rate, special_rate, supply_cnt, req_cnt, updated_at)
            VALUES (?,?,?,?,?,?,?)""",
            (item.get("STAT_DE"), item.get("SUBSCRPT_AREA_CODE_NM"),
             to_float(item.get("SUPLY_CMPET_RATE", 0)),
             to_float(item.get("SPSPLY_CMPET_RATE", 0)),
             to_int(item.get("SUPLY_HSHLDCO", 0)),
             to_int(item.get("SUPLY_REQ_CNT", 0)), now))
        count += 1

    conn.commit()
    conn.close()
    print(f"✅ 청약경쟁률 {count}건 저장 완료")

# ===== 롤링 업데이트 (개별 지표, 최신 1개월 추가 + 최고령 1개월 삭제) =====
def probe_month(cfg, ym):
    """해당 지표의 특정 월(ym) 데이터가 실제로 공표되어 있는지 가볍게 확인만 한다 (저장 안 함)"""
    table = cfg["table"]
    try:
        if table in ("미분양", "인허가", "착공", "준공"):
            items = fetch_molit(cfg["form_id"], cfg["style_num"], ym, ym)
            return len(items) > 0
        elif table == "인구":
            # 서울(1100000000)을 대표로 확인 - 인구 통계는 전국 동시 공표라 대표성 있음
            url = "https://apis.data.go.kr/1741000/admmPpltnHhStus/selectAdmmPpltnHhStus"
            params = {
                "serviceKey": DATA_KEY, "admmCd": "1100000000",
                "srchFrYm": ym, "srchToYm": ym,
                "lv": "2", "regSeCd": "1", "type": "json",
                "numOfRows": "5", "pageNo": "1"
            }
            res = requests.get(url, params=params, timeout=10)
            data = res.json()
            items = data.get("Response", {}).get("items", {})
            if not items or isinstance(items, str):
                return False
            item_list = items.get("item", [])
            if isinstance(item_list, dict):
                item_list = [item_list]
            return len(item_list) > 0
        elif table == "청약경쟁률":
            url = "https://api.odcloud.kr/api/ApplyhomeStatSvc/v1/getAPTCmpetrtAreaStat"
            params = {
                "serviceKey": DATA_KEY, "page": "1", "perPage": "5",
                "returnType": "json",
                "cond[STAT_DE::GTE]": ym, "cond[STAT_DE::LTE]": ym + "31",
            }
            res = requests.get(url, params=params, timeout=10)
            data = res.json()
            return len(data.get("data", [])) > 0
    except Exception:
        return False
    return False

def find_latest_available_month(cfg, initial_guess, max_back=4):
    """initial_guess부터 시작해서 실제로 데이터가 있는 가장 최신월을 찾을 때까지 한 달씩 뒤로 물러난다.
    다 실패하면 initial_guess를 그대로 반환(최소한 화면에 뭔가는 보여주기 위함)"""
    d = datetime.strptime(initial_guess, "%Y%m")
    for _ in range(max_back + 1):
        candidate = d.strftime("%Y%m")
        if probe_month(cfg, candidate):
            return candidate
        d = datetime(d.year, d.month, 1) - timedelta(days=2)
        d = datetime(d.year, d.month, 1)
    return initial_guess

def get_expected_latest_month(cfg):
    """지표별 대략적인 공개 지연(lag_days)을 초기 추정치로 삼고, 실제 존재 여부를 확인해가며 보정한다"""
    now = datetime.now()
    initial = datetime(now.year, now.month, 1) - timedelta(days=cfg["lag_days"])
    return find_latest_available_month(cfg, initial.strftime("%Y%m"))

def rolling_update(cfg, keep_months=12):
    """실제 존재가 확인된 최신월 데이터가 DB에 없으면 수집해서 추가하고,
    keep_months개월을 초과하는 오래된 월은 삭제해 항상 최근 N개월 창을 유지한다."""
    table = cfg["table"]
    expected_ym = get_expected_latest_month(cfg)

    conn = sqlite3.connect("pf_data.db")
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE date=?", (expected_ym,))
    already = cur.fetchone()[0] > 0
    conn.close()

    if already:
        print(f"  → {table}: {expected_ym} 이미 최신 상태 (추가 수집 없음)")
    else:
        print(f"  → {table}: {expected_ym} 신규 수집 중...")
        cfg["save"](expected_ym, expected_ym)

    conn = sqlite3.connect("pf_data.db")
    cur = conn.cursor()
    cur.execute(f"SELECT DISTINCT date FROM {table} ORDER BY date DESC")
    months = [r[0] for r in cur.fetchall()]
    if len(months) > keep_months:
        old_months = months[keep_months:]
        for m in old_months:
            cur.execute(f"DELETE FROM {table} WHERE date=?", (m,))
        print(f"  → {table}: 오래된 {len(old_months)}개월치 삭제 ({', '.join(old_months)})")
    conn.commit()
    conn.close()

# 지표별 공개 지연 초기 추정치(lag_days) + MOLIT 지표는 probe에 필요한 form_id/style_num도 포함
ROLLING_CONFIG = {
    "미분양":      {"table": "미분양",      "save": save_미분양,      "lag_days": 30, "form_id": 2082, "style_num": 128},
    "인허가":      {"table": "인허가",      "save": save_인허가,      "lag_days": 30, "form_id": 1952, "style_num": 1},
    "착공":        {"table": "착공",        "save": save_착공,        "lag_days": 60, "form_id": 5386, "style_num": 1},
    "준공":        {"table": "준공",        "save": save_준공,        "lag_days": 60, "form_id": 5372, "style_num": 1},
    "인구":        {"table": "인구",        "save": save_인구,        "lag_days": 30},
    "청약경쟁률":  {"table": "청약경쟁률",  "save": save_청약경쟁률,  "lag_days": 30},
}

def get_indicator_status(indicator):
    """앱 화면의 상태 테이블용: DB 최신월, 실제 공표된 최신월, 최신여부를 반환"""
    if indicator == "노후도":
        conn = sqlite3.connect("pf_data.db")
        cur = conn.cursor()
        cur.execute("SELECT MAX(year) FROM 노후도")
        db_latest = cur.fetchone()[0]
        conn.close()
        return {"db_latest": db_latest, "expected": None, "is_current": None}

    cfg = ROLLING_CONFIG.get(indicator)
    if not cfg:
        return {"db_latest": None, "expected": None, "is_current": None}
    conn = sqlite3.connect("pf_data.db")
    cur = conn.cursor()
    cur.execute(f"SELECT MAX(date) FROM {cfg['table']}")
    db_latest = cur.fetchone()[0]
    conn.close()
    expected = get_expected_latest_month(cfg)
    return {"db_latest": db_latest, "expected": expected, "is_current": (db_latest == expected)}

def run_rolling_update(indicator):
    if indicator == "노후도":
        save_노후도()
        print("✅ 노후도 전체 갱신 완료")
        return
    cfg = ROLLING_CONFIG.get(indicator)
    if not cfg:
        print(f"⚠ 알 수 없는 지표: {indicator}")
        return
    rolling_update(cfg)
    print(f"✅ {indicator} 롤링 업데이트 완료")

# ===== 메인 =====
if __name__ == "__main__":
    _missing = [k for k, v in [("MOLIT_KEY", MOLIT_KEY), ("DATA_KEY", DATA_KEY)] if not v]
    if _missing:
        print(f"[ERROR] .env(또는 Secrets)에 다음 키가 없습니다: {', '.join(_missing)}")
        print("        .env 파일에 MOLIT_KEY=..., DATA_KEY=... 를 추가해주세요.")
        sys.exit(1)

    if len(sys.argv) > 2 and sys.argv[1] == "--update":
        run_rolling_update(sys.argv[2])
        sys.exit(0)

    print("🚀 DB 초기화 및 데이터 수집 시작...")

    if os.path.exists("pf_data.db"):
        os.remove("pf_data.db")

    init_db()

    start_dt1, end_dt1 = get_month_range(12)
    start_dt2, end_dt2 = get_month_range_stable(12)

    print(f"📅 미분양/인허가/인구/청약 기간: {start_dt1} ~ {end_dt1}")
    print(f"📅 착공/준공 기간:               {start_dt2} ~ {end_dt2}")

    save_미분양(start_dt1, end_dt1)
    save_인허가(start_dt1, end_dt1)
    save_착공(start_dt2, end_dt2)
    save_준공(start_dt2, end_dt2)
    save_인구(start_dt1, end_dt1)
    save_노후도()
    save_청약경쟁률(start_dt1, end_dt1)

    print("🎉 전체 완료!")
