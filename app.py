import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone, date, time
from streamlit_js_eval import get_geolocation

# ページ基本設定
st.set_page_config(page_title="カフェ混雑ナビ", page_icon="☕", layout="wide")

st.title("☕ 未来予測 ＆ 目的別 カフェ穴場ナビ")
st.caption("Googleマップでは分からない「目的 × 天候 × 未来の状況」から最適な穴場を判定！")

st.divider()

JST = timezone(timedelta(hours=9), 'JST')

# 大手チェーン・判定用のキーワード辞書
CHAIN_PATTERNS = {
    "quick": ["ドトール", "ベローチェ", "サンマルク", "プロント", "Doutor", "Veloce"],
    "station_heavy": ["スターバックス", "Starbucks", "タリーズ", "Tully's"],
    "stay": ["コメダ", "Komeda", "星乃珈琲", "上島珈琲", "むさしの森"]
}

# フォールバック用の標準データ
DEFAULT_CAFE_TEMPLATES = [
    {"name": "スターバックス コーヒー (駅前店)", "type": "人気大手チェーン", "is_station": True, "is_far": False, "turnover_penalty": 10, "advice": "駅前でアクセス抜群ですが満席になりやすいです。テイクアウト推奨。"},
    {"name": "ドトールコーヒーショップ (駅構内・改札横店)", "type": "高回転・セルフカフェ", "is_station": True, "is_far": False, "turnover_penalty": -10, "advice": "回転率が高いため、少し待てば席が確保できる可能性が高いです。"},
    {"name": "上島珈琲店 / プロント (大通り沿い店)", "type": "ボックス・滞在型カフェ", "is_station": False, "is_far": False, "turnover_penalty": 10, "advice": "電源席が多く作業に向いていますが、滞在時間が長くなりがちです。"},
    {"name": "コメダ珈琲店 (大通り・郊外店)", "type": "ボックス・滞在型カフェ", "is_station": False, "is_far": True, "turnover_penalty": 20, "advice": "席が広く快適ですが、混雑時は発券機での待ち時間が発生します。"},
    {"name": "ベローチェ (裏路地・オフィス街店)", "type": "高回転・セルフカフェ", "is_station": False, "is_far": False, "turnover_penalty": -15, "advice": "席数が多く裏路地にあるため、ピーク時でも比較的空いている穴場です。"}
]

# ==========================================
# 1. 位置情報 ＆ ジオコーディング
# ==========================================
def get_coordinates(location_name):
    """ OpenStreetMap (Nominatim) で地名から座標を取得 """
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={location_name}&format=json&limit=1&countrycodes=jp"
        headers = {"User-Agent": "CafeCongestionApp/4.0 (contact: test@example.com)"}
        res = requests.get(url, headers=headers, timeout=5).json()
        if res:
            return float(res[0]["lat"]), float(res[0]["lon"]), res[0]["display_name"]
    except Exception:
        pass
    # デフォルト (東陽町)
    return 35.6691, 139.8166, location_name

