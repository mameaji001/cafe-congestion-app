import streamlit as st
import pandas as pd
import requests

# ページ基本設定
st.set_page_config(page_title="カフェ混雑予想", page_icon="☕", layout="wide")

st.title("☕ カフェ混雑シチュエーション予想")
st.caption("今の状況や位置情報から、混雑確率とおすすめの立ち回りを自動判定します！")

st.divider()

# タブ分けで直感的なUIに
tab1, tab2 = st.tabs(["📡 自動推測（位置情報＆リアルタイム天気）", "⚙️ 手動でシチュエーション指定"])

# デフォルト設定
lat, lon = 35.6812, 139.7671 # 東京駅初期値
weather_label = "晴れ/曇り"
weather_score = 0

with tab1:
    st.subheader("現在地から自動推測")
    st.write("ボタンを押して現在地の天気と位置情報を取得します。")
    
    # 位置情報取得用HTML/JS
    loc_html = """
    <script>
    function getLocation() {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(showPosition);
        } else { 
            alert("Geolocation is not supported by this browser.");
        }
    }
    function showPosition(position) {
        const lat = position.coords.latitude;
        const lon = position.coords.longitude;
        window.parent.postMessage({type: 'streamlit:setComponentValue', value: {lat: lat, lon: lon}}, '*');
    }
    </script>
    <button onclick="getLocation()" style="padding: 10px 20px; background-color: #ff4b4b; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">
        📍 現在地を取得して天気をチェック
    </button>
    """
    
    # 簡易位置情報取得（IP・APIベース補完）
    try:
        # 無料の天気API (Open-Meteo)
        weather_res = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true").json()
        temp = weather_res.get("current_weather", {}).get("temperature", "--")
        weather_code = weather_res.get("current_weather", {}).get("weathercode", 0)
        
        # Weathercode 判定 (51以上は雨・雪系)
        if weather_code >= 51:
            weather_label = "雨・悪天候 🌧️"
            weather_score = 25
        else:
            weather_label = "晴れ/曇り ☀️"
            weather_score = 0
            
        col_w1, col_w2 = st.columns(2)
        col_w1.metric(label="現在の推定天気", value=weather_label)
        col_w2.metric(label="現在地の気温", value=f"{temp} ℃")
    except Exception as e:
        st.warning("天気の自動取得に失敗したため、手動設定を使用します。")

with tab2:
    st.subheader("条件を手動で細かく選ぶ")
    c1, c2 = st.columns(2)
    with c1:
        manual_weather = st.radio("天候", ["晴れ・曇り", "雨・悪天候"])
        manual_loc = st.radio("立地", ["駅直結・改札すぐ", "徒歩3〜5分圏内", "徒歩7分以上"])
    with c2:
        manual_time = st.selectbox("時間帯", ["平日・午前", "平日・カフェタイム（14-17時）", "土日祝・カフェタイム（14-17時）", "夜（18時以降）"])
        manual_event = st.checkbox("近隣でイベント・祭りがある")

# --- 判定ロジック ---
score = 20 + weather_score

# 手動タブ選択時の補正
if manual_weather == "雨・悪天候":
    score += 25
if manual_loc == "駅直結・改札すぐ":
    score += 30
elif manual_loc == "徒歩7分以上":
    score -= 15

if "土日祝" in manual_time:
    score += 25
if manual_event:
    score += 30

congestion = max(10, min(99, score))

st.divider()

# --- 結果表示 ---
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
        st.info("・駅直結や有名チェーンは避けるのが無難です。\n・駅から徒歩7分以上離れたビル上階のカフェやテイクアウト専門店が狙い目です！")
    elif congestion >= 40:
        st.info("・席数の多い店舗（ドトール等）や、2階以上に席がある店舗を探すと入りやすいです。")
    else:
        st.info("・ゆっくり過ごせるチャンス！ゆったり座れるソファ席や作業向きカフェを狙ってみましょう。")

st.progress(congestion / 100)

st.divider()

# --- 地図表示（マップ） ---
st.header("🗺️ 周辺カフェの混雑傾向マップ")
st.caption("赤：混雑リスク高 / 緑：穴場リスク低")

# 現在地周辺のサンプルデータ生成
map_data = pd.DataFrame({
    'lat': [lat + 0.002, lat - 0.003, lat + 0.001, lat - 0.001],
    'lon': [lon + 0.002, lon - 0.001, lon - 0.003, lon + 0.003],
    'name': ['駅前チェーンカフェ', '路地裏隠れ家カフェ', 'ビル2Fテラスカフェ', 'テイクアウト専門店']
})

st.map(map_data)

st.caption("【スポンサーリンク】📢 ここにGoogle AdMobなどの広告バナーが配置されます")
