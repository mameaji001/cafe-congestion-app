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

# --- 2. 無料データ取得関数 (OpenStreetMap / 安定化修正版) -----------------------
@st.cache_data(ttl=3600)
def get_cafes_from_osm(area_name):
    """地名から緯度経度を取得し、周辺カフェをOverpass APIで取得する"""
    # 適切なUser-Agentを設定してブロックを回避
    headers = {
        "User-Agent": "CafeCongestionPredictorApp/2.0 (contact: test@example.com)"
    }
    
    try:
        # 緯度経度検索 (Nominatim)
        geo_url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": area_name,
            "format": "json",
            "limit": 1,
            "countrycodes": "jp"
        }
        
        geo_res = requests.get(geo_url, headers=headers, params=params, timeout=10)
        
        if geo_res.status_code != 200:
            return None, f"エリア検索に失敗しました (Status Code: {geo_res.status_code})"
            
        geo_data = geo_res.json()
        if not geo_data:
            return None, "指定されたエリアが見つかりませんでした。駅名や市区町村名を変えて試してください。"
            
        lat = float(geo_data[0]["lat"])
        lon = float(geo_data[0]["lon"])
        
        # Overpass API (周辺700mのカフェを検索)
        overpass_url = "https://overpass-api.de/api/interpreter"
        query = f"""
        [out:json][timeout:15];
        (
          node["amenity"="cafe"](around:700,{lat},{lon});
          way["amenity"="cafe"](around:700,{lat},{lon});
        );
        out body 15;
        """
        
        op_res = requests.post(overpass_url, data={"data": query}, headers=headers, timeout=15)
        
        if op_res.status_code != 200:
            return None, f"カフェデータの取得に失敗しました (Status Code: {op_res.status_code})"
            
        res_json = op_res.json()
        
        cafes = []
        for item in res_json.get("elements", []):
            tags = item.get("tags", {})
            name = tags.get("name")
            if name:
                is_chain = any(chain.lower() in name.lower() for chain in MAJOR_CHAINS)
                cafes.append({
                    "name": name,
                    "type": "大手チェーン" if is_chain else "個人系・穴場カフェ",
                    "lat": item.get("lat", lat),
                    "lon": item.get("lon", lon),
                    "opening_hours": tags.get("opening_hours", "情報なし")
                })
        return cafes, None
        
    except requests.exceptions.JSONDecodeError:
        return None, "データ形式のエラーが発生しました。時間を置いて再試行してください。"
    except Exception as e:
        return None, f"通信エラー: {e}"

# --- 3. 混雑度計算ロジック -----------------------------------------------------
def calculate_congestion(cafe, weather, time_slot, purpose, day_type):
    score = 40
    
    if time_slot == "カフェタイム（14時〜17時）":
        score += 25
    elif time_slot == "ランチ帯（11時〜14時）":
        score += 15
        
    if weather == "雨・悪天候":
        if cafe["type"] == "大手チェーン":
            score += 20
        else:
            score -= 15
            
    if day_type == "土日祝":
        score += 15
        
    if purpose == "作業・ノマド（長居傾向）":
        score += 10
        
    return min(max(score, 10), 95)

# --- 4. 検索＆結果表示 --------------------------------------------------------
if st.button("🔎 カフェ混雑度を予測する"):
    with st.spinner(f"「{location_name}」周辺の実在カフェデータを検索中..."):
        cafes, error = get_cafes_from_osm(location_name)
        
        if error:
            st.error(error)
        elif not cafes:
            st.warning(f"「{location_name}」周辺に登録されているカフェが見つかりませんでした。別の主要駅名などで試してみてください。")
        else:
            st.success(f"「{location_name}」周辺で {len(cafes)} 件のカフェが見つかりました！")
            st.header("2. 混雑予測結果一覧")
            
            results = []
            for cafe in cafes:
                c_score = calculate_congestion(cafe, weather, time_slot, purpose, day_type)
                
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
            
