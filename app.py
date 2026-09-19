import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="カフェ混雑予測アプリ", page_icon="☕", layout="centered")

st.title("☕ カフェ混雑予測（完全無料版）")
st.write("OpenStreetMapのリアルタイムデータとシチュエーション分析で穴場カフェを予測します。")

# 代表的な大手カフェチェーン（判定用）
MAJOR_CHAINS = [
    "スターバックス", "Starbucks", "ドトール", "Doutor", "タリーズ", "Tully's",
    "サンマルク", "コメダ", "Komeda", "エクセルシオール", "ベローチェ", "Veloce",
    "プロント", "Pronto", "カフェ・ド・クリエ", "星乃珈琲", "上島珈琲"
]

# --- 1. エリア検索 -----------------------------------------------------------
st.header("1. エリアとシチュエーションを選択")

location_name = st.text_input("検索したいエリア・駅名を入力してください", value="東陽町")

# シチュエーション選択
col1, col2 = st.columns(2)
with col1:
    weather = st.selectbox("天候", ["晴れ・曇り", "雨・悪天候"])
    time_slot = st.selectbox("時間帯", ["午前（〜11時）", "ランチ帯（11時〜14時）", "カフェタイム（14時〜17時）", "夜（17時〜）"])

with col2:
    purpose = st.selectbox("利用目的", ["サクッと（テイクアウト/短時間）", "作業・ノマド（長居傾向）", "おしゃべり・休憩"])
    day_type = st.selectbox("曜日", ["平日", "土日祝"])

# --- 2. 無料データ取得関数 (OpenStreetMap) -----------------------------------
@st.cache_data(ttl=3600)  # 1時間はデータをキャッシュして高速化
def get_cafes_from_osm(area_name):
    """OpenStreetMapから指定エリアのカフェを検索して取得する関数"""
    # ジオコーディング（地名 -> 緯度経度）
    geo_url = f"https://nominatim.openstreetmap.org/search?format=json&q={area_name}&countrycodes=jp"
    headers = {"User-Agent": "CafeCongestionPredictorApp/1.0"}
    
    try:
        geo_res = requests.get(geo_url, headers=headers, timeout=5).json()
        if not geo_res:
            return None, "指定されたエリアが見つかりませんでした。"
        
        lat = float(geo_res[0]["lat"])
        lon = float(geo_res[0]["lon"])
        
        # Overpass API (周辺500mのカフェを検索)
        overpass_url = "https://overpass-api.de/api/interpreter"
        query = f"""
        [out:json][timeout:10];
        (
          node["amenity"="cafe"](around:500,{lat},{lon});
          way["amenity"="cafe"](around:500,{lat},{lon});
        );
        out body 15;
        """
        res = requests.post(overpass_url, data={"data": query}, timeout=10).json()
        
        cafes = []
        for item in res.get("elements", []):
            tags = item.get("tags", {})
            name = tags.get("name")
            if name:
                # 大手チェーンかどうかの判定
                is_chain = any(chain.lower() in name.lower() for chain in MAJOR_CHAINS)
                cafes.append({
                    "name": name,
                    "type": "大手チェーン" if is_chain else "個人系・穴場カフェ",
                    "lat": item.get("lat", lat),
                    "lon": item.get("lon", lon),
                    "opening_hours": tags.get("opening_hours", "情報なし")
                })
        return cafes, None
    except Exception as e:
        return None, f"データ取得エラー: {e}"

# --- 3. 混雑度計算ロジック -----------------------------------------------------
def calculate_congestion(cafe, weather, time_slot, purpose, day_type):
    score = 40  # 基準値
    
    # 時間帯補正
    if time_slot == "カフェタイム（14時〜17時）":
        score += 25
    elif time_slot == "ランチ帯（11時〜14時）":
        score += 15
        
    # 天候＆店舗タイプ補正
    if weather == "雨・悪天候":
        if cafe["type"] == "大手チェーン":
            score += 20  # 駅近チェーンは雨だと混む
        else:
            score -= 15  # 個人店・路地裏カフェは雨だと空きやすい
            
    # 休日補正
    if day_type == "土日祝":
        score += 15
        
    # 目的補正
    if purpose == "作業・ノマド（長居傾向）":
        score += 10  # 回転率が下がるため実質混雑度UP
        
    # スコアを0〜100に収める
    return min(max(score, 10), 95)

# --- 4. 検索＆結果表示 --------------------------------------------------------
if st.button("🔎 カフェ混雑度を予測する"):
    with st.spinner(f"「{location_name}」周辺の実在カフェデータを検索中..."):
        cafes, error = get_cafes_from_osm(location_name)
        
        if error:
            st.error(error)
        elif not cafes:
            st.warning(f"「{location_name}」の半径500m以内に登録されているカフェが見つかりませんでした。別の大きな駅名やエリア名で試してみてください。")
        else:
            st.success(f"「{location_name}」周辺で {len(cafes)} 件のカフェが見つかりました！")
            st.header("2. 混雑予測結果一覧")
            
            # 各店舗の予測計算
            results = []
            for cafe in cafes:
                c_score = calculate_congestion(cafe, weather, time_slot, purpose, day_type)
                
                # 状態判定
                if c_score >= 70:
                    status = "🔴 混雑率高（待ち発生かも）"
                elif c_score >= 45:
                    status = "🟡 やや混雑（入れる可能性あり）"
                else:
                    status = "🟢 空いている可能性大（穴場！）"
                    
                results.append({
                    "店舗名": cafe["name"],
                    "タイプ": cafe["type"],
                    "予測混雑度": f"{c_score}%",
                    "判定": status,
                    "営業時間メモ": cafe["opening_hours"]
                })
            
            df = pd.DataFrame(results)
            st.dataframe(df, use_container_width=True)
            
            st.info("💡 **ヒント**: 雨の日は「大手チェーン」に人が集中しやすいため、少し離れた「個人系・穴場カフェ」を狙うと座れる確率が上がります！")
