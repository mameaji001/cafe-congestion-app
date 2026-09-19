from datetime import datetime
import streamlit as st

# ページ設定
st.set_page_config(
    page_title="カフェ最適解ナビ - 思考ゼロカフェ選び", page_icon="☕", layout="centered"
)


# ==========================================
# 1. マスターデータ（店舗＋トレンド・イベント情報）
# ==========================================
# 本来はDBや外部ファイルから取得しますが、まずはモックとして定義
def get_cafe_database():
  return [
    {
      "name": "スターバックスコーヒー 水道橋店",
      "area": "水道橋",
      "type": "チェーン（作業多め）",
      "walk_min": 2,
      "base_crowd": 80,
    },
    {
      "name": "ドトールコーヒーショップ 水道橋東口店",
      "area": "水道橋",
      "type": "チェーン（回転早い）",
      "walk_min": 1,
      "base_crowd": 85,
    },
    {
      "name": "珈琲館 水道橋裏路地店",
      "area": "水道橋",
      "type": "個人・落ち着いたカフェ",
      "walk_min": 7,
      "base_crowd": 40,
    },
    {
      "name": "スターバックスコーヒー 新宿三丁目店",
      "area": "新宿",
      "type": "チェーン（作業多め）",
      "walk_min": 3,
      "base_crowd": 90,
    },
    {
      "name": "エクセルシオールカフェ 新宿西口店",
      "area": "新宿",
      "type": "チェーン（回転早い）",
      "walk_min": 4,
      "base_crowd": 75,
    },
    {
      "name": "喫茶ルノアール 新宿南口隠れ家店",
      "area": "新宿",
      "type": "個人・落ち着いたカフェ",
      "walk_min": 8,
      "base_crowd": 35,
    },
  ]


# ==========================================
# 2. 思考ゼロの最適解を計算するロジック
# ==========================================
def calculate_best_cafe(
    target_area, current_hour, is_weekend, is_raining, has_event, has_collab
):
  cafes = get_cafe_database()
  # エリアで絞り込み
  filtered_cafes = [c for c in cafes if c["area"] == target_area]

  if not filtered_cafes:
    return None, "指定されたエリアのデータがまだありません。"

  scored_cafes = []
  for cafe in filtered_cafes:
    score = cafe["base_crowd"]
    reasons = []

    # ① 時間帯の補正
    if 12 <= current_hour <= 14:
      score += 20
      reasons.append("お昼時のため全体的に混雑")
    elif 14 <= current_hour <= 17:
      score += 30
      reasons.append("カフェのピークタイム")

    # ② 雨の日の補正（駅直結・駅チカは激混み、遠くは穴場）
    if is_raining:
      if cafe["walk_min"] <= 2:
        score += 25
        reasons.append("雨天のため駅近に人が集中")
      else:
        score -= 25
        reasons.append("雨の日でも駅から歩くため比較的穴場")

    # ③ イベント・ライブ・試合の補正
    if has_event:
      score += 35
      reasons.append("周辺エリアで大規模イベント開催中")

    # ④ 新商品・コラボ補正（チェーン店に大打撃、個人店は相対的に安全）
    if has_collab and "チェーン" in cafe["type"]:
      score += 40
      reasons.append("人気コラボ・新商品の影響で大混雑")
    elif has_collab:
      score -= 10
      reasons.append("コラボの影響を受けにくい隠れ家傾向")

    # スコアの上下限調整 (0〜100%)
    final_crowd = max(10, min(99, score))
    scored_cafes.append(
        {"cafe": cafe, "crowd": final_crowd, "reasons": reasons}
    )

  # 「最も空いている（混雑度が低い）最適解」を1つだけ選ぶ！
  best_choice = min(scored_cafes, key=lambda x: x["crowd"])
  return best_choice, scored_cafes


# ==========================================
# 3. 画面UIの構築
# ==========================================
st.title("☕ カフェ最適解ナビ")
st.caption(
    "Googleマップを開いて迷う時間をゼロに。今のあなたにベストな1店舗をズバッと提案します。"
)

# モード選択（GPS vs 検索）
mode = st.radio(
    "現在地を選んでください", ["📍 今すぐここから探す（GPS想定）", "電車・移動先を検索する"], horizontal=True
)

target_area = "水道橋"
if "検索" in mode:
  target_area = st.selectbox("行き先のエリア・駅名", ["水道橋", "新宿"])
else:
  st.info("📍 現在地を検知しました：**水道橋エリア** と判定")
  target_area = "水道橋"

# 現在の自動取得データ ＋ トレンドの仮設定
now = datetime.now()
current_hour = st.slider(
    "時間帯（シミュレーション用）", 8, 22, now.hour
)
is_weekend = st.checkbox("土日祝日ですか？", value=(now.weekday() >= 5))

st.markdown("---")
st.subheader("⚡ 本日の周辺シチュエーション（自動推測＆手動調整）")
col1, col2, col3 = st.columns(3)
with col1:
  is_raining = st.checkbox("雨が降っている", value=False)
with col2:
  has_event = st.checkbox("近くで大型イベントあり", value=True)
with col3:
  has_collab = st.checkbox("有名コラボ・新商品発売日", value=False)

st.markdown("---")

# 実行ボタン
if st.button("🚀 今行くべきベストな店を決定する", type="primary", use_container_width=True):
  best_result, all_results = calculate_best_cafe(
      target_area, current_hour, is_weekend, is_raining, has_event, has_collab
  )

  if best_result:
    cafe = best_result["cafe"]
    crowd = best_result["crowd"]

    # 思考ゼロの最強の1店舗をズバッと大きく表示
    st.success("✨ 【あなたへの最適解】この店に直行せよ！")

    st.markdown(f"### 📍 **{cafe['name']}**")
    st.write(
        f"🏃 駅から徒歩 **{cafe['walk_min']}分** ｜ ☕ タイプ：`{cafe['type']}`"
    )

    # 混雑度の表示
    if crowd < 50:
      st.metric(
          label="予想混雑度",
          value=f"{crowd}%（座れる確率が高いです🎉）",
          delta="穴場",
          delta_color="normal",
      )
    else:
      st.metric(
          label="予想混雑度",
          value=f"{crowd}%（少し急ぎましょう⚠️）",
          delta="注意",
          delta_color="inverse",
      )

    # 選ばれた理由
    st.markdown("**💡 この店が選ばれた理由：**")
    for r in best_result["reasons"]:
      st.write(f"- {r}")

    with st.expander("🔍 周辺の他の店舗の状況（比較用）"):
      for item in all_results:
        c = item["cafe"]
        st.write(
            f"- **{c['name']}** (徒歩{c['walk_min']}分): 予想混雑度 **"
            f" {item['crowd']}%**"
        )
  else:
    st.warning("該当するエリアに店舗が見つかりませんでした。")
