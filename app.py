import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone, date, time
from streamlit_js_eval import get_geolocation

# ページ設定
st.set_page_config(page_title="未来予測＆目的別 カフェ混雑ナビ", page_icon="☕", layout="wide")

st.title("☕ 未来予測 ＆ 目的別 カフェ穴場ナビ")
st.caption("Googleマップでは分からない「目的 × 天候 × 未来の状況」から最適な穴場を判定！")

st.divider()

JST = timezone(timedelta(hours=9), 'JST')

# ==========================================
# 1. モード選択
# ==========================================
st.sidebar.header("⚙️ 条件・検索設定")
mode = st.sidebar.radio("📍 検索モードを選択", ["今すぐ探す（現在地GPS）", "未来・指定場所で探す"])

target_location = ""
target_datetime = None

if mode == "今すぐ探す（現在地GPS）":
    loc = get_geolocation()
    lat, lon = None, None
    if loc and 'coords' in loc:
        lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
        st.sidebar.success(f"GPS取得: 緯度{lat:.4f} / 経度{lon:.4f}")
    else:
        lat, lon = 35.6812, 139.7671
        st.sidebar.info("現在地未取得のため「東京駅」として計算中")
    
    target_location = "現在地周辺"
    target_datetime = datetime.now(JST)

else:
    target_location = st.sidebar.text_input("検索エリア・駅名を入力", value="渋谷駅")
    selected_date = st.sidebar.date_input("日付を選択", date.today())
    selected_time = st.sidebar.time_input("時間を選択", time(15, 0))
    target_datetime = datetime.combine(selected_date, selected_time).replace(tzinfo=JST)
    lat, lon = 35.6580, 139.7016

# ==========================================
# 2. 用途（目的）選択
# ==========================================
st.sidebar.subheader("🎯 カフェ利用の目的（複数選択可）")
use_pc = st.sidebar.checkbox("💻 PC作業・仕事（コンセント・Wi-Fi重視）")
use_chat = st.sidebar.checkbox("🗣️ 友達と談笑・おしゃべり（話しやすさ・席数重視）")
use_read = st.sidebar.checkbox("📖 読書・勉強（静かさ・落ち着き重視）")
use_quick = st.sidebar.checkbox("⚡️ スキマ時間のサクッと休憩（回転率・手軽さ重視）")

# ==========================================
# 3. スコア計算
# ==========================================
weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
weekday_str = weekday_names[target_datetime.weekday()]
hour = target_datetime.hour
is_weekend = target_datetime.weekday() >= 5

time_score = 0
if is_weekend:
    if 13 <= hour <= 17:
        time_score = 35
        time_msg = "休日ピークタイム（全体的に混雑）"
    elif 11 <= hour <= 12 or 18 <= hour <= 20:
        time_score = 20
        time_msg = "休日準ピークタイム"
    else:
        time_score = 5
        time_msg = "休日の早朝/夜間（狙い目）"
else:
    if 8 <= hour <= 9:
        time_score = 25
        time_msg = "平日朝ラッシュ（駅チカ混雑）"
    elif 12 <= hour <= 13:
        time_score = 30
        time_msg = "平日ランチタイム"
    elif 14 <= hour <= 17:
        time_score = 20
        time_msg = "平日カフェタイム"
    else:
        time_score = 0
        time_msg = "平日のアイドルタイム（空きあり）"

is_rain = False
weather_label = "晴れ/曇り ☀️"
if mode == "今すぐ探す（現在地GPS）":
    try:
        w_res = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true").json()
        w_code = w_res.get("current_weather", {}).get("weathercode", 0)
        if w_code >= 51:
            is_rain = True
            weather_label = "雨・悪天候 🌧️"
    except:
        pass
else:
    is_rain = st.sidebar.checkbox("🌧️ 天気：雨としてシミュレーション")

is_event = st.sidebar.checkbox("🎪 周辺で大規模イベント開催中", value=False)

# ステータス表示
c1, c2, c3 = st.columns(3)
c1.metric("対象エリア", target_location)
c2.metric("対象日時", f"{target_datetime.strftime('%m/%d')}({weekday_str}) {target_datetime.strftime('%H:%M')}")
c3.metric("予想天候", weather_label if mode == "今すぐ探す（現在地GPS）" else ("雨 🌧️" if is_rain else "晴れ ☀️"))

st.caption(f"💡 **時間帯の傾向:** {time_msg}")
st.divider()

# ==========================================
# 4. カフェ判定 ＆ Googleマップ差別化アドバイス
# ==========================================
st.header("🏪 カフェ穴場判定 ＆ 立ち回りナビ")

