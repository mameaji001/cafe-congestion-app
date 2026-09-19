import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone, date, time
from streamlit_js_eval import get_geolocation

# ページ基本設定
st.set_page_config(
    page_title="カフェ穴場・混雑予測ナビ ☕️", 
    page_icon="☕️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自由なスタイリング（ポップで親しみやすいテーマ）
st.markdown("""
    <style>
    .main-title {
        color: #ff6b81;
        font-weight: bold;
        font-size: 2.2rem;
    }
    .sub-title {
        color: #555555;
        font-size: 1.0rem;
    }
    .stButton>button {
        background-color: #ff6b81;
        color: white;
        border-radius: 20px;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("<div class='main-title'>☕️ ぴったりカフェ＆穴場ナビ</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>天候や時間帯、みんなの目的（勉強・談笑・ママ会など）から今の穴場を判定します♪</div>", unsafe_allow_html=True)

st.divider()

JST = timezone(timedelta(hours=9), 'JST')

# ==========================================
# 1. 汎用ジオコーディング（どんなエリアでも座標取得）
# ==========================================
def get_coordinates(location_name):
    """ OpenStreetMapで全国の地名・駅名から緯度経度を取得 """
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={location_name}&format=json&limit=1&countrycodes=jp"
        headers = {"User-Agent": "CafeNaviApp/5.0"}
        res = requests.get(url, headers=headers, timeout=5).json()
        if res:
            return float(res[0]["lat"]), float(res[0]["lon"]), res[0]["display_name"].split(",")[0]
    except Exception:
        pass
    # デフォルト：原宿・表参道周辺
    return 35.6702, 139.7027, location_name

# ==========================================
# 2. 全国対応：OpenStreetMap店舗データ取得
# ==========================================
@st.cache_data(ttl=1800)
def fetch_cafes_for_area(lat, lon, area_name):
    headers = {"User-Agent": "CafeNaviApp/5.0"}
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
                
                # タイプ判定
                is_chain = any(k in name for k in ["スターバックス", "Starbucks", "ドトール", "タリーズ", "ベローチェ", "サンマルク", "プロント", "コメダ"])
                is_trend = any(k in name for k in ["映え", "スイーツ", "韓国", "タピオカ", "Pancake", "パンケーキ", "サロン"])
                
                cafes.append({
                    "name": name,
                    "address": f"{area_name} 周辺",
                    "type": "トレンド・人気カフェ 🌸" if is_trend else ("定番チェーン ☕️" if is_chain else "ゆったり個人カフェ 🌿"),
                    "open_hour": 8, "close_hour": 21,
                    "is_station": is_chain,
                    "is_far": not is_chain,
                    "turnover_penalty": -10 if "ドトール" in name or "ベローチェ" in name else 10,
                    "advice": "トレンド店のため若者層で混みやすいです。" if is_trend else "作業やスキマ休憩に利用しやすい店舗です。",
                    "features": {
                        "jk_jd": is_trend or "スターバックス" in name or "Pancake" in name,
                        "business": is_chain and "スターバックス" not in name,
                        "mom": not is_chain or "コメダ" in name,
                        "quick": "ドトール" in name or "ベローチェ" in name
                    }
                })
    except Exception:
        cafes = []

    # API取得ができなかった場合の代替表示（どんなエリアでも破綻しない）
    if not cafes:
        cafes = [
            {
                "name": f"{area_name}駅前 スキマカフェ",
                "address": f"{area_name} 改札出てすぐ",
                "type": "定番セルフカフェ ☕️",
                "open_hour": 7, "close_hour": 22,
                "is_station": True, "is_far": False, "turnover_penalty": -10,
                "advice": "回転率が高いため、サクッと休憩したい時に最適です。",
                "features": {"jk_jd": False, "business": True, "mom": False, "quick": True}
            },
            {
                "name": f"{area_name} テラス＆スイーツカフェ",
                "address": f"{area_name} 徒歩3分",
                "type": "トレンド・人気カフェ 🌸",
                "open_hour": 10, "close_hour": 20,
                "is_station": False, "is_far": False, "turnover_penalty": 15,
                "advice": "女子会や映えスイーツ、おしゃべりに人気のスポットです。",
                "features": {"jk_jd": True, "business": False, "mom": True, "quick": False}
            },
            {
                "name": f"{area_name} 裏路地ローカル珈琲",
                "address": f"{area_name} 徒歩5分",
                "type": "ゆったり個人カフェ 🌿",
                "open_hour": 9, "close_hour": 19,
                "is_station": False, "is_far": True, "turnover_penalty": -5,
                "advice": "駅から少し離れているため、ピーク時でも入れる確率が高い穴場です。",
                "features": {"jk_jd": True, "business": True, "mom": True, "quick": False}
            }
        ]
        
    return cafes

# ==========================================
# 3. サイドバー・条件設定（ユーザー視点の選択肢）
# ==========================================
st.sidebar.header("🔍 条件を選ぶ")

mode = st.sidebar.radio("📍 探しかた", ["文字で入力して探す", "現在地GPSで探す"])

search_query = "原宿"
if mode == "文字で入力して探す":
    search_query = st.sidebar.text_input("エリア名・駅名を入力（全国対応）", value="原宿")
else:
    loc = get_geolocation()
    if loc and 'coords' in loc:
        lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
        st.sidebar.success("📍 GPSで現在地を取得しました！")
        search_query = "現在地周辺"
    else:
        st.sidebar.warning("GPS取得中のため、仮のエリアを表示しています。")
        search_query = st.sidebar.text_input("エリア名・駅名を入力", value="渋谷")

selected_date = st.sidebar.date_input("日付", date.today())
selected_time = st.sidebar.time_input("時間", time(15, 0))
target_datetime = datetime.combine(selected_date, selected_time).replace(tzinfo=JST)

lat, lon, area_disp = get_coordinates(search_query)

# 天気・イベント
is_rain = st.sidebar.checkbox("🌧️ あいにくの雨模様")
is_event = st.sidebar.checkbox("🎪 近くでイベント・祭りあり")

st.sidebar.divider()

# ユーザー属性・目的選択（親しみやすいラベル）
st.sidebar.subheader("👤 あなたの利用スタイル")
user_jk_jd = st.sidebar.checkbox("🎀 JK・女子大生（映え・最新トレンド・おしゃべり）")
user_biz = st.sidebar.checkbox("💻 サラリーマン・OL（PC作業・コンセント・即入店）")
user_mom = st.sidebar.checkbox("👶 ママ・パパ・子連れ（ゆったり席・ベビーカー優先）")

# 時間帯判定
hour = target_datetime.hour
is_weekend = target_datetime.weekday() >= 5
weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
weekday_str = weekday_names[target_datetime.weekday()]

# ==========================================
# 4. ヘッダーサマリー表示
# ==========================================
c1, c2, c3 = st.columns(3)
c1.metric("📍 検索エリア", search_query)
c2.metric("🗓️ 予定日時", f"{target_datetime.strftime('%m/%d')}({weekday_str}) {target_datetime.strftime('%H:%M')}")
c3.metric("☁️ お天気", "雨・悪天候 🌧️" if is_rain else "晴れ・曇り ☀️")

st.divider()

# ==========================================
# 5. カフェ一覧 ＆ 混雑度スコア表示
# ==========================================
st.subheader(f"✨ {search_query} 周辺のおすすめ・穴場カフェ")

cafes = fetch_cafes_for_area(lat, lon, search_query)

time_score = 35 if (is_weekend and 13 <= hour <= 17) else (20 if 14 <= hour <= 17 else 10)

for cafe in cafes:
    # 混雑度計算
    score = 15 + time_score
    if is_rain:
        if cafe["is_station"]: score += 30
        elif cafe["is_far"]: score -= 20
    else:
        if cafe["is_station"]: score += 10
    
    score += cafe["turnover_penalty"]
    if is_event: score += 25
    if user_jk_jd and cafe["features"]["jk_jd"]: score += 15  # 若者向けスポットは混みやすい
    
    final_score = max(10, min(99, score))

    # マッチング用バグ表示
    match_tags = []
    if user_jk_jd and cafe["features"]["jk_jd"]: match_tags.append("🌸 トレンド・映え")
    if user_biz and cafe["features"]["business"]: match_tags.append("💻 作業・電源向")
    if user_mom and cafe["features"]["mom"]: match_tags.append("👶 ゆったり・子連れ向")
    if cafe["features"]["quick"]: match_tags.append("⚡️ 回転早め")

    with st.container(border=True):
        col1, col2, col3 = st.columns([2.5, 1.5, 1])

        with col1:
            st.markdown(f"**{cafe['name']}**")
            st.caption(f"🏷️ {cafe['type']} | 📍 {cafe['address']}")
            st.caption(f"💬 {cafe['advice']}")

        with col2:
            if match_tags:
                st.write(" ".join([f"`{t}`" for t in match_tags]))
            else:
                st.caption("標準的な利用に向いています")

        with col3:
            if final_score >= 75:
                st.error(f"混雑確率 **{final_score}%**\n(混雑気味)")
            elif final_score >= 45:
                st.warning(f"混雑確率 **{final_score}%**\n(やや混雑)")
            else:
                st.success(f"混雑確率 **{final_score}%**\n(ねらい目！)")

st.divider()

# MAP表示
st.subheader("🗺️ 周辺の地図を確認")
st.components.v1.html(
    f"""
    <iframe width="100%" height="300" frameborder="0" scrolling="no" src="https://maps.google.com/maps?q={lat},{lon}&z=15&output=embed"></iframe>
    """,
    height=320
)
