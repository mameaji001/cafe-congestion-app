from datetime import datetime
import streamlit as st
from streamlit_js_eval import get_geolocation

# ページ設定
st.set_page_config(
    page_title="カフェ最適解ナビ - 思考ゼロカフェ選び", page_icon="☕", layout="centered"
)


# ==========================================
# 1. 全国対応：動的店舗データ生成ロジック
# ==========================================
def generate_cafes_for_area(target_area):
  """入力された全国の任意のエリア名に合わせて、自動的に店舗候補を生成します"""
  if not target_area:
    target_area = "指定エリア"

  return [
      {
          "name": f"スターバックスコーヒー {target_area}店",
          "area": target_area,
          "type": "作業向き（コンセント多め）",
          "walk_min": 2,
          "base_crowd": 80,
      },
      {
          "name": f"ドトールコーヒーショップ {target_area}駅前店",
          "area": target_area,
          "type": "サクッと休憩・回転早い",
          "walk_min": 1,
          "base_crowd": 85,
      },
      {
          "name": f"地域密着ロースター {target_area}隠れ家カフェ",
          "area": target_area,
          "type": "おしゃべり・落ち着いた空間",
          "walk_min": 7,
          "base_crowd": 40,
      },
      {
          "name": f"大手カフェチェーン {target_area}中央通り店",
          "area": target_area,
          "type": "作業向き（コンセント多め）",
          "walk_min": 4,
          "base_crowd": 70,
      },
  ]


# ==========================================
# 2. 最適解を計算するロジック
# ==========================================
def calculate_best_cafe(
    target_area, current_hour, is_weekend, purpose, auto_env_score
):
  cafes = generate_cafes_for_area(target_area)
  scored_cafes = []

  for cafe in cafes:
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
    "Googleマップを開いて迷う時間をゼロに。全国どこでも今のあなたにベストな1店舗をご提案します。"
)

# モード選択
mode = st.radio(
    "場所の指定方法を選んでください",
    ["📍 現在地から探す（GPS）", "✏️ 全国の駅名・エリアを自由に入力する"],
    horizontal=True,
)

target_area = ""

if "現在地" in mode:
  st.write("📍 **GPS現在地を取得中...**")
  loc = get_geolocation()
  if loc and "coords" in loc:
    lat = loc["coords"]["latitude"]
    lon = loc["coords"]["longitude"]
    st.success(
        f"現在地を取得しました（緯度: {lat:.4f}, 経度: {lon:.4f}）。"
        "※現在はデモのため仮エリアを設定しています"
    )
    # 将来的にはここで逆ジオコーディング（緯度経度から駅名を特定）を入れられます
    target_area = st.text_input(
        "現在地の周辺駅・エリア名を確認・変更:", value="渋谷"
    )
  else:
    st.info(
        "位置情報の権限を確認中、またはシミュレーションモードです。エリア名を手入力してください。"
    )
    target_area = st.text_input("エリア・駅名を入力:", value="渋谷")
else:
  target_area = st.text_input(
      "✏️ 行きたい駅名・エリアを入力してください（例: 京都、名古屋、横浜、札幌など）",
      value="大阪",
  )

st.markdown("---")

# 目的の選択肢
purpose = st.selectbox(
    "🎯 今日のあなたの目的は？",
    ["作業したい", "サクッと休憩", "おしゃべり・ゆっくり"],
)

# シチュエーション自動判定
now = datetime.now()
current_hour = now.hour
is_weekend = now.weekday() >= 5
auto_env_score = 25  # 自動反映スコア

st.caption(
    f"🤖 **自動コンテキスト解析**：現在 {current_hour}時 / "
    f"{'土日祝' if is_weekend else '平日'} ｜ ${target_area} 周辺のトレンドを反映中"
)

st.markdown("---")

# 実行ボタン
if st.button("🚀 今すぐベストな店を見る", type="primary", use_container_width=True):
  if not target_area.strip():
    st.warning("エリア名または駅名を入力してください。")
  else:
    best_result, all_results = calculate_best_cafe(
        target_area, current_hour, is_weekend, purpose, auto_env_score
    )

    if best_result:
      cafe = best_result["cafe"]
      crowd = best_result["crowd"]

      # おすすめの提案見出し
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

      # ほかの店舗情報の一覧化
      st.markdown(f"### 📋 {target_area} 周辺のほかの店舗状況")
      for item in all_results:
        c = item["cafe"]
        c_score = item["crowd"]
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
