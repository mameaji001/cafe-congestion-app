import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone, date, time
from streamlit_js_eval import get_geolocation

# ページ設定
st.set_page_config(page_title="カフェ混雑ナビ", page_icon="☕", layout="wide")

st.title("☕ 未来予測 ＆ 目的別 カフェ穴場ナビ")
st.caption("Googleマップでは分からない「目的 × 天候 × 未来の状況」から最適な穴場を判定！")

st.divider()

JST = timezone(timedelta(hours=9), 'JST')

# ジオコーディング（OpenStreetMap）
def get_coordinates(location_name):
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={location_name}&format=json&limit=1"
        headers = {"User-Agent": "CafeCongestionApp/1.0"}
        res = requests.get(url, headers=headers, timeout=5).json()
        if res:
            return float(res[0]["lat"]), float(res[0]["lon"]), res[0]["display_name"]
    except Exception:
        pass
    return 35.6691, 139.8166, location_name

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

# 天気情報
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

# 目的とフィルタリング
st.sidebar.subheader("🎯 カフェ利用の目的（複数選択可）")
use_pc = st.sidebar.checkbox("💻 PC作業・仕事（コンセント・Wi-Fi重視）")
use_chat = st.sidebar.checkbox("🗣️ 友達と談笑・おしゃべり（話しやすさ・席数重視）")
use_read = st.sidebar.checkbox("📖 読書・勉強（静かさ・落ち着き重視）")
use_quick = st.sidebar.checkbox("⚡️ スキマ時間のサクッと休憩（回転率・手軽さ重視）")

weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
weekday_str = weekday_names[target_datetime.weekday()]
hour = target_datetime.hour
is_weekend = target_datetime.weekday() >= 5

time_score = 0
if is_weekend:
    time_score = 35 if 13 <= hour <= 17 else (20 if 11 <= hour <= 12 or 18 <= hour <= 20 else 5)
else:
    time_score = 25 if 8 <= hour <= 9 else (30 if 12 <= hour <= 13 else (20 if 14 <= hour <= 17 else 0))

c1, c2, c3 = st.columns(3)
c1.metric("対象エリア", target_location)
c2.metric("対象日時", f"{target_datetime.strftime('%m/%d')}({weekday_str}) {target_datetime.strftime('%H:%M')}")
c3.metric("予想天候", weather_label if mode == "今すぐ探す（現在地GPS）" else ("雨 🌧️" if is_rain else "晴れ ☀️"))

st.divider()

st.header("🏪 カフェ穴場判定 ＆ 立ち回りナビ")

cafes = [
    {
        "name": "スターバックス コーヒー (駅前店)",
        "address": f"{target_location}駅前 1-1-1 ビル1F",
        "type": "大手チェーン / 駅近",
        "dist": "徒歩1分",
        "open_hour": 7, "close_hour": 22,
        "is_station": True, "is_far": False,
        "features": {"pc": True, "chat": True, "read": False, "quick": True},
        "turnover_penalty": 10,
        "advice": "駅前でアクセス抜群ですが満席になりやすいです。テイクアウト推奨。"
    },
    {
        "name": "ドトールコーヒーショップ (駅構内・改札横店)",
        "address": f"{target_location}駅構内 改札すぐ",
        "type": "セルフカフェ / カウンター中心",
        "dist": "徒歩0分",
        "open_hour": 6, "close_hour": 21,
        "is_station": True, "is_far": False,
        "features": {"pc": False, "chat": True, "read": False, "quick": True},
        "turnover_penalty": -10,
        "advice": "回転率が高いため、少し待てば席が確保できる可能性が高いです。"
    },
    {
        "name": "上島珈琲店 / プロント (大通り沿い店)",
        "address": f"{target_location} 2-3-5 大通り沿い",
        "type": "落ち着いた空間 / ソファ・電源あり",
        "dist": "徒歩4分",
        "open_hour": 7, "close_hour": 22,
        "is_station": False, "is_far": False,
        "features": {"pc": True, "chat": True, "read": True, "quick": False},
        "turnover_penalty": 10,
        "advice": "電源席が多く作業に向いていますが、滞在時間が長くなりがちです。"
    },
    {
        "name": "コメダ珈琲店 (郊外・大通り店)",
        "address": f"{target_location} 3-10-2",
        "type": "ボックス席メイン / 滞在型",
        "dist": "徒歩6分",
        "open_hour": 7, "close_hour": 23,
        "is_station": False, "is_far": True,
        "features": {"pc": True, "chat": True, "read": True, "quick": False},
        "turnover_penalty": 20,
        "advice": "席が広く快適ですが、混雑時は発券機での待ち時間が発生します。"
    },
    {
        "name": "ベローチェ (裏路地・オフィス街店)",
        "address": f"{target_location} 1-8-12 裏路地ビル1F",
        "type": "広々低価格カフェ / 穴場",
        "dist": "徒歩5分",
        "open_hour": 7, "close_hour": 21,
        "is_station": False, "is_far": False,
        "features": {"pc": True, "chat": True, "read": True, "quick": True},
        "turnover_penalty": -15,
        "advice": "席数が多く裏路地にあるため、ピーク時でも比較的空いている穴場です。"
    }
]

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
            st.markdown(f"**☕ {cafe['name']}**")
            st.caption(f"📍 住所: {cafe['address']} ({cafe['dist']}) | 🕒 {cafe['open_hour']}:00〜{cafe['close_hour']}:00")
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
# GoogleマップAPIキーを組み込んだ地図表示（修正版）
# ==========================================
st.header("🗺️ 周辺マップ（Google Maps API連携）")

google_api_key = "AIzaSyAN1EEVcNTgNI_Dxu8WBc7XVBTUBOHzVwY"

# f-stringを使わず通常の文字列結合にしてSyntaxErrorを完全に防止
map_html = """
    <div id="map" style="width:100%; height:300px;"></div>
    <script>
      function initMap() {
        const targetLocation = { lat: """ + str(lat) + """, lng: """ + str(lon) + """ };
        const map = new google.maps.Map(document.getElementById("map"), {
          zoom: 15,
          center: targetLocation,
        });
        new google.maps.Marker({
          position: targetLocation,
          map: map,
          title: "検索中心地",
        });
      }
    </script>
    <script async defer
      src="https://maps.googleapis.com/maps/api/js?key=""" + google_api_key + """&callback=initMap">
    </script>
"""

st.components.v1.html(map_html, height=320)
