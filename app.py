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

# ==========================================
# 実在店舗データベース（主要エリアの実データ）
# ==========================================
REAL_CAFE_DATABASE = {
    "東陽町": [
        {"name": "プロント 東陽町店", "address": "東陽町駅 徒歩1分", "type": "高回転・セルフカフェ", "open_hour": 7, "close_hour": 22, "is_station": True, "is_far": False, "turnover_penalty": -10, "advice": "駅すぐでアクセス良好。席数も多めで使いやすいです。", "features": {"pc": True, "chat": True, "read": True, "quick": True}},
        {"name": "ドトールコーヒーショップ 東陽町店", "address": "東陽町駅 徒歩2分", "type": "高回転・セルフカフェ", "open_hour": 7, "close_hour": 21, "is_station": True, "is_far": False, "turnover_penalty": -15, "advice": "回転率が高いため、混んでいても少し待てば座れる確率が高いです。", "features": {"pc": False, "chat": True, "read": True, "quick": True}},
        {"name": "カフェ・ド・クリエ 東陽町店", "address": "東陽町駅 徒歩3分", "type": "セルフ・ゆったりカフェ", "open_hour": 7, "close_hour": 20, "is_station": False, "is_far": False, "turnover_penalty": 0, "advice": "比較的分煙・席にゆとりがあり、読書や作業に向いています。", "features": {"pc": True, "chat": True, "read": True, "quick": False}},
        {"name": "タリーズコーヒー 江東区役所前店", "address": "東陽町駅 徒歩5分（区役所前）", "type": "人気大手チェーン", "is_station": False, "is_far": True, "turnover_penalty": 10, "advice": "駅から少し離れるため、駅前が混雑している時間帯の穴場です。", "features": {"pc": True, "chat": True, "read": True, "quick": False}},
        {"name": "上島珈琲店 東陽町店", "address": "東陽町駅 徒歩4分", "type": "ボックス・滞在型カフェ", "open_hour": 7, "close_hour": 20, "is_station": False, "is_far": False, "turnover_penalty": 15, "advice": "落ち着いた雰囲気で電源席もあり仕事に向いていますが、混雑時は滞在長めです。", "features": {"pc": True, "chat": False, "read": True, "quick": False}},
    ],
    "木場": [
        {"name": "スターバックス コーヒー イトーヨーカドー木場店", "address": "木場駅 徒歩5分", "type": "人気大手チェーン", "is_station": False, "is_far": True, "turnover_penalty": 20, "advice": "商業施設内のため土日はファミリー層で非常に混雑します。", "features": {"pc": True, "chat": True, "read": False, "quick": False}},
        {"name": "コメダ珈琲店 深川ギャザリア店", "address": "木場駅 徒歩4分", "type": "ボックス・滞在型カフェ", "open_hour": 7, "close_hour": 22, "is_station": False, "is_far": False, "turnover_penalty": 20, "advice": "席が広く快適ですが、ピーク時は発券機での待ちが発生します。", "features": {"pc": True, "chat": True, "read": True, "quick": False}},
    ]
}

# 座標変換辞書
LOCATION_COORDS = {
    "東陽町": (35.6691, 139.8166),
    "木場": (35.6692, 139.8080),
    "門前仲町": (35.6717, 139.7963),
    "清澄白河": (35.6823, 139.8086),
}

# ==========================================
# サイドバー・条件設定
# ==========================================
st.sidebar.header("⚙️ 条件・検索設定")
mode = st.sidebar.radio("📍 検索モードを選択", ["今すぐ探す（現在地GPS）", "未来・指定場所で探す"])

target_location = "東陽町"
target_datetime = datetime.now(JST)

if mode == "今すぐ探す（現在地GPS）":
    loc = get_geolocation()
    if loc and 'coords' in loc:
        lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
        st.sidebar.success(f"📍 GPS取得成功!\n({lat:.4f}, {lon:.4f})")
    else:
        st.sidebar.info("💡 エリアを指定してください")
        target_location = st.sidebar.selectbox("エリアを選択", list(REAL_CAFE_DATABASE.keys()), index=0)
else:
    target_location = st.sidebar.selectbox("エリアを選択", list(REAL_CAFE_DATABASE.keys()), index=0)
    selected_date = st.sidebar.date_input("日付を選択", date.today())
    selected_time = st.sidebar.time_input("時間を選択", time(15, 0))
    target_datetime = datetime.combine(selected_date, selected_time).replace(tzinfo=JST)

lat, lon = LOCATION_COORDS.get(target_location, (35.6691, 139.8166))

# 天気設定
is_rain = st.sidebar.checkbox("🌧️ 天気：雨としてシミュレーション") if mode != "今すぐ探す（現在地GPS）" else False
is_event = st.sidebar.checkbox("🎪 周辺で大規模イベント開催中", value=False)

# 利用目的設定
st.sidebar.subheader("🎯 カフェ利用の目的")
use_pc = st.sidebar.checkbox("💻 PC作業・仕事")
use_chat = st.sidebar.checkbox("🗣️ 友達と談笑")
use_read = st.sidebar.checkbox("📖 読書・勉強")
use_quick = st.sidebar.checkbox("⚡️ サクッと休憩")

# ヘッダー表示
weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
weekday_str = weekday_names[target_datetime.weekday()]

c1, c2, c3 = st.columns(3)
c1.metric("対象エリア", target_location)
c2.metric("対象日時", f"{target_datetime.strftime('%m/%d')}({weekday_str}) {target_datetime.strftime('%H:%M')}")
c3.metric("予想天候", "雨 🌧️" if is_rain else "晴れ ☀️")

st.divider()

# ==========================================
# カフェ穴場判定表示
# ==========================================
st.header("🏪 カフェ穴場判定 ＆ 立ち回りナビ")

# 選択エリアの実データ取得
cafes = REAL_CAFE_DATABASE.get(target_location, REAL_CAFE_DATABASE["東陽町"])

# 時間帯判定スコア
hour = target_datetime.hour
is_weekend = target_datetime.weekday() >= 5
time_score = 35 if (is_weekend and 13 <= hour <= 17) else (20 if 14 <= hour <= 17 else 10)

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
    if use_quick and cafe["features"]["quick"]: match_reasons.append("⚡️ 高回転")

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

# MAP表示
st.header("🗺️ 周辺マップ")
st.components.v1.html(
    f"""
    <iframe width="100%" height="300" frameborder="0" scrolling="no" src="https://maps.google.com/maps?q={lat},{lon}&z=15&output=embed"></iframe>
    """,
    height=320
)