# ==========================================
# 2. OpenStreetMapから実カフェデータを動的取得 (フォールバック付き)
# ==========================================
@st.cache_data(ttl=1800)
def fetch_real_cafes(lat, lon, area_label):
    headers = {"User-Agent": "CafeCongestionApp/4.0 (contact: test@example.com)"}
    overpass_url = "https://overpass-api.de/api/interpreter"
    
    query = f"""
    [out:json][timeout:10];
    (
      node["amenity"="cafe"](around:1500,{lat},{lon});
      way["amenity"="cafe"](around:1500,{lat},{lon});
    );
    out body 20;
    """
    
    parsed_cafes = []
    try:
        res = requests.post(overpass_url, data={"data": query}, headers=headers, timeout=8)
        if res.status_code == 200:
            data = res.json()
            for item in data.get("elements", []):
                tags = item.get("tags", {})
                name = tags.get("name")
                if not name:
                    continue
                    
                addr = tags.get("addr:street", "") or tags.get("addr:suburb", "") or f"{area_label}周辺"
                
                is_station = any(k in name for k in CHAIN_PATTERNS["station_heavy"])
                is_quick = any(k in name for k in CHAIN_PATTERNS["quick"])
                is_stay = any(k in name for k in CHAIN_PATTERNS["stay"])
                
                turnover_penalty = -10 if is_quick else (15 if is_stay else 0)
                
                if is_stay:
                    c_type = "ボックス・滞在型カフェ"
                elif is_quick:
                    c_type = "高回転・セルフカフェ"
                elif is_station:
                    c_type = "人気大手チェーン"
                else:
                    c_type = "個人系・ローカルカフェ"

                parsed_cafes.append({
                    "name": name,
                    "address": addr,
                    "type": c_type,
                    "dist": "周辺エリア",
                    "open_hour": 7, "close_hour": 22,
                    "is_station": is_station,
                    "is_far": not is_station and not is_quick,
                    "features": {
                        "pc": not is_quick,
                        "chat": True,
                        "read": not is_station,
                        "quick": is_quick or is_station
                    },
                    "turnover_penalty": turnover_penalty,
                    "advice": "混雑時は近隣の個人店や徒歩数分の店舗へ移動するとスムーズです。" if is_station else "比較的マイペースに利用しやすい店舗です。"
                })
    except Exception:
        parsed_cafes = []

    # API取得が失敗または0件時はフォールバックデータを生成
    if not parsed_cafes:
        for tmpl in DEFAULT_CAFE_TEMPLATES:
            parsed_cafes.append({
                "name": tmpl["name"],
                "address": f"{area_label} エリア",
                "type": tmpl["type"],
                "dist": "周辺エリア",
                "open_hour": 7, "close_hour": 22,
                "is_station": tmpl["is_station"],
                "is_far": tmpl["is_far"],
                "features": {"pc": True, "chat": True, "read": True, "quick": True},
                "turnover_penalty": tmpl["turnover_penalty"],
                "advice": tmpl["advice"]
            })
            
    return parsed_cafes

# ==========================================
# 3. サイドバー・条件設定 ＆ 位置情報処理
# ==========================================
st.sidebar.header("⚙️ 条件・検索設定")
mode = st.sidebar.radio("📍 検索モードを選択", ["今すぐ探す（現在地GPS）", "未来・指定場所で探す"])

target_location = ""
target_datetime = None
lat, lon = 35.6691, 139.8166  # デフォルト（東陽町）

if mode == "今すぐ探す（現在地GPS）":
    st.sidebar.caption("※ブラウザの位置情報アクセス許可が必要です")
    loc = get_geolocation()
    
    if loc and 'coords' in loc:
        lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
        st.sidebar.success(f"📍 GPS取得成功!\n(緯度:{lat:.4f} / 経度:{lon:.4f})")
        target_location = "現在地周辺"
    else:
        st.sidebar.info("💡 GPS未取得時は、下のフォームに地名を入力してください。")
        fallback_input = st.sidebar.text_input("検索エリア・駅名を入力", value="東陽町")
        target_location = fallback_input
        lat, lon, _ = get_coordinates(fallback_input)
        
    target_datetime = datetime.now(JST)

else:
    target_location = st.sidebar.text_input("検索エリア・駅名を入力", value="東陽町")
    selected_date = st.sidebar.date_input("日付を選択", date.today())
    selected_time = st.sidebar.time_input("時間を選択", time(15, 0))
    target_datetime = datetime.combine(selected_date, selected_time).replace(tzinfo=JST)
    
    if target_location:
        lat, lon, _ = get_coordinates(target_location)

# ==========================================
# 4. リアルタイム天気取得
# ==========================================
is_rain = False
weather_label = "晴れ/曇り ☀️"

if mode == "今すぐ探す（現在地GPS）":
    try:
        w_res = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true", timeout=5).json()
        w_code = w_res.get("current_weather", {}).get("weathercode", 0)
        if w_code >= 51:
            is_rain = True
            weather_label = "雨・悪天候 🌧️"
    except:
        pass
else:
    is_rain = st.sidebar.checkbox("🌧️ 天気：雨としてシミュレーション")

is_event = st.sidebar.checkbox("🎪 周辺で大規模イベント開催中", value=False)

