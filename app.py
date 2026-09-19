from datetime import datetime, timedelta, timezone, date, time
import json
import os
from google import genai
import requests
import streamlit as st
from streamlit_js_eval import get_geolocation

# ページ設定
st.set_page_config(
    page_title="全国対応 カフェ最適解ナビ",
    page_icon="☕",
    layout="centered",
)

st.title("☕ 全国対応 カフェ最適解ナビ")
st.write(
    "GPSや手動指定からエリア・時間を反映し、天気情報と連動してベストなカフェをご提案します。"
)

# 日本時間を取得（UTC+9）
JST = timezone(timedelta(hours=+9), "JST")
now_jst = datetime.now(JST)


# ==========================================
# 1. 天気自動取得関数（Open-Meteo API活用）
# ==========================================
def get_weather_by_latlon(lat, lon):
  try:
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=weather_code,temperature_2m"
    res = requests.get(url, timeout=5)
    data = res.json()
    code = data["current"]["weather_code"]
    temp = data["current"]["temperature_2m"]

    is_rainy = code >= 51
    weather_desc = (
        "雨・悪天候" if is_rainy else "晴れ・曇り（良好なコンディション）"
    )
    return is_rainy, f"{weather_desc}（気温: {temp}°C）"
  except Exception:
    return False, "天気データの取得に失敗しました（通常モードで計算します）"


# ==========================================
# 2. Gemini APIによる全国のリアル店舗データ取得
# ==========================================
def fetch_cafes_by_ai(area_name, is_rainy, current_hour):
  api_key = os.environ.get("GEMINI_API_KEY")
  if not api_key:
    return (
        None,
        "APIキー（GEMINI_API_KEY）が設定されていないため、店舗情報を取得できません。",
    )

  try:
    client = genai.Client()
    prompt = f"""
        あなたは日本全国の地理とカフェ事情に精通したプロフェッショナルです。
        「{area_name}」の周辺に実在する代表的なカフェ（大手チェーン、人気店、個人店など）を3店舗挙げてください。
        現在の状況は「{current_hour}時」、天気はクラウド基準で「{'雨・悪天候' if is_rainy else '晴れ・曇り'}」です。
        
        以下のJSON形式（マークダウンのコードブロックなし、プレーンなJSONのみ）で正確に出力してください。
        {{
          "area_comment": "{area_name}周辺の現在の混雑傾向やイベント状況に関する一言解説",
          "cafes": [
            {{
              "name": "実在する店舗名1",
              "address": "おおよその住所または立地",
              "type": "作業向き / サクッと休憩 / おしゃべり・落ち着いた空間 のいずれか",
              "walk_min": 駅や中心地からの徒歩分数(整数),
              "base_crowd": 50 (基本の混雑度 0〜100)
            }}
          ]
        }}
        """

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
    )

    text = response.text.strip()
    if "```json" in text:
      text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
      text = text.split("```")[1].split("```")[0].strip()

    data = json.loads(text)
    return data, None
  except Exception as e:
    return None, f"データ取得エラー: {e}"


# ==========================================
# 3. 画面UI：モード選択 ＆ 入力フォーム
# ==========================================
st.subheader("📍 検索モードの選択")
mode = st.radio(
    "検索方法を選んでください",
    [
        "📍 【今すぐ】GPS現在地と現在時刻を自動反映",
        "🚃 【未来・指定】場所・日付・時間を自由に選択",
    ],
    horizontal=False,
)

target_area = ""
target_datetime = now_jst
is_rainy = False
weather_info_text = ""

if "今すぐ" in mode:
  st.write("🔄 GPSから現在地を取得中...")
  loc = get_geolocation()

  if loc and "coords" in loc:
    lat = loc["coords"]["latitude"]
    lon = loc["coords"]["longitude"]
    st.success(f"GPS取得成功（緯度: {lat:.4f}, 経度: {lon:.4f}）")
    # 緯度経度からおおよそのエリア名を指定できるようにする、または現在地周辺として入力欄を用意
    target_area = st.text_input(
        "🏠 あなたの現在地（駅名・エリア名を入力してください）",
        value="江東区東陽町周辺",
        help="GPS座標から自動で場所名が取れないため、お手数ですが現在の最寄駅やエリア名をご入力ください",
    )
    is_rainy, weather_info_text = get_weather_by_latlon(lat, lon)
  else:
    st.warning("⚠️ スマホのGPSがうまく取得できませんでした。下のフォームに現在のエリア名を入力してください。")
    target_area = st.text_input("🔍 現在のエリア・駅名を入力", value="新宿駅周辺")
    is_rainy, weather_info_text = get_weather_by_latlon(35.6894, 139.6917)

  target_datetime = now_jst
  st.info(
      f"🕒 **現在時刻**：{target_datetime.strftime('%Y年%m月%d日 %H:%M')} ｜ ☁️ **天気**：{weather_info_text}"
  )

