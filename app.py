"""
カフェ最適解ナビ ＆ 混雑予測（実データ版）

設計方針
  - 店名・住所・座標・営業時間は「外部データソースから取得した実在情報」のみを表示する。
    取得できなかった項目は捏造せず「情報なし」と明示する。
  - データ取得層（geocode / fetch_cafes）をUIから分離。
    将来 Google Places API に差し替える場合は、この2関数の中身だけ交換すればよい。
  - 時刻は常に JST。天気は「検索したエリアの座標」で取得する（東京固定にしない）。

データ出典: © OpenStreetMap contributors (ODbL) / Open-Meteo
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st

# ==========================================================
# 定数
# ==========================================================
JST = timezone(timedelta(hours=9), "JST")
USER_AGENT = "cafe-navi/1.0 (contact: your-mail@example.com)"  # ←自分の連絡先に変更推奨

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

DAY_IDX = {"Mo": 0, "Tu": 1, "We": 2, "Th": 3, "Fr": 4, "Sa": 5, "Su": 6}

# OSMに営業時間が入っていない場合の「チェーン標準値（参考）」
# 実データではないことをUI側で必ず明示する
CHAIN_PROFILES = [
    # (名前に含まれるキーワード, 表示名, 開店, 閉店, 性格, 回転の速さ係数)
    (("スターバックス", "STARBUCKS", "Starbucks"), "スターバックス", 7, 22, "作業向き（電源・Wi-Fi）", 1.10),
    (("ドトール", "DOUTOR"), "ドトール", 7, 21, "短時間休憩・回転が速い", 0.85),
    (("コメダ", "Komeda"), "コメダ珈琲店", 7, 23, "長居向き・席が広い", 1.15),
    (("タリーズ", "TULLY"), "タリーズ", 7, 21, "作業向き", 1.05),
    (("ベローチェ", "VELOCE"), "カフェ・ベローチェ", 7, 22, "安価・回転が速い", 0.85),
    (("サンマルク", "ST.MARC", "St. Marc"), "サンマルクカフェ", 7, 21, "短時間休憩", 0.90),
    (("エクセルシオール", "EXCELSIOR"), "エクセルシオール", 7, 21, "作業向き", 1.00),
    (("星乃", "星乃珈琲"), "星乃珈琲店", 8, 22, "長居向き", 1.10),
    (("プロント", "PRONTO"), "プロント", 7, 22, "夜はバー営業", 0.95),
    (("上島", "上島珈琲"), "上島珈琲店", 8, 21, "落ち着いた雰囲気", 1.00),
    (("珈琲館",), "珈琲館", 8, 21, "落ち着いた雰囲気", 1.00),
    (("マクドナルド", "McDonald"), "マクドナルド", 7, 23, "安価・騒がしめ", 0.80),
]


# ==========================================================
# ユーティリティ
# ==========================================================
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """2点間の距離（メートル）"""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def match_chain(name: str):
    """店名からチェーンを推定。該当なしなら None"""
    for keys, label, oh, ch, character, turnover in CHAIN_PROFILES:
        if any(k in name for k in keys):
            return {
                "label": label,
                "open_hour": oh,
                "close_hour": ch,
                "character": character,
                "turnover": turnover,
            }
    return None


# ---------- OSM opening_hours の簡易パーサ ----------
def _days_from_spec(spec: str) -> set[int]:
    days: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = a.strip(), b.strip()
            if a in DAY_IDX and b in DAY_IDX:
                i, j = DAY_IDX[a], DAY_IDX[b]
                k = i
                while True:
                    days.add(k)
                    if k == j:
                        break
                    k = (k + 1) % 7
        elif part in DAY_IDX:
            days.add(DAY_IDX[part])
    return days


def parse_opening_hours(oh: str | None, now: datetime):
    """
    戻り値: (is_open: bool|None, 今日の営業時間表示: str|None)
    解釈できない書式は (None, 原文) を返す。推測はしない。
    """
    if not oh:
        return None, None
    oh = oh.strip()
    if oh in ("24/7", "Mo-Su 00:00-24:00"):
        return True, "24時間営業"

    wd = now.weekday()
    mins_now = now.hour * 60 + now.minute
    todays_ranges: list[tuple[int, int]] = []
    understood = False

    for rule in oh.split(";"):
        rule = rule.strip()
        if not rule:
            continue
        if "PH" in rule and "off" in rule:
            continue

        m = re.search(r"\d{1,2}:\d{2}", rule)
        day_spec = rule[: m.start()].strip() if m else rule.strip()

        if day_spec and not any(d in day_spec for d in DAY_IDX):
            # Su-Sa 以外の表記（"Jan-Mar" 等）は解釈しない
            if day_spec.lower() not in ("", "open"):
                continue
        days = _days_from_spec(day_spec) if day_spec else set(range(7))
        if not days:
            days = set(range(7))
        if wd not in days:
            understood = True
            continue

        for t in re.finditer(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", rule):
            understood = True
            o = int(t.group(1)) * 60 + int(t.group(2))
            c = int(t.group(3)) * 60 + int(t.group(4))
            todays_ranges.append((o, c))

    if not understood:
        return None, oh
    if not todays_ranges:
        return False, "本日定休"

    is_open = False
    for o, c in todays_ranges:
        if c <= o:  # 日をまたぐ
            if mins_now >= o or mins_now < c:
                is_open = True
        elif o <= mins_now < c:
            is_open = True

    disp = " / ".join(f"{o // 60:02d}:{o % 60:02d}〜{c // 60:02d}:{c % 60:02d}" for o, c in todays_ranges)
    return is_open, disp


# ==========================================================
# データ取得層（ここを差し替えれば Google Places に移行可能）
# ==========================================================
@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def geocode(query: str):
    """エリア名 → (lat, lon, 正式名称)。失敗時 None。"""
    candidates = [query, f"{query}駅", f"{query} 日本"]
    for q in candidates:
        try:
            res = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": q,
                    "format": "jsonv2",
                    "limit": 1,
                    "countrycodes": "jp",
                    "accept-language": "ja",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=8,
            )
            data = res.json()
            if data:
                hit = data[0]
                return float(hit["lat"]), float(hit["lon"]), hit.get("display_name", q)
        except Exception:
            continue
    return None


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def reverse_geocode(lat: float, lon: float) -> str:
    try:
        res = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "jsonv2", "accept-language": "ja"},
            headers={"User-Agent": USER_AGENT},
            timeout=8,
        ).json()
        addr = res.get("address", {})
        for key in ("neighbourhood", "quarter", "suburb", "city_district", "town", "city"):
            if addr.get(key):
                return addr[key]
        return res.get("display_name", "現在地")
    except Exception:
        return "現在地"


@st.cache_data(ttl=60 * 30, show_spinner=False)
def fetch_cafes(lat: float, lon: float, radius_m: int):
    """
    OpenStreetMap から実在するカフェ／コーヒー店を取得する。
    名前のないPOIは除外（ダミー表示を避けるため）。
    """
    q = f"""
    [out:json][timeout:25];
    (
      node["amenity"="cafe"]["name"](around:{radius_m},{lat},{lon});
      way["amenity"="cafe"]["name"](around:{radius_m},{lat},{lon});
      node["amenity"="fast_food"]["cuisine"="coffee_shop"]["name"](around:{radius_m},{lat},{lon});
      way["amenity"="fast_food"]["cuisine"="coffee_shop"]["name"](around:{radius_m},{lat},{lon});
    );
    out center tags 120;
    """
    last_err = None
    for url in OVERPASS_ENDPOINTS:
        try:
            res = requests.post(url, data={"data": q}, headers={"User-Agent": USER_AGENT}, timeout=40)
            res.raise_for_status()
            elements = res.json().get("elements", [])
            break
        except Exception as e:  # 次のミラーへ
            last_err = e
            elements = None
    if elements is None:
        raise RuntimeError(f"Overpass API に接続できませんでした: {last_err}")

    cafes = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name:ja") or tags.get("name")
        if not name:
            continue
        if el["type"] == "node":
            plat, plon = el.get("lat"), el.get("lon")
        else:
            center = el.get("center", {})
            plat, plon = center.get("lat"), center.get("lon")
        if plat is None or plon is None:
            continue

        addr_parts = [
            tags.get("addr:province") or tags.get("addr:state", ""),
            tags.get("addr:city", ""),
            tags.get("addr:suburb", ""),
            tags.get("addr:neighbourhood", ""),
            tags.get("addr:block_number", ""),
            tags.get("addr:housenumber", ""),
        ]
        address = "".join(p for p in addr_parts if p)

        cafes.append(
            {
                "osm_id": f"{el['type']}/{el['id']}",
                "name": name,
                "brand": tags.get("brand"),
                "address": address,
                "lat": plat,
                "lon": plon,
                "opening_hours": tags.get("opening_hours"),
                "internet": tags.get("internet_access"),
                "outlets": tags.get("service:electricity") or tags.get("power_supply"),
                "smoking": tags.get("smoking"),
                "takeaway": tags.get("takeaway"),
                "distance_m": haversine_m(lat, lon, plat, plon),
            }
        )

    cafes.sort(key=lambda c: c["distance_m"])
    return cafes


@st.cache_data(ttl=60 * 10, show_spinner=False)
def fetch_weather(lat: float, lon: float):
    """検索地点の現在天候。東京固定にしないことが重要。"""
    try:
        res = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon, "current_weather": "true", "timezone": "Asia/Tokyo"},
            timeout=8,
        ).json()
        cw = res.get("current_weather", {})
        code = int(cw.get("weathercode", 0))
        temp = float(cw.get("temperature", 20.0))
        if code >= 71:
            text, icon = "雪", "🌨️"
        elif code >= 51:
            text, icon = "雨", "🌧️"
        elif code in (1, 2, 3, 45, 48):
            text, icon = "曇り", "☁️"
        else:
            text, icon = "晴れ", "☀️"
        return {"ok": True, "temp": temp, "code": code, "text": f"{text} {icon}"}
    except Exception:
        return {"ok": False, "temp": None, "code": 0, "text": "取得失敗"}


# ==========================================================
# 混雑度の推定（実測値ではなく統計的推定であることを明示する）
# ==========================================================
def estimate_crowd(cafe: dict, now: datetime, weather: dict, is_weekend: bool):
    h = now.hour + now.minute / 60
    reasons: list[str] = []

    # 時間帯カーブ
    if is_weekend:
        curve = [(7, 20), (10, 45), (12, 70), (14, 78), (16, 70), (18, 50), (21, 30), (24, 15)]
        reasons.append("休日は日中（12〜17時）に来客が集中する傾向")
    else:
        curve = [(7, 30), (9, 40), (12, 72), (13, 68), (15, 55), (17, 45), (19, 40), (22, 20), (24, 12)]
        reasons.append("平日はランチ帯（12〜13時）がピーク")

    score = curve[-1][1]
    prev_h, prev_v = 0, curve[0][1]
    for ch, cv in curve:
        if h <= ch:
            ratio = (h - prev_h) / max(ch - prev_h, 0.001)
            score = prev_v + (cv - prev_v) * ratio
            break
        prev_h, prev_v = ch, cv

    # 駅／中心からの距離（近いほど混む）
    d = cafe["distance_m"]
    if d <= 150:
        score += 12
        reasons.append("エリア中心から至近（人が最初に入る店になりやすい）")
    elif d <= 400:
        score += 5
    elif d >= 800:
        score -= 10
        reasons.append("中心から離れており、流入が少なめ")

    # 天候
    if weather["ok"]:
        t = weather["temp"]
        if weather["code"] >= 51 and d <= 300:
            score += 18
            reasons.append("雨天＋中心至近のため、雨宿り需要で混みやすい")
        elif weather["code"] >= 51:
            score -= 5
            reasons.append("雨天だが距離があるため、あえて歩く人は少ない")
        if t is not None and t >= 30 and d <= 300:
            score += 12
            reasons.append(f"猛暑（{t:.0f}℃）で避暑需要が中心部に集中")
        elif t is not None and t <= 5 and d <= 300:
            score += 10
            reasons.append(f"低温（{t:.0f}℃）で駅近に人が集中")

    # チェーン特性（回転の速さ）
    chain = match_chain(cafe["name"])
    if chain:
        score *= chain["turnover"]
        if chain["turnover"] <= 0.9:
            reasons.append(f"{chain['label']}は回転が速く、満席でも待ち時間が短い")
        elif chain["turnover"] >= 1.1:
            reasons.append(f"{chain['label']}は長居する客が多く、席が埋まりやすい")
    else:
        score -= 8
        reasons.append("チェーン以外の個人店のため、来客が分散しやすい（穴場候補）")

    return int(max(8, min(97, round(score)))), reasons


# ==========================================================
# UI
# ==========================================================
st.set_page_config(page_title="カフェ最適解ナビ", page_icon="☕", layout="centered")

now = datetime.now(JST)
is_weekend = now.weekday() >= 5
WD = ["月", "火", "水", "木", "金", "土", "日"][now.weekday()]

st.title("☕ カフェ最適解ナビ")
st.caption("入力したエリアの**実在する**カフェをOpenStreetMapから取得し、JST時刻・現地の天候から混雑を推定します。")

# ---- 場所の指定 ----
mode = st.radio("場所の指定", ["✏️ 駅名・エリア名で検索", "📍 現在地（GPS）"], horizontal=True)

center = None  # (lat, lon, 表示名)

if mode.startswith("✏️"):
    col_a, col_b = st.columns([3, 1])
    area = col_a.text_input("駅名・エリア名", value="東陽町", placeholder="例：東陽町、札幌駅、梅田、博多、仙台")
    radius = col_b.selectbox("検索範囲", [300, 500, 800, 1200], index=1, format_func=lambda x: f"{x}m")
    if area.strip():
        g = geocode(area.strip())
        if g:
            center = (g[0], g[1], area.strip())
        else:
            st.error(f"「{area}」の位置を特定できませんでした。表記を変えるか、市区町村名を足してみてください（例：「東陽町 江東区」）。")
else:
    radius = st.selectbox("検索範囲", [300, 500, 800, 1200], index=1, format_func=lambda x: f"{x}m")
    try:
        from streamlit_js_eval import get_geolocation

        loc = get_geolocation()
    except Exception:
        loc = None
        st.warning("位置情報コンポーネントを読み込めませんでした。`streamlit-js-eval` がインストールされているか確認してください。")

    if loc and "coords" in loc:
        lat, lon = loc["coords"]["latitude"], loc["coords"]["longitude"]
        center = (lat, lon, reverse_geocode(lat, lon))
    else:
        st.info("ブラウザの位置情報ダイアログで「許可」を選択してください。取得できない場合は駅名検索をご利用ください。")

if center is None:
    st.stop()

lat, lon, place_label = center
weather = fetch_weather(lat, lon)

# ---- 現在のコンテキスト ----
c1, c2, c3 = st.columns(3)
c1.metric("現在時刻 (JST)", now.strftime("%H:%M"), f"{WD}曜日・{'休日' if is_weekend else '平日'}")
c2.metric("気温", f"{weather['temp']:.1f} ℃" if weather["ok"] else "—")
c3.metric("天候", weather["text"])
st.caption(f"📍 検索中心: **{place_label}**（{lat:.4f}, {lon:.4f}） / 半径 {radius}m")

# ---- 取得 ----
try:
    with st.spinner("実在するカフェを検索中…"):
        cafes = fetch_cafes(lat, lon, radius)
except Exception as e:
    st.error(f"店舗データの取得に失敗しました。時間をおいて再試行してください。\n\n詳細: {e}")
    st.stop()

if not cafes:
    st.warning(f"半径{radius}m以内に登録済みのカフェが見つかりませんでした。検索範囲を広げてみてください。")
    st.stop()

# ---- フィルタ ----
f1, f2 = st.columns([1, 1])
only_open = f1.checkbox("営業中のみ表示", value=True)
sort_key = f2.selectbox("並び順", ["空いている順", "近い順"])

rows = []
for cafe in cafes[:40]:
    is_open, oh_disp = parse_opening_hours(cafe["opening_hours"], now)
    source = "実データ"
    if is_open is None:
        chain = match_chain(cafe["name"])
        if chain:
            is_open = chain["open_hour"] <= now.hour < chain["close_hour"]
            oh_disp = f"{chain['open_hour']:02d}:00〜{chain['close_hour']:02d}:00"
            source = "チェーン標準（参考値）"
        else:
            source = "情報なし"
    crowd, reasons = estimate_crowd(cafe, now, weather, is_weekend)
    rows.append({**cafe, "is_open": is_open, "oh_disp": oh_disp, "oh_source": source, "crowd": crowd, "reasons": reasons})

if only_open:
    rows = [r for r in rows if r["is_open"] is not False]
rows.sort(key=lambda r: (r["crowd"], r["distance_m"]) if sort_key == "空いている順" else (r["distance_m"],))

if not rows:
    st.warning("条件に合う店舗がありません。「営業中のみ表示」を外すか、範囲を広げてください。")
    st.stop()

st.markdown(f"**{len(rows)}件**（{'空いている順' if sort_key == '空いている順' else '近い順'}）")

# ---- 一覧（コンパクト表示 + 詳細は展開） ----
for r in rows[:20]:
    walk = max(1, round(r["distance_m"] / 80))
    if r["is_open"] is False:
        badge = "🔴 営業時間外"
    elif r["crowd"] >= 70:
        badge = f"🔴 混雑 {r['crowd']}%"
    elif r["crowd"] >= 45:
        badge = f"🟡 やや混雑 {r['crowd']}%"
    else:
        badge = f"🟢 空席あり {r['crowd']}%"

    chain = match_chain(r["name"])
    tag = chain["character"] if chain else "個人店・独立系"

    with st.container(border=True):
        left, right = st.columns([3, 1])
        left.markdown(
            f"**{r['name']}**  \n"
            f"<span style='color:gray;font-size:0.85em'>"
            f"徒歩{walk}分 ({int(r['distance_m'])}m) ／ {r['oh_disp'] or '営業時間 情報なし'} ／ {tag}"
            f"</span>",
            unsafe_allow_html=True,
        )
        right.markdown(f"**{badge}**")

        with st.expander("詳細"):
            st.write(f"住所: {r['address'] or '情報なし'}")
            st.write(f"営業時間: {r['oh_disp'] or '情報なし'}（出典: {r['oh_source']}）")
            extras = []
            if r["internet"] in ("wlan", "yes"):
                extras.append("Wi-Fiあり")
            if r["outlets"] in ("yes", "socket"):
                extras.append("電源あり")
            if r["smoking"] == "no":
                extras.append("禁煙")
            st.write("設備: " + ("／".join(extras) if extras else "情報なし"))
            st.markdown("**混雑推定の根拠:**")
            for reason in r["reasons"]:
                st.write(f"- {reason}")
            st.markdown(
                f"[Googleマップで開く](https://www.google.com/maps/search/?api=1&query="
                f"{r['lat']},{r['lon']}) ／ "
                f"[OSMで確認](https://www.openstreetmap.org/{r['osm_id']})"
            )

st.divider()
st.caption(
    "※ 混雑度は実測値ではなく、時間帯・曜日・現地天候・立地・業態から算出した**推定値**です。"
    "実測の混雑データが必要な場合は Google Places の Popular Times 系データ、"
    "または店舗側からの提供が必要になります。"
)
st.caption("店舗データ: © OpenStreetMap contributors (ODbL) ／ 天候: Open-Meteo ／ 地名: Nominatim")
