import streamlit as st
import datetime
import os
import json
from google import genai

# Streamlit ページ設定
st.set_page_config(page_title="全国対応 カフェ混雑・穴場予測AIナビ", layout="centered")

st.title("☕ 全国対応 カフェ混雑・穴場予測AIナビ")
st.write("日本全国の任意の駅名・エリアを入力し、AIのイベント予測や天候（雨など）を反映したリアルタイム混雑・穴場予測を行います。")

# --- 1. エリア・条件入力エリア ---
st.subheader("⚙️ 検索条件の設定")

target_area = st.text_input("検索したい駅名・エリアを入力（例：札幌駅、梅田、博多、名古屋市栄）", "渋谷駅周辺")
is_rainy = st.checkbox("🌧️ 当日は雨（または雨天予報）", value=False)

# --- 2. Gemini APIを活用したエリア別カフェ＆イベント情報の自動解析 ---
def fetch_cafes_and_events_by_ai(area_name, rainy_flag):
    """
    Gemini APIを使用して、指定された日本全国のエリアにある実在のカフェ情報と、
    周辺のイベント状況・混雑度を動的に取得する
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "APIキーが設定されていないため、店舗情報を取得できません。"
    
    try:
        client = genai.Client()
        prompt = f"""
        あなたは日本全国の地理とカフェ事情に精通したアシスタントです。
        「{area_name}」の周辺に実在する代表的なカフェ（大手チェーンや有名店など）を3〜4店舗挙げてください。
        また、{area_name}周辺で現在カフェの混雑に影響するようなイベント（ライブ、お祭り、試合など）の有無を推測してください。
        
        以下のJSON形式（マークダウンのコードブロックなし、プレーンなJSONのみ）で回答してください。
        {{
          "has_event": trueまたはfalse,
          "event_comment": "イベントの有無や理由に関する説明文",
          "cafes": [
            {{
              "name": "実在する店舗名1",
              "address": "おおよその住所",
              "station_direct": trueまたはfalse (駅直結または駅ビル内か),
              "walk_minutes": 駅からの徒歩分数(整数),
              "base_congestion": 50
            }}
          ]
        }}
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
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
        return None, f"データ取得中にエラーが発生しました: {e}"

# --- 3. 予測実行ボタン ---
if st.button("🚀 全国エリアの混雑・穴場を予測する"):
    with st.spinner(f"「{target_area}」周辺の実在カフェデータとイベント状況をAIが分析中..."):
        ai_data, err = fetch_cafes_and_events_by_ai(target_area, is_rainy)
        
        if err or not ai_data:
            st.error(f"エラーが発生しました: {err}")
        else:
            st.subheader(f"📍 「{target_area}」の分析結果")
            
            if ai_data.get("has_event"):
                st.warning(f"⚠️ **周辺イベント情報**: {ai_data.get('event_comment')}")
            else:
                st.success(f"✅ イベント状況: {ai_data.get('event_comment', '周辺での大規模な混雑要因は検出されていません。')}")
                
            if is_rainy:
                st.info("🌧️ **雨天補正発動**: 駅チカ・直結の店舗に混雑が集中し、駅から離れた店舗が穴場になります。")

            st.markdown("---")

            cafes = ai_data.get("cafes", [])
            if not cafes:
                st.warning("該当エリアのカフェ情報が見つかりませんでした。別のキーワードでお試しください。")
            
            for cafe in cafes:
                congestion = cafe.get("base_congestion", 50)
                is_direct = cafe.get("station_direct", False)
                walk = cafe.get("walk_minutes", 3)
                
                if is_rainy:
                    if is_direct or walk <= 2:
                        congestion += 25
                    else:
                        congestion -= 15
                
                if ai_data.get("has_event"):
                    congestion += 20
                    
                congestion = max(10, min(100, congestion))
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"### **{cafe.get('name')}**")
                    st.caption(f"📍 所在地目安: {cafe.get('address')} / 徒歩 {walk}分")
                    if is_rainy and is_direct:
                        st.markdown("💬 *雨天のため、駅チカ・直結で混雑が集中しやすい店舗です。*")
                    elif is_rainy and not is_direct:
                        st.markdown("💬 *駅から少し歩くため、雨の日でも比較的落ち着いて座れる穴場です。*")
                    else:
                        st.markdown("💬 *標準的な混雑傾向の店舗です。*")
                with col2:
                    if congestion >= 70:
                        st.error(f"混雑度: {congestion}%")
                    elif congestion >= 40:
                        st.warning(f"混雑度: {congestion}%")
                    else:
                        st.success(f"穴場度高: {congestion}%")
                st.markdown("---")