# ==========================================
# 5. 利用目的設定
# ==========================================
st.sidebar.subheader("🎯 カフェ利用の目的（複数選択可）")
use_pc = st.sidebar.checkbox("💻 PC作業・仕事（コンセント・Wi-Fi重視）")
use_chat = st.sidebar.checkbox("🗣️ 友達と談笑・おしゃべり（話しやすさ・席数重視）")
use_read = st.sidebar.checkbox("📖 読書・勉強（静かさ・落ち着き重視）")
use_quick = st.sidebar.checkbox("⚡️ スキマ時間のサクッと休憩（回転率・手軽さ重視）")

# 時間帯判定スコア
weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
weekday_str = weekday_names[target_datetime.weekday()]
hour = target_datetime.hour
is_weekend = target_datetime.weekday() >= 5

time_score = 0
if is_weekend:
    time_score = 35 if 13 <= hour <= 17 else (20 if 11 <= hour <= 12 or 18 <= hour <= 20 else 5)
else:
    time_score = 25 if 8 <= hour <= 9 else (30 if 12 <= hour <= 13 else (20 if 14 <= hour <= 17 else 0))

# ヘッダー表示
c1, c2, c3 = st.columns(3)
c1.metric("対象エリア", target_location)
c2.metric("対象日時", f"{target_datetime.strftime('%m/%d')}({weekday_str}) {target_datetime.strftime('%H:%M')}")
c3.metric("予想天候", weather_label if mode == "今すぐ探す（現在地GPS）" else ("雨 🌧️" if is_rain else "晴れ ☀️"))

st.divider()

# ==========================================
# 6. カフェ穴場判定表示
# ==========================================
st.header("🏪 カフェ穴場判定 ＆ 立ち回りナビ")

cafes = fetch_real_cafes(lat, lon, target_location)

for cafe in cafes:
    current_target_hour = target_datetime.hour
    is_open = cafe["open_hour"] <= current_target_hour < cafe["close_hour"]

    score = 15 + time_score
    if is_rain:
        if cafe["is_station"]: score += 30
        elif cafe["is_far"]: score -= 20
    else:
        if cafe["is_station"]: score += 15
    
    score += cafe["turnover_penalty"]
    if is_event: score += 25
    final_score = max(10, min(99, score))

    match_reasons = []
    if use_pc and cafe["features"]["pc"]: match_reasons.append("💻 PC作業可")
    if use_chat and cafe["features"]["chat"]: match_reasons.append("🗣️ おしゃべり可")
    if use_read and cafe["features"]["read"]: match_reasons.append("📖 読書・勉強向")
    if use_quick and cafe["features"]["quick"]: match_reasons.append("⚡️ 高回転・短時間")

    with st.container(border=True):
        col1, col2, col3 = st.columns([2.5, 1.5, 1])

        with col1:
            st.markdown(f"**☕ {cafe['name']}** (`{cafe['type']}`)")
            st.caption(f"📍 {cafe['address']} | 🕒 {cafe['open_hour']}:00〜{cafe['close_hour']}:00")
            st.caption(f"💡 {cafe['advice']}")

        with col2:
            if match_reasons:
                st.write(" ".join([f"`{m}`" for m in match_reasons]))
            else:
                st.caption("目的との一致条件なし")

        with col3:
            if not is_open:
                st.error("🔒 営業時間外")
            elif final_score >= 70:
                st.error(f"混雑度: **{final_score}%**")
            elif final_score >= 40:
                st.warning(f"混雑度: **{final_score}%**")
            else:
                st.success(f"混雑度: **{final_score}%**")

st.divider()

# ==========================================
# 7. 地図表示 (Google Maps Embedded)
# ==========================================
st.header("🗺️ 周辺マップ")

st.components.v1.html(
    f"""
    <iframe 
        width="100%" 
        height="300" 
        frameborder="0" 
        scrolling="no" 
        marginheight="0" 
        marginwidth="0" 
        src="https://maps.google.com/maps?q={lat},{lon}&z=15&output=embed">
    </iframe>
    """,
    height=320
)
