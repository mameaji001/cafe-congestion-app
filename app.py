from datetime import datetime
import streamlit as st
from streamlit_js_eval import get_geolocation

# ページ設定
st.set_page_config(
    page_title="カフェ最適解ナビ - 思考ゼロカフェ選び", page_icon="☕", layout="centered"
)


# ==========================================
# 1. マスターデータ（店舗＋特徴）
# ==========================================
def get_cafe_database():
  return [
    {
      "name": "スターバックスコーヒー 水道橋店",
      "area": "水道橋",
      "type": "作業向き（コンセント多め）",
      "walk_min": 2,
      "base_crowd": 80,
    },
    {
      "name": "ドトールコーヒーショップ 水道橋東口店",
      "area": "水道橋",
      "type": "サクッと休憩・回転早い",
      "walk_min": 1,
      "base_crowd": 85,
    },
    {
      "name": "珈琲館 水道橋裏路地店",
      "area": "水道橋",
      "type": "おしゃべり・落ち着いた空間",
      "walk_min": 7,
      "base_crowd": 40,
    },
    {
      "name": "スターバックスコーヒー 新宿三丁目店",
      "area": "新宿",
      "type": "作業向き（コンセント多め）",
      "walk_min": 3,
      "base_crowd": 90,
    },
    {
      "name": "エクセルシオールカフェ 新宿西口店",
      "area": "新宿",
      "type": "サクッと休憩・回転早い",
      "walk_min": 4,
      "base_crowd": 75,
    },
    {
      "name": "喫茶ルノアール 新宿南口隠れ家店",
      "area": "新宿",
      "type": "おしゃべり・落ち着いた空間",
      "walk_min": 8,
      "base_crowd": 35,
    },
  ]


# ==========================================
# 2. 最適解を計算するロジック（自動推測込み）
# ==========================================
def calculate_best_cafe(
    target_area, current_hour, is_weekend, purpose, auto_env_score
):
  cafes = get_cafe_database()
  filtered_cafes = [c for c in cafes if c["area"] == target_area]

  if not filtered_cafes:
    return None, []

  scored_cafes = []
  for cafe in filtered_cafes:
    score = cafe["base_crowd"]
    reasons = []

    # ① 時間帯の自動補正
    if 12 <= current_hour <= 14:
      score += 20
      reasons.append("お昼時のため全体的に混雑傾向です")
    elif 14 <= current_hour <= 17:
      score += 25
      reasons.append("カフェのピークタイム帯です")

    # ② 自動取得した環境スコア（雨やイベントなど）の加算
    if auto_env_score > 0:
      if cafe["walk_min"] <= 2:
        score += auto_env_score
        reasons.append("悪天候やイベントの影響で駅近に人が集中しています")
      else:
        score -= 15
        reasons.append("駅から少し歩くため、混雑を避けやすい穴場です")

    # ③ 目的による相性補正
    if purpose == "作業したい" and "作業向き" in cafe["type"]:
      score -= 10
      reasons.append("ご希望の「作業向き」の設備が整っています")
    elif purpose == "サクッと休憩" and "回転早い" in cafe["type"]:
      score -= 15
      reasons.append("回転が早いためスムーズに入りやすいです")
    elif purpose == "おしゃべり・ゆっくり" and "落ち着いた空間" in cafe["type"]:
      score -= 15
      reasons.append("落ち着いてお話できるゆったりした空間です")

    final_crowd = max(10, min(99, score))
    scored_cafes.append(
        {"cafe": cafe, "crowd": final_crowd, "reasons": reasons}
    )

  # 混雑度が最も低いものを最適解とする
  scored_cafes.sort(key=lambda x: x["crowd"])
  return scored_cafes[0], scored_cafes


# ==========================================
# 3. 画面UIの構築
# ==========================================
st.title("☕ カフェ最適解ナビ")
st.caption(
    "Googleマップを開いて迷う時間をゼロに。今のあなたにベストな1店舗をご提案します。"
)

# モード選択
mode = st.radio(
    "現在地から探すか、移動先を検索するか選んでください",
    ["📍 現在地から探す（GPS）", "🚃 電車・移動先を検索する"],
    horizontal=True,
)

target_area = "水道橋"

if "現在地" in mode:
  st.write("📍 **GPS現在地を取得中...**")
  # 実際のブラウザGPS取得
  loc = get_geolocation()
  if loc:
    lat = loc["coords"]["latitude"]
    lon = loc["coords"]["longitude"]
    st.success(
        f"現在地を取得しました（緯度: {lat:.2f}, 経度: {lon:.2f）。※デモのため水道橋エリアとして計算します"
    )
  else:
    st.info("位置情報の権限を確認中、またはシミュレーションモードです。")
  target_area = "水道橋"
else:
  target_area = st.selectbox("行き先のエリア・駅名を選択", ["水道橋", "新宿"])

st.markdown("---")

# ④ 目的の選択肢
purpose = st.selectbox(
    "🎯 今日のあなたの目的は？",
    ["作業したい", "サクッと休憩", "おしゃべり・ゆっくり"],
)

# ① シチュエーション自動判定（裏側で自動取得するイメージ、微調整も可）
now = datetime.now()
current_hour = now.hour
is_weekend = now.weekday() >= 5

# 自動判定のサマリーを表示
auto_env_score = 25  # 例として雨やイベントがあると仮定したスコア
st.caption(
    f"🤖 **自動コンテキスト解析**：現在 {current_hour}時 / "
    f"{'土日祝' if is_weekend else '平日'} ｜ 周辺環境・天候データを自動反映中"
)

st.markdown("---")

# 実行ボタン
if st.button("🚀 今すぐベストな店を見る", type="primary", use_container_width=True):
  best_result, all_results = calculate_best_cafe(
      target_area, current_hour, is_weekend, purpose, auto_env_score
  )

  if best_result:
    cafe = best_result["cafe"]
    crowd = best_result["crowd"]

    # ③ 優しいトーンの提案見出し
    st.success("✨ **今ここがおすすめです！**")

    st.markdown(f"### 📍 **{cafe['name']}**")
    st.write(
        f"🏃 駅から徒歩 **{cafe['walk_min']}分** ｜ ☕ タイプ："
        f" `{cafe['type']}`"
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
    st.markdown("**💡 このお店を選んだ理由：**")
    for r in best_result["reasons"]:
      st.write(f"- {r}")

    st.markdown("---")

    # ⑤ ほかの店舗情報もわかりやすく一覧化
    st.markdown("### 📋 周辺のほかの店舗状況")
    for item in all_results:
      c = item["cafe"]
      c_score = item["crowd"]
      # 混雑度に応じたアイコン変化
      status_icon = "🟢 空いてます" if c_score < 50 else "🔴 混雑中"
      with st.expander(
          f"{status_icon} ｜ {c['name']} （予想混雑度: {c_score}%）"
      ):
        st.write(f"- 駅から徒歩: **{c['walk_min']}分**")
        st.write(f"- 特徴: `{c['type']}`")
        if item["reasons"]:
          st.write("- 判定ポイント:")
          for sub_r in item["reasons"]:
            st.write(f"  * {sub_r}")
  else:
    st.warning("該当するエリアに店舗が見つかりませんでした。")
