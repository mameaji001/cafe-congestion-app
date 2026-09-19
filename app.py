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

# ==========================================
# 1. 位置情報 ＆ ジオコーディング
# ==========================================
def get_coordinates(location_name):
    """ OpenStreetMap (Nominatim) で地名から座標を取得 """
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={location_name}&format=json&limit=1&countrycodes=jp"
        headers = {"User-Agent": "CafeCongestionApp/2.0 (contact: test@example.com)"}
        res = requests.get(url, headers=headers, timeout=5).json()
        if res:
            return float(res[0]["lat"]), float(res[0]["lon"]), res[0]["display_name"]
    except Exception:
        pass
    # デフォルト (東陽町)
    return 35.6691, 139.8166, location_name

# ==========================================
# 2. OpenStreetMapから実カフェデータを動的取得
# ==========================================
@st.cache_data(ttl=1800)  # 30分間キャッシュ
def fetch_real_cafes(lat, lon):
    """ Overpass API を使って現在地/指定座標の周辺700mにあるカフェを動的に取得 """
    headers = {"User-Agent": "CafeCongestionApp/2.0 (contact: test@example.com)"}
    overpass_url = "https://overpass-api.de/api/interpreter"
    
    query = f"""
    [out:json][timeout:10];
    (
      node["amenity"="cafe"](around:700,{lat},{lon});
      way["amenity"="cafe"](around:700,{lat},{lon});
    );
    out body 20;
    """
    try:
        res = requests.post(overpass_url, data={"data": query}, headers=headers, timeout=10)
        if res.status_code != 200:
            return []
        data = res.json()
        
        parsed_cafes = []
        for item in data.get("elements", []):
            tags = item.get("tags", {})
            name = tags.get("name")
            if not name:
                continue
                
            addr = tags.get("addr:street", "") or tags.get("addr:suburb", "") or "周辺エリア"
            
            # 店舗名から属性を簡易自動判定
            is_station = any(k in name for k in CHAIN_PATTERNS["station_heavy"])
            is_quick = any(k in name for k in CHAIN_PATTERNS["quick"])
            is_stay = any(k in name for k in CHAIN_PATTERNS["stay"])
            
            # 回転率・滞在傾向ペナルティ補正
            turnover_penalty = -10 if is_quick else (15 if is_stay else 0)
            
            # タイプ判定
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
                "dist": "周辺700m以内",
                "open_hour": 7, "close_hour": 22,  # 基本の営業時間想定
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
            
        return parsed_cafes
    except Exception:
        return []

# ==========================================
# 3. サイドバー・条件設定
# ==========================================
st.sidebar.header("⚙️ 条件・検索設定")
mode = st.sidebar.radio("📍 検索モードを選択", ["今すぐ探す（現在地GPS）", "未来・指定場所で探す"])

target_location = ""
target_datetime = None
lat, lon = 35.6691, 139.8166

if mode == "今すぐ探す（現在地GPS）":
    loc = get_geolocation()
    if loc and 'coords' in loc:
        lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
        st.sidebar.success(f"GPS取得: 緯度{lat:.4f} / 経度{lon:.4f}")
    else:
        st.sidebar.info("現在地未取得のため「東陽町」として計算中")
    
    target_location = "現在地周辺"
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
# 6. 実データの動的取得 ＆ 混雑・穴場判定
# ==========================================
st.header("🏪 カフェ穴場判定 ＆ 立ち回りナビ")

# OpenStreetMapから実際のカフェリストを動的に取得
with st.spinner("周辺の実在カフェデータを検索中..."):
    cafes = fetch_real_cafes(lat, lon)

if not cafes:
    st.warning("周辺に登録カフェが見つからなかったか、通信エラーが発生しました。別のエリア名を入力してみてください。")
else:
    st.caption(f"📍 {target_location} 周辺で {len(cafes)} 件のカフェを実データから検出しました")

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
