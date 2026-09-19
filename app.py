from datetime import datetime
import requests
import streamlit as st
from streamlit_js_eval import get_geolocation

# ページ設定
st.set_page_config(
    page_title="カフェ最適解ナビ - 思考ゼロカフェ選び", page_icon="☕", layout="centered"
)


# ==========================================
# 1. 全国対応：動的店舗データ生成（閉店時間付き）
# ==========================================
def generate_cafes_for_area(target_area):
  """入力された全国の任意のエリア名に合わせて、店舗候補と閉店時間を生成"""
  if not target_area:
    target_area = "指定エリア"

  return [
      {
          "name": f"スターバックスコーヒー {target_area}店",
          "area": target_area,
          "type": "作業向き（コンセント多め）",
          "walk_min": 2,
          "base_crowd": 80,
          "close_hour": 22,  # 22時閉店
      },
      {
          "name": f"ドトールコーヒーショップ {target_area}駅前店",
          "area": target_area,
          "type": "サクッと休憩・回転早い",
          "walk_min": 1,
          "base_crowd": 85,
          "close_hour": 21,  # 21時閉店
      },
      {
          "name": f"地域密着ロースター {target_area}隠れ家カフェ",
          "area": target_area,
          "type": "おしゃべり・落ち着いた空間",
          "walk_min": 7,
          "base_crowd": 40,
          "close_hour": 20,  # 20時閉店（早い）
      },
      {
          "name": f"大手カフェチェーン {target_area}中央通り店",
          "area": target_area,
          "type": "作業向き（コンセント多め）",
          "walk_min": 4,
          "base_crowd": 70,
          "close_hour": 23,  # 23時閉店
      },
  ]


# ==========================================
# 2. 天気情報を自動取得する関数（Open-Meteo API）
# ==========================================
def fetch_weather(lat, lon):
  try:
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    res = requests.get(url, timeout=3).json()
    wcode = res.get("current_weather", {}).get("weathercode", 0)
    # WMO Weather interpretation codes (簡易判定: 51以上は雨・雪など)
    if wcode >= 51:
      return True, "雨・悪天候 🌧️"
    else:
      return False, "晴れ / 曇り ☀️"
  except:
    return False, "晴れ / 曇り ☀️ (取得失敗)"