else:
  st.markdown("---")
  target_area = st.text_input(
      "🔍 行きたい駅名・エリア名を入力",
      "新宿駅周辺",
      help="日本全国どの都道府県・駅名でもOKです",
  )
  
  # 日付選択
  selected_date = st.date_input("📅 日付を選択", date.today())
  
  # センスの良い時間選択
  time_options = {
      "07:00 (早朝・開店直後)": 7,
      "08:00 (朝活・通勤前)": 8,
      "09:00 (午前・比較的落ち着き)": 9,
      "10:00 (午前・ティータイム前)": 10,
      "11:00 (お昼直前・少しずつ混雑)": 11,
      "12:00 (ランチタイム・満席注意)": 12,
      "13:00 (ランチピーク・混雑)": 13,
      "14:00 (午後のカフェタイム開始)": 14,
      "15:00 (午後一番の混雑ピーク)": 15,
      "16:00 (夕方・少しずつ空き始める)": 16,
      "17:00 (夕方・仕事帰りの流れ込み)": 17,
      "18:00 (夜・ディナー前の一休み)": 18,
      "19:00 (夜・落ち着く時間帯)": 19,
      "20:00 (夜遅め・穴場タイム)": 20,
      "21:00 (夜間・静かに過ごせる)": 21,
  }
  
  selected_time_label = st.selectbox("⏰ 時間帯を選択", list(time_options.keys()), index=8)
  selected_hour = time_options[selected_time_label]
  
  target_datetime = datetime.combine(selected_date, time(selected_hour, 0)).replace(tzinfo=JST)

  is_rainy, weather_info_text = get_weather_by_latlon(35.6894, 139.6917)
  st.info(f"☁️ **天気予報データ**： {weather_info_text}")

st.markdown("---")

purpose = st.selectbox(
    "🎯 今日の目的は？", ["作業したい", "サクッと休憩", "おしゃべり・ゆっくり"]
)


# ==========================================
# 4. 実行ボタンとロジック処理
# ==========================================
if st.button("🚀 ベストなカフェを探す", type="primary", use_container_width=True):
  current_hour = target_datetime.hour
  
  with st.spinner(f"「{target_area}」の店舗データとリアルタイム状況を分析中..."):
    ai_data, err = fetch_cafes_by_ai(target_area, is_rainy, current_hour)

    if err or not ai_data:
      st.error(err)
    else:
      st.markdown(f"### 📍 「{target_area}」の分析結果")
      st.write(f"💡 {ai_data.get('area_comment', '')}")
      st.markdown(f"🗓️ 指定日時: **{target_datetime.strftime('%Y年%m月%d日 %H:00')}**")
      st.markdown("---")

      cafes = ai_data.get("cafes", [])
      scored_list = []

      for cafe in cafes:
        score = cafe.get("base_crowd", 50)
        reasons = []

        # 時間帯による補正
        if 20 <= current_hour or current_hour < 8:
          score -= 35
          reasons.append("夜遅い時間帯のため、客足が引いて比較的空いています（穴場）")
        elif 12 <= current_hour <= 14:
          score += 15
          reasons.append("お昼時のため混雑しやすい時間帯です")
        elif 14 <= current_hour <= 18:
          score += 25
          reasons.append("カフェのピークタイムのため混み合います")

        # 天気（雨）による補正
        walk = cafe.get("walk_min", 3)
        if is_rainy:
          if walk <= 2:
            score += 20
            reasons.append("雨天のため、駅から近い店舗に人が集中しています")
          else:
            score -= 15
            reasons.append("駅から少し歩くため、雨の日でも比較的空いています")

        # 目的とのマッチング補正
        c_type = cafe.get("type", "")
        if purpose in c_type:
          score -= 15
          reasons.append(f"ご希望の「{purpose}」にぴったりのタイプです")

        final_score = max(10, min(99, score))
        scored_list.append(
            {"cafe": cafe, "crowd": final_score, "reasons": reasons}
        )

      scored_list.sort(key=lambda x: x["crowd"])

      if scored_list:
        best = scored_list[0]
        bc = best["cafe"]

        st.success("✨ **今ここがおすすめです！**")
        st.markdown(f"### 📍 **{bc['name']}**")
        st.write(
            f"🚶 徒歩 **{bc['walk_min']}分** ｜ ☕ タイプ：`{bc['type']}` ｜"
            f" 📍 {bc['address']}"
        )

        if best["crowd"] < 50:
          st.metric(
              label="予想混雑度",
              value=f"{best['crowd']}%（座れる確率が高いです🎉）",
              delta="穴場",
          )
        else:
          st.metric(
              label="予想混雑度",
              value=f"{best['crowd']}%（やや混み合っています⚠️）",
              delta="注意",
              delta_color="inverse",
          )

        st.markdown("**💡 おすすめの理由：**")
        for r in best["reasons"]:
          st.write(f"- {r}")

        st.markdown("---")
        st.markdown("### 📋 周辺のほかの店舗状況")
        for item in scored_list[1:]:
          c = item["cafe"]
          c_score = item["crowd"]
          status_icon = "🟢 空いてます" if c_score < 50 else "🔴 混雑中"
          with st.expander(
              f"{status_icon} ｜ {c['name']} （予想混雑度: {c_score}%）"
          ):
            st.write(f"- 徒歩: **{c['walk_min']}分**")
            st.write(f"- 特徴: `{c['type']}` / 住所: {c['address']}")
            for sub_r in item["reasons"]:
              st.write(f"  * {sub_r}")