cafes = [
    {
        "name": "スターバックス（駅ビル直結店）",
        "type": "大手チェーン / 駅直結",
        "dist": "徒歩1分",
        "open_hour": 7, "close_hour": 22,
        "atmosphere": "賑やか・学生〜ビジネス層",
        "is_station": True, "is_far": False,
        "features": {"pc": True, "chat": True, "read": False, "quick": True},
        "turnover_penalty": 10,
        "advice": "駅直結でアクセス抜群ですが、雨天や休日は長蛇の列になりがち。テイクアウト以外の着席利用は非推奨です。"
    },
    {
        "name": "ドトールコーヒーショップ（駅前）",
        "type": "セルフカフェ / カウンター多め",
        "dist": "徒歩2分",
        "open_hour": 6, "close_hour": 21,
        "atmosphere": "サクッと利用・会社員多め",
        "is_station": False, "is_far": False,
        "features": {"pc": False, "chat": True, "read": False, "quick": True},
        "turnover_penalty": -10,
        "advice": "回転率が非常に高いため、一見満席に見えても5分ほど待てば席が空く確率が高い穴場です。"
    },
    {
        "name": "コメダ珈琲店（大通り沿い店）",
        "type": "ボックス席メイン / 滞在型",
        "dist": "徒歩5分",
        "open_hour": 7, "close_hour": 23,
        "atmosphere": "落ち着いたボックス席・ファミリー・シニア層",
        "is_station": False, "is_far": False,
        "features": {"pc": True, "chat": True, "read": True, "quick": False},
        "turnover_penalty": 20,
        "advice": "席の間隔が広くPC作業や長話に最適ですが、滞在時間が長いため一度満席になると回転しません。事前予約か発券機確認を推奨。"
    },
    {
        "name": "隠れ家ロースターカフェ（2階）",
        "type": "個人経営 / 静かな空間",
        "dist": "徒歩8分",
        "open_hour": 11, "close_hour": 19,
        "atmosphere": "静か・大人の隠れ家・おひとり様多め",
        "is_station": False, "is_far": True,
        "features": {"pc": False, "chat": False, "read": True, "quick": False},
        "turnover_penalty": 15,
        "advice": "駅から少し歩くため、雨の日やピーク時でも混雑を回避しやすい最強の穴場です。静かに読書・一人時間を過ごしたい時に◎"
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
    unmatch_reasons = []
    
    if use_pc:
        if cafe["features"]["pc"]: match_reasons.append("電源・Wi-Fi環境あり")
        else: unmatch_reasons.append("PC作業には不向き")
    if use_chat:
        if cafe["features"]["chat"]: match_reasons.append("話しやすい雰囲気")
        else: unmatch_reasons.append("会話メイン向きではない")
    if use_read:
        if cafe["features"]["read"]: match_reasons.append("静かで読書に集中できる")
        else: unmatch_reasons.append("ガヤガヤしやすく読書に非推奨")
    if use_quick:
        if cafe["features"]["quick"]: match_reasons.append("回転が早くサクッと入れる")
        else: unmatch_reasons.append("長居客が多く席確保に時間要す")

    with st.container(border=True):
        col_main, col_match, col_status = st.columns([2, 1.5, 1])

        with col_main:
            st.markdown(f"### ☕ {cafe['name']}")
            st.write(f"特徴: **{cafe['type']}** ／ 距離: **{cafe['dist']}**")
            st.caption(f"🕒 {cafe['open_hour']}:00〜{cafe['close_hour']}:00 ／ 👥 {cafe['atmosphere']}")
            
            # Googleマップとの差別化ポイント：立ち回りアドバイス
            st.info(f"💡 **立ち回りアドバイス:** {cafe['advice']}")

        with col_match:
            st.markdown("**【目的マッチ度】**")
            if not (use_pc or use_chat or use_read or use_quick):
                st.caption("👈 サイドバーで目的を選択してください")
            else:
                for m in match_reasons:
                    st.write(f"✅ {m}")
                for um in unmatch_reasons:
                    st.write(f"⚠️ {um}")

        with col_status:
            if not is_open:
                st.error("🔒 営業時間外")
            elif final_score >= 70:
                st.error(f"混雑度: **{final_score}%**\n\n🚨 満席リスク高")
            elif final_score >= 40:
                st.warning(f"混雑度: **{final_score}%**\n\n⚠️ タイミング次第")
            else:
                st.success(f"混雑度: **{final_score}%**\n\n✨ 空いてる穴場！")

st.divider()

# ==========================================
# 5. スマホ最適化マップ表示
# ==========================================
st.header("🗺️ 周辺マップ")

# スマホ画面でもはみ出さないスリムな地図表示の設定
df_map = pd.DataFrame({'lat': [lat], 'lon': [lon]})

# モバイル用スタイル調整（縦幅を小さめにしてスクロールしやすくする）
st.components.v1.html(
    f"""
    <iframe 
        width="100%" 
        height="280" 
        frameborder="0" 
        scrolling="no" 
        marginheight="0" 
        marginwidth="0" 
        src="https://maps.google.com/maps?q={lat},{lon}&z=15&output=embed">
    </iframe>
    """,
    height=300
)
