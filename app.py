import streamlit as st
import pandas as pd
import requests
from streamlit_js_eval import get_geolocation

# ページ設定
st.set_page_config(page_title="カフェ混雑予想", page_icon="☕", layout="wide")

st.title("☕ カフェ混雑シチュエーション予想")
st.caption("現在地のリアルタイムGPS座標を取得して、混雑シミュレーションを行います！")

st.divider()

# --- GPS（位置情報）の取得 ---
st.subheader("📍 現在地のGPS取得")
st.write("「位置情報を取得」ボタンを押すと、ブラウザから現在地の正確な緯度・経度を取得します。")

# JavaScript経由でGPS取得
loc = get_geolocation()

lat, lon = None, None

if loc and 'coords' in loc:
    lat = loc['coords']['latitude']
    lon = loc['coords']['longitude']
    st.success(f"✅ GPS取得成功！ 緯度: {lat:.6f} / 経度: {lon:.6f}")
else:
    st.info("💡 下のボタンまたはブラウザの許可ダイアログで位置情報の利用を「許可」してください。")

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
    
    # 雨系コード判定
    if weather_code >= 51:
        weather_label = "雨・悪天候 🌧️"
        weather_score = 25
    else:
        weather_label = "晴れ/曇り ☀️"
        weather_score = 0

except Exception:
    st.warning("天気の自動取得に失敗しました。")

# 条件・シチュエーション設定
col_w1, col_w2 = st.columns(2)
col_w1.metric(label="現在地の推測天気", value=weather_label)
col_w2.metric(label="現在地の気温", value=f"{temp} ℃")

st.subheader("⚙️ シチュエーション補正")
c1, c2 = st.columns(2)
with c1:
    is_station_direct = st.checkbox("近くのカフェが「駅直結・改札すぐ」にある")
    is_far = st.checkbox("駅から徒歩7分以上離れた店舗を狙う")
with c2:
    is_event = st.checkbox("周辺でイベント・祭りが開催されている")

# --- 判定ロジック ---
score = 20 + weather_score

if is_station_direct:
    score += 30
if is_far:
    score -= 20
if is_event:
    score += 30

congestion = max(10, min(99, score))

st.divider()

# --- 判定結果表示 ---
st.header("📊 判定結果")

m1, m2 = st.columns([1, 2])

with m1:
    if congestion >= 70:
        st.error(f"⚠️ 予想混雑度: **{congestion}%**")
        st.write("🚨 **かなり混雑しています**")
    elif congestion >= 40:
        st.warning(f"🟡 予想混雑度: **{congestion}%**")
        st.write("⚠️ **やや混雑しています**")
    else:
        st.success(f"🟢 予想混雑度: **{congestion}%**")
        st.write("✨ **空いている可能性が高いです**")

with m2:
    st.write("💡 **おすすめの立ち回りアドバイス**")
    if congestion >= 70:
        st.info("・駅直結や改札前の店舗は激混みです！\n・駅から徒歩7分以上離れた店舗や2階以上の隠れ家カフェを狙いましょう。")
    elif congestion >= 40:
        st.info("・席数の多い広めの店舗や、テイクアウト専門スタンドを選ぶとスムーズに入れます。")
    else:
        st.info("・混雑のリスクは低めです。ゆったり座れるお好みのカフェをお楽しみください！")

st.progress(congestion / 100)

st.divider()

# --- 現在地を中心にしたマップ表示 ---
st.header("🗺️ 取得したGPS中心の地図")
st.caption("ピンは実際の現在地周辺を示しています")

df_map = pd.DataFrame({
    'lat': [lat],
    'lon': [lon]
})

st.map(df_map, zoom=15)
