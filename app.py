import streamlit as st
import pandas as pd
import requests
from datetime import datetime, date, time
from streamlit_js_eval import get_geolocation

# ページ設定
st.set_page_config(page_title="未来予測＆目的別 カフェ混雑ナビ", page_icon="☕", layout="wide")

st.title("☕ 未来予測 ＆ 目的別 カフェ混雑・穴場ナビ")
st.caption("「いつ・どこで・何のために」カフェを探すかに合わせて、混雑度と最適な店舗を予測・判定します。")

st.divider()

# ==========================================
# 1. 「いつ・どこで」モード選択（現在 vs 未来）
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
        lat, lon = 35.6812, 139.7671  # デフォルト（東京駅）
        st.sidebar.info("現在地未取得のため「東京駅」として計算中")
    
    target_location = "現在地周辺"
    target_datetime = datetime.now()

else:  # 未来・指定場所で探す
    target_location = st.sidebar.text_input("検索エリア・駅名を入力", value="渋谷駅")
    selected_date = st.sidebar.date_input("日付を選択", date.today())
    selected_time = st.sidebar.time_input("時間を選択", time(15, 0))
    target_datetime = datetime.combine(selected_date, selected_time)
    lat, lon = 35.6580, 139.7016  # 例: 渋谷周辺座標

# ==========================================
# 2. 用途（目的）の選択
# ==========================================
st.sidebar.subheader("🎯 カフェ利用の目的（複数選択可）")
use_pc = st.sidebar.checkbox("💻 PC作業・仕事（コンセント・Wi-Fi重視）")
use_chat = st.sidebar.checkbox("🗣️ 友達と談笑・おしゃべり（話しやすさ・席数重視）")
use_read = st.sidebar.checkbox("📖 読書・勉強（静かさ・落ち着き重視）")
use_quick = st.sidebar.checkbox("⚡️ スキマ時間のサクッと休憩（回転率・手軽さ重視）")

# ==========================================
# 3. 日時・天気・環境スコアの計算
# ==========================================
weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
weekday_str = weekday_names[target_datetime.weekday()]
hour = target_datetime.hour
is_weekend = target_datetime.weekday() >= 5

# 時間帯スコア
time_score = 0
if is_weekend:
    if 13 <= hour <= 17:
        time_score = 35
        time_msg = "休日ピークタイム（どこも混雑しやすい）"
    elif 11 <= hour <= 12 or 18 <= hour <= 20:
        time_score = 20
        time_msg = "休日準ピークタイム"
    else:
        time_score = 5
        time_msg = "休日の早朝/夜間（比較的空いています）"
else:
    if 8 <= hour <= 9:
        time_score = 25
        time_msg = "平日朝ラッシュ（駅チカ・大手チェーン混雑）"
    elif 12 <= hour <= 13:
        time_score = 30
        time_msg = "平日ランチタイム（混雑）"
    elif 14 <= hour <= 17:
        time_score = 20
        time_msg = "平日カフェタイム・打合せ利用"
    else:
        time_score = 0
        time_msg = "平日のアイドルタイム（狙い目）"

# 天気自動取得（現在の場合のみ取得、未来は手動シミュレーション）
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

# メインパネルのステータス表示
c1, c2, c3 = st.columns(3)
c1.metric("対象エリア", target_location)
c2.metric("対象日時", f"{target_datetime.strftime('%m/%d')}({weekday_str}) {target_datetime.strftime('%H:%M')}")
c3.metric("予想天候", weather_label if mode == "今すぐ探す（現在地GPS）" else ("雨 🌧️" if is_rain else "晴れ ☀️"))

st.caption(f"💡 **時間帯の背景:** {time_msg}")
st.divider()

# ==========================================
# 4. 周辺カフェリスト ＆ 目的マッチング＆混雑判定
# ==========================================
st.header("🏪 周辺カフェの混雑予想 ＆ 目的適性判定")

# 店舗のモデルデータ（属性と特徴）
cafes = [
    {
        "name": "スターバックス（駅ビル直結店）",
        "type": "大手チェーン / 駅直結",
        "dist": "徒歩1分",
        "is_station": True, "is_far": False,
        "features": {"pc": True, "chat": True, "read": False, "quick": True},
        "turnover_penalty": 10
    },
    {
        "name": "ドトールコーヒーショップ（駅前）",
        "type": "セルフカフェ / カウンター多め",
        "dist": "徒歩2分",
        "is_station": False, "is_far": False,
        "features": {"pc": False, "chat": True, "read": False, "quick": True},
        "turnover_penalty": -10
    },
    {
        "name": "コメダ珈琲店（大通り沿い店）",
        "type": "ボックス席メイン / 滞在型",
        "dist": "徒歩5分",
        "is_station": False, "is_far": False,
        "features": {"pc": True, "chat": True, "read": True, "quick": False},
        "turnover_penalty": 20
    },
    {
        "name": "隠れ家ロースターカフェ（2階）",
        "type": "個人経営 / 静かな空間",
        "dist": "徒歩8分",
        "is_station": False, "is_far": True,
        "features": {"pc": False, "chat": False, "read": True, "quick": False},
        "turnover_penalty": 15
    }
]

for cafe in cafes:
    # --- A. 混雑スコア計算 ---
    score = 15 + time_score
    if is_rain:
        if cafe["is_station"]: score += 30
        elif cafe["is_far"]: score -= 20
    else:
        if cafe["is_station"]: score += 15
    
    score += cafe["turnover_penalty"]
    if is_event: score += 25
    final_score = max(10, min(99, score))

    # --- B. 目的マッチング判定 ---
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

    # --- C. 表示作成 ---
    with st.container(border=True):
        col_main, col_match, col_status = st.columns([2, 1.5, 1])

        with col_main:
            st.markdown(f"### ☕ {cafe['name']}")
            st.write(f"特徴: **{cafe['type']}** ／ 距離: **{cafe['dist']}**")
            
            # 理由解説
            reasons = []
            if is_rain and cafe["is_station"]: reasons.append("🌧️ 雨で駅直結に集中")
            elif is_rain and cafe["is_far"]: reasons.append("🌧️ 雨のため徒歩移動店舗は空き気味")
            if is_weekend and 13 <= hour <= 17: reasons.append("休日ピーク帯")
            if reasons:
                st.caption("【混雑理由】 " + " / ".join(reasons))

        with col_match:
            st.markdown("**【あなたの目的との相性】**")
            if not (use_pc or use_chat or use_read or use_quick):
                st.caption("👈 サイドバーで目的を選ぶと判定されます")
            else:
                for m in match_reasons:
                    st.write(f"✅ {m}")
                for um in unmatch_reasons:
                    st.write(f"⚠️ {um}")

        with col_status:
            if final_score >= 70:
                st.error(f"混雑度: **{final_score}%**\n\n🚨 満席リスク高")
            elif final_score >= 40:
                st.warning(f"混雑度: **{final_score}%**\n\n⚠️ タイミング次第")
            else:
                st.success(f"混雑度: **{final_score}%**\n\n✨ 空いてる狙い目！")

st.divider()

# マップ表示
st.header("🗺️ 周辺エリアマップ")
df_map = pd.DataFrame({'lat': [lat], 'lon': [lon]})
st.map(df_map, zoom=14)
