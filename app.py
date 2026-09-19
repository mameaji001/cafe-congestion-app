# ==========================================
# 3. サイドバー・条件設定 ＆ 位置情報処理
# ==========================================
st.sidebar.header("⚙️ 条件・検索設定")
mode = st.sidebar.radio("📍 検索モードを選択", ["今すぐ探す（現在地GPS）", "未来・指定場所で探す"])

target_location = ""
target_datetime = None
lat, lon = 35.6691, 139.8166  # デフォルト（東陽町）

if mode == "今すぐ探す（現在地GPS）":
    st.sidebar.caption("※ブラウザの位置情報アクセス許可が必要です")
    loc = get_geolocation()
    
    if loc and 'coords' in loc:
        lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
        st.sidebar.success(f"📍 GPS取得成功!\n(緯度:{lat:.4f} / 経度:{lon:.4f})")
        target_location = "現在地周辺"
    else:
        st.sidebar.warning("⚠️ GPSが取得できませんでした。")
        # GPS失敗時は手動でエリアを入力できるように代替フォームを表示
        fallback_input = st.sidebar.text_input("エリア名・駅名を手動入力してください", value="東陽町")
        target_location = fallback_input
        lat, lon, _ = get_coordinates(fallback_input)
        
    target_datetime = datetime.now(JST)

else:
    target_location = st.sidebar.text_input("検索エリア・駅名を入力", value="東陽町")
    selected_date = st.sidebar.date_input("日付を選択", date.today())
    selected_time = st.sidebar.time_input("時間を選択", time(15, 0))
    target_datetime = datetime.combine(selected_date, selected_time).replace(tzinfo=JST)
    
    if target_location:
        lat, lon, _ = get_coordinates(target_location)
