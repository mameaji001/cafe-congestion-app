import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone, date, time
from streamlit_js_eval import get_geolocation

# ページ基本設定
st.set_page_config(
    page_title="カフェ穴場ナビ ☕️", 
    page_icon="☕️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# スタイリング
st.markdown("""
    <style>
    .main-title { color: #2c3e50; font-weight: bold; font-size: 2.0rem; }
    .sub-title { color: #7f8c8d; font-size: 0.95rem; }
    </style>
""", unsafe_allow_html=True)

st.markdown("<div class='main-title'>☕️ エリアを打つだけ！カフェ穴場ナビ</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>場所と目的に合わせて、今の天気・混雑確率・立ち回りアドバイスを自動で予測します。</div>", unsafe_allow_html=True)

st.divider()

JST = timezone(timedelta(hours=9), 'JST')

# ==========================================
# 1. ジオコーディング（エリア名から緯度経度を取得）
# ==========================================
def get_coordinates(location_name):
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={location_name}&format=json&limit=1&countrycodes=jp"
        headers = {"User-Agent": "CafeNaviApp/7.0"}
        res = requests.get(url, headers=headers, timeout=5).json()
        if res:
            return float(res[0]["lat"]), float(res[0]["lon"]), res[0]["display_name"].split(",")[0]
    except Exception:
        pass
    return 35.6996, 139.7526, location_name  # デフォルト

# ==========================================
# 2. 自動天気取得（Open-Meteo API）
# ==========================================
def fetch_weather(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        res = requests.get(url, timeout=5).json()
        w_code = res.get("current_weather", {}).get("weathercode", 0)
        if w_code >= 51:
            return True, "雨・悪天候 🌧️"
    except Exception:
        pass
    return False, "晴れ / 曇り ☀️"

# ==========================================
# 3. エリア特性 ＆ イベントAI自動推測
# ==========================================
def analyze_area_characteristics(area_name, target_dt):
    """ 入力された場所と日時から、混雑要因やイベントを自動判定する """
    area_lower = area_name.lower()
    hour = target_dt.hour
    is_weekend = target_dt.weekday() >= 5
    
    event_detected = False
    event_msg = ""
    base_boost = 0
    
    # ドーム・スタジアム・大型イベントエリア
    if any(k in area_lower for k in ["水道橋", "後楽園", "東京ドーム"]):
        if is_weekend and (11 <= hour <= 19):
            event_detected = True
            event_msg = "⚾ 東京ドーム周辺：試合やコンサートによる大規模な混雑が予想されます。"
            base_boost += 35
    elif any(k in area_lower for k in ["舞浜", "ディズニー"]):
        event_detected = True
        event_msg = "🎢 舞浜エリア：パークの開閉園前後は周辺カフェが非常に混雑します。"
        base_boost += 30
    elif any(k in area_lower for k in ["国立競技場", "千駄ケ谷", "味の素スタジアム", "日産スタジアム"]):
        if is_weekend:
            event_detected = True
            event_msg = "⚽ スタジアム周辺：スポーツの試合やイベント開催による混雑注意。"
            base_boost += 30
    elif any(k in area_lower for k in ["渋谷", "新宿", "原宿", "池袋", "銀座"]):
        if is_weekend and (13 <= hour <= 18):
            event_detected = True
            event_msg = "🛍️ 主要ターミナル駅：休日のショッピング客で一日中混み合います。"
            base_boost += 20
            
    return event_detected, event_msg, base_boost

# ==========================================
# 4. カフェデータ取得（全国対応・フォールバック付）
# ==========================================
@st.cache_data(ttl=1800)
def fetch_cafes(lat, lon, area_name):
    headers = {"User-Agent": "CafeNaviApp/7.0"}
    overpass_url = "https://overpass-api.de/api/interpreter"
    
    query = f"""
    [out:json][timeout:10];
    (
      node["amenity"="cafe"](around:1000,{lat},{lon});
      way["amenity"="cafe"](around:1000,{lat},{lon});
    );
    out body 15;
    """
    
    cafes = []
    try:
        res = requests.post(overpass_url, data={"data": query}, headers=headers, timeout=8)
        if res.status_code == 200:
            data = res.json()
            for item in data.get("elements", []):
                tags = item.get("tags", {})
                name = tags.get("name")
                if not name:
                    continue
                
                is_chain = any(k in name for k in ["スターバックス", "Starbucks", "ドトール", "タリーズ", "ベローチェ", "プロント", "コメダ"])
                is_quick = any(k in name for k in ["ドトール", "ベローチェ", "プロント"])
                
                cafes.append({
                    "name": name,
                    "address": f"{area_name} 周辺",
                    "type": "人気大手チェーン ☕️" if is_chain else "ローカル・個人カフェ 🌿",
                    "open_hour": 7, "close_hour": 22,
                    "is_station": is_chain,
                    "is_far": not is_chain,
                    "turnover_penalty": -15 if is_quick else (15 if not is_chain else 0),
                    "advice": "回転率が高めですが混雑しやすい店舗です。" if is_quick else "落ち着いて過ごせますが席数が限られます。",
                    "features": {
                        "pc": not is_quick,
                        "chat": True,
                        "read": not is_chain,
                        "quick": is_quick
                    }
                })
    except Exception:
        cafes = []

    if not cafes:
        cafes = [
            {
                "name": f"{area_name}駅前 セルフカフェ",
                "address": f"{area_name} 駅チカ",
                "type": "高回転・セルフカフェ ⚡️",
                "open_hour": 7, "close_hour": 22,
                "is_station": True, "is_far": False, "turnover_penalty": -15,
                "advice": "駅からのアクセスが良く、サクッと利用したい時に便利です。",
                "features": {"pc": False, "chat": True, "read": True, "quick": True}
            },
            {
                "name": f"{area_name} 大通り沿いカフェ",
                "address": f"{area_name} メイン通り",
                "type": "人気大手チェーン ☕️",
                "open_hour": 8, "close_hour": 21,
                "is_station": True, "is_far": False, "turnover_penalty": 10,
                "advice": "作業や待ち合わせに向いていますが、ピーク時は混み合います。",
                "features": {"pc": True, "chat": True, "read": True, "quick": False}
            },
            {
                "name": f"{area_name} 隠れ家ロースター",
                "address": f"{area_name} 徒歩5分・路地裏",
                "type": "ゆったり個人カフェ 🌿",
                "open_hour": 9, "close_hour": 19,
                "is_station": False, "is_far": True, "turnover_penalty": -10,
                "advice": "駅から少し歩くため、比較的静かに過ごせる穴場です。",
                "features": {"pc": True, "chat": True, "read": True, "quick": False}
            }
        ]
    return cafes

# ==========================================
# 5. サイドバー（シンプルな入力のみ）
# ==========================================
st.sidebar.header("📍 検索条件")

search_query = st.sidebar.text_input("行きたいエリア・駅名を入力", value="水道橋")

lat, lon, area_disp = get_coordinates(search_query)

# 現在時刻と自動天気を取得
now_dt = datetime.now(JST)
is_rain, weather_label = fetch_weather(lat, lon)
is_event, event_msg, event_boost = analyze_area_characteristics(search_query, now_dt)

st.sidebar.divider()

# 利用目的（シンプル）
st.sidebar.subheader("🎯 カフェ利用の目的（複数選択可）")
use_pc = st.sidebar.checkbox("💻 PC作業・仕事")
use_chat = st.sidebar.checkbox("🗣️ 友達と談笑・おしゃべり")
use_read = st.sidebar.checkbox("📖 読書・勉強")
use_quick = st.sidebar.checkbox("⚡️ スキマ時間のサクッと休憩")

# ==========================================
# 6. メイン画面・サマリー
# ==========================================
weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
weekday_str = weekday_names[now_dt.weekday()]

c1, c2, c3 = st.columns(3)
c1.metric("📍 対象エリア", search_query)
c2.metric("🕒 現在時刻", f"{now_dt.strftime('%m/%d')}({weekday_str}) {now_dt.strftime('%H:%M')}")
c3.metric("☁️ 現地の天気", weather_label)

if is_event:
    st.warning(f"⚠️ **AIエリア推測**: {event_msg}")

st.divider()

# ==========================================
# 7. 混雑度スコア計算 ＆ カフェ一覧表示
# ==========================================
st.subheader(f"🏪 {search_query} 周辺のカフェ穴場判定")

cafes = fetch_cafes(lat, lon, search_query)

hour = now_dt.hour
is_weekend = now_dt.weekday() >= 5
time_score = 35 if (is_weekend and 13 <= hour <= 17) else (20 if 14 <= hour <= 17 else 10)

for cafe in cafes:
    # 混雑スコアロジック
    score = 15 + time_score + event_boost
    if is_rain:
        if cafe["is_station"]: score += 30
        elif cafe["is_far"]: score -= 20
    else:
        if cafe["is_station"]: score += 15
    
    score += cafe["turnover_penalty"]
    
    final_score = max(10, min(99, score))

    # 目的マッチングタグ
    match_tags = []
    if use_pc and cafe["features"]["pc"]: match_tags.append("💻 PC作業可")
    if use_chat and cafe["features"]["chat"]: match_tags.append("🗣️ おしゃべり向")
    if use_read and cafe["features"]["read"]: match_tags.append("📖 読書・勉強向")
    if use_quick and cafe["features"]["quick"]: match_tags.append("⚡️ 高回転・サクッと")

    with st.container(border=True):
        col1, col2, col3 = st.columns([2.5, 1.5, 1])

        with col1:
            st.markdown(f"**☕ {cafe['name']}** (`{cafe['type']}`)")
            st.caption(f"📍 {cafe['address']}")
            st.caption(f"💡 {cafe['advice']}")

        with col2:
            if match_tags:
                st.write(" ".join([f"`{t}`" for t in match_tags]))
            else:
                st.caption("標準的な利用に向いています")

        with col3:
            if final_score >= 70:
                st.error(f"混雑確率: **{final_score}%**\n(混雑・要回避)")
            elif final_score >= 40:
                st.warning(f"混雑確率: **{final_score}%**\n(やや混み)")
            else:
                st.success(f"混雑確率: **{final_score}%**\n(ねらい目！)")

st.divider()

# MAP表示
st.subheader("🗺️ 周辺エリアマップ")
st.components.v1.html(
    f"""
    <iframe width="100%" height="300" frameborder="0" scrolling="no" src="https://maps.google.com/maps?q={lat},{lon}&z=15&output=embed"></iframe>
    """,
    height=320
)
