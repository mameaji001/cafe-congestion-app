import streamlit as st
import pandas as pd
import requests
from streamlit_js_eval import get_geolocation

# ページ設定
st.set_page_config(page_title="カフェ混雑予想", page_icon="☕", layout="wide")

st.title("☕ カフェ混雑シチュエーション予想 ＆ 周辺店舗チェック")
st.caption("現在地のGPSとシチュエーションから、周辺カフェの混雑度を素早く判定します！")

st.divider()

# --- GPS（位置情報）の取得 ---
st.subheader("📍 現在地のGPS取得")
loc = get_geolocation()

lat, lon = None, None
if loc and 'coords' in loc:
    lat = loc['coords']['latitude']
    lon = loc['coords']['longitude']
    st.success(f"✅ GPS取得成功！ 緯度: {lat:.6f} / 経度: {lon:.6f}")
else:
    st.info("💡 ブラウザの位置情報ポップアップで「許可」を選択してください。")

# デフォルト（東京駅）フォールバック
if lat is None or lon is None:
    lat, lon = 35.6812, 139.7671
    st.caption("※ 現在地未取得のため、初期値（東京駅周辺）でシミュレーションしています。")

st.divider()

# --- 天気自動取得 (Open-Meteo API) ---
weather_label = "晴れ/曇り ☀️"
weather_score = 0
temp = "--"

try:
    weather_res = requests.get(
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    ).json()
    current_w = weather_res.get("current_weather", {})
    temp = current_w.get("temperature", "--")
    weather_code = current_w.get("weathercode", 0)
    
    if weather_code >= 51:
        weather_label = "雨・悪天候 🌧️"
        weather_score = 25
    else:
        weather_label = "晴れ/曇り ☀️"
        weather_score = 0
except Exception:
    pass

col_w1, col_w2 = st.columns(2)
col_w1.metric(label="現在の天気", value=weather_label)
col_w2.metric(label="現在の気温", value=f"{temp} ℃")

st.divider()

# --- シチュエーション条件設定 ---
st.subheader("⚙️ 混雑・立地条件の選択")
c1, c2 = st.columns(2)
with c1:
    is_station_direct = st.checkbox("「駅直結・改札すぐ」の店舗を狙う")
    is_far = st.checkbox("駅から徒歩7分以上の店舗を狙う")
with c2:
    is_event = st.checkbox("周辺でイベント・祭りが開催されている")

# --- 共通ベーススコア計算 ---
base_score = 20 + weather_score
if is_station_direct:
    base_score += 30
if is_far:
    base_score -= 20
if is_event:
    base_score += 30

st.divider()

# --- 周辺店舗のダミーリスト表示（APIキー不要） ---
st.header("🏪 周辺のカフェリスト＆個別混雑予想")
st.caption("現在地周辺にある想定の店舗と、その混雑予測ステータスです。")

# ダミー店舗データ（店舗ごとの特性を持たせる）
dummy_cafes = [
    {"name": "スターバックス（駅前店）", "type": "駅直結・大手チェーン", "offset": 15, "dist": "徒歩1分"},
    {"name": "ドトールコーヒーショップ", "type": "駅チカ・カウンター多め", "offset": 5, "dist": "徒歩3分"},
    {"name": "隠れ家ロースターカフェ", "type": "個人経営・2階建て", "offset": -20, "dist": "徒歩6分"},
    {"name": "タリーズコーヒー（ビルイン店）", "type": "オフィス街型", "offset": 0, "dist": "徒歩4分"},
    {"name": "ブック＆コーヒー 読書堂", "type": "滞在型・回転率低", "offset": 10, "dist": "徒歩8分"},
]

for cafe in dummy_cafes:
    # 店舗ごとの個別補正を加える
    cafe_score = max(10, min(99, base_score + cafe["offset"]))
    
    with st.container(border=True):
        col_info, col_status = st.columns([2, 1])
        
        with col_info:
            st.markdown(f"### ☕ {cafe['name']}")
            st.write(f"特徴: {cafe['type']} ／ 距離: **{cafe['dist']}**")
            
        with col_status:
            if cafe_score >= 70:
                st.error(f"予想混雑度: **{cafe_score}%**\n(混雑・避けるべき)")
            elif cafe_score >= 40:
                st.warning(f"予想混雑度: **{cafe_score}%**\n(やや混雑)")
            else:
                st.success(f"予想混雑度: **{cafe_score}%**\n(空いてる狙い目)")

st.divider()

# --- 現在地を中心にしたマップ表示 ---
st.header("🗺️ 現在地マップ")
df_map = pd.DataFrame({'lat': [lat], 'lon': [lon]})
st.map(df_map, zoom=15)