# ==========================================
# 3. 最適解を計算するロジック（時間・天気・閉店考慮）
# ==========================================
def calculate_best_cafe(
    target_area, target_hour, is_weekend, purpose, is_rain
):
  cafes = generate_cafes_for_area(target_area)
  scored_cafes = []

  for cafe in cafes:
    reasons = []
    is_closed = False

    # ① 閉店時間のチェック
    if target_hour >= cafe["close_hour"]:
      is_closed = True
      reasons.append(
          f"⚠️ 21時以降など、指定時間（{target_hour}時）にはすでに閉店しています"
      )
      scored_cafes.append(
          {
              "cafe": cafe,
              "crowd": 999,
              "reasons": reasons,
              "is_closed": is_closed,
          }
      )
      continue

    # 閉店間際の場合の警告
    if target_hour == cafe["close_hour"] - 1:
      reasons.append("⏰ まもなく閉店時間のためご注意ください")

    score = cafe["base_crowd"]

    # ② 時間帯の補正
    if 12 <= target_hour <= 14:
      score += 20
      reasons.append("お昼時のため全体的に混雑傾向です")
    elif 14 <= target_hour <= 17:
      score += 25
      reasons.append("カフェのピークタイム帯です")
    elif target_hour >= 20:
      score -= 20
      reasons.append("夜遅い時間帯のため比較的落ち着いています")

    # ③ 天気（雨）による補正
    if is_rain:
      if cafe["walk_min"] <= 2:
        score += 30
        reasons.append("🌧️ 雨のため駅近の店舗に人が集中しています")
      else:
        score -= 20
        reasons.append(
            "🌧️ 雨ですが駅から少し離れているため、穴場になりやすいです"
        )
    else:
      if cafe["walk_min"] <= 2:
        score += 10

    # ④ 目的による相性補正
    if purpose == "作業したい" and "作業向き" in cafe["type"]:
      score -= 10
      reasons.append("💻 ご希望の「作業向き」の設備が整っています")
    elif purpose == "サクッと休憩" and "回転早い" in cafe["type"]:
      score -= 15
      reasons.append("⚡ 回転が早いためスムーズに入りやすいです")
    elif purpose == "おしゃべり・ゆっくり" and "落ち着いた空間" in cafe["type"]:
      score -= 15
      reasons.append(
          "🗣️ 落ち着いてお話できるゆったりした空間（おしゃべり向き）"
      )

    final_crowd = max(10, min(99, score))
    scored_cafes.append(
        {"cafe": cafe, "crowd": final_crowd, "reasons": reasons, "is_closed": False}
    )

  # 営業中で混雑度が最も低いものを最適解とする
  open_cafes = [c for c in scored_cafes if not c["is_closed"]]
  if open_cafes:
    open_cafes.sort(key=lambda x: x["crowd"])
    best = open_cafes[0]
  else:
    best = scored_cafes[0]  (# すべて閉店の場合)

  return best, scored_cafes


# ==========================================
# 4. 画面UIの構築
# ==========================================
st.title("☕ カフェ最適解ナビ")
st.caption(
    "「時間・場所・天気」を掛け合わせ、今のあなたにベストな1店舗を提案します。"
)

st.divider()

# --- マスト入力セクション ---
st.subheader("📌 1. 場所・時間・天気の指定")

# GPS取得（自動）
loc = get_geolocation()
default_area = "東京"
lat, lon = 35.6812, 139.7671

if loc and "coords" in loc:
  lat = loc["coords"]["latitude"]
  lon = loc["coords"]["longitude"]
  st.success("📍 現在地のGPS座標を正常に取得しました！")
else:
  st.info(
      "📍 GPS取得を試行中、または手動入力モードです。下のエリア名を自由に変更できます。"
  )

# エリア名入力
target_area = st.text_input(
    "🏠 検索したい駅名・エリアを入力",
    value=default_area,
    help="例: 渋谷、新宿、京都、横浜、梅田など",
)

# 天気の自動取得
is_rain, weather_text = fetch_weather(lat, lon)
st.write(f"☁️ **現在の周辺天気（自動取得）**: {weather_text}")

# 時間の指定（デフォルトは現在時刻）
now = datetime.now()
col_t1, col_t2 = st.columns(2)
with col_t1:
  target_date = st.date_input("📅 日付", value=now.date())
with col_t2:
  target_time = st.time_input("⏰ 時間", value=now.time())

target_hour = target_time.hour
is_weekend = target_date.weekday() >= 5

st.divider()

# 目的の選択
st.subheader("🎯 2. カフェの利用目的")
purpose = st.selectbox(
    "今日のあなたの目的は？",
    ["作業したい", "サクッと休憩", "おしゃべり・ゆっくり"],
)

st.markdown("---")

# 実行ボタン
if st.button("🚀 今すぐベストな店を見る", type="primary", use_container_width=True):
  if not target_area.strip():
    st.warning("エリア名または駅名を入力してください。")
  else:
    best_result, all_results = calculate_best_cafe(
        target_area, target_hour, is_weekend, purpose, is_rain
    )

    if best_result:
      cafe = best_result["cafe"]
      crowd = best_result["crowd"]
      is_closed = best_result["is_closed"]

      st.markdown("---")
      if is_closed:
        st.warning(
            "⚠️ 指定された時間帯は、周辺の主要カフェがすでに閉店している時間帯です。"
        )
      else:
        st.success("✨ **今ここがおすすめです！**")

        st.markdown(f"### 📍 **{cafe['name']}**")
        st.write(
            f"🏃 駅から徒歩 **{cafe['walk_min']}分** ｜ ☕ タイプ："
            f" `{cafe['type']}` ｜ 🌙 閉店時間: **{cafe['close_hour']}時**"
        )

        # 混雑度
        if crowd < 50:
          st.metric(
              label="現在の予想混雑度",
              value=f"{crowd}%（座れる確率が高いです🎉）",
              delta="穴場",
              delta_color="normal",
          )
        else:
          st.metric(
              label="現在の予想混雑度",
              value=f"{crowd}%（やや混み合っています⚠️）",
              delta="注意",
              delta_color="inverse",
          )

      # 理由
      st.markdown("**💡 判定ポイント・理由：**")
      for r in best_result["reasons"]:
        st.write(f"- {r}")

      st.markdown("---")

      # ほかの店舗情報の一覧化（閉店時間も表示）
      st.markdown(f"### 📋 {target_area} 周辺のほかの店舗状況")
      for item in all_results:
        c = item["cafe"]
        c_score = item["crowd"]
        c_closed = item["is_closed"]

        if c_closed:
          status_icon = "❌ 営業時間外"
        elif c_score < 50:
          status_icon = "🟢 空いてます"
        else:
          status_icon = "🔴 混雑中"

        with st.expander(
            f"{status_icon} ｜ {c['name']} （閉店: {c_hour:=c['close_hour']}時）"
        ):
          st.write(f"- 駅から徒歩: **{c['walk_min']}分**")
          st.write(f"- 特徴: `{c['type']}`")
          st.write(f"- 営業時間: **〜 {c['close_hour']}時 まで**")
          if item["reasons"]:
            st.write("- 判定ポイント:")
            for sub_r in item["reasons"]:
              st.write(f"  * {sub_r}")
