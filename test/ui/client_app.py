import sys
import streamlit as st
import pandas as pd
import os
import time
import io

# --- 跨目录导入逻辑 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    # 尝试从 trade_logic 导入 (根据你实际的文件名修改)
    from core.trade_logic import start_optimization_task, VERSION
except ImportError:
    try:
        from core.trade import start_optimization_task, VERSION
    except ImportError as e:
        st.error(f"❌ 导入失败！请检查 core 文件夹下的文件名是否为 trade_logic.py\n错误: {e}")
        st.stop()

# --- 基础配置 ---
st.set_page_config(page_title=f"跨境AI大师 {VERSION}", layout="wide", page_icon="🚀")

# --- 1. AI 引擎预设数据 ---
ENGINE_CONFIGS = {
    "Google Gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model_name": "gemini-1.5-flash"
    },
    "DeepSeek": {
        "base_url": "https://api.deepseek.com/v1",
        "model_name": "deepseek-chat"
    },
    "自定义中转": {
        "base_url": "https://api.xxx.com/v1",
        "model_name": "gpt-4o"
    }
}

# --- 2. 初始化 Session State ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'char_limit' not in st.session_state:
    st.session_state.char_limit = 60

# ================= 权限校验层 =================
if not st.session_state.authenticated:
    st.title("🔐 软件授权验证")
    _, auth_col, _ = st.columns([1, 2, 1])
    with auth_col:
        auth_code = st.text_input("请输入卡密 (License Key)", type="password")
        if st.button("立即验证并登录", use_container_width=True):
            if auth_code == "888888":
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ 卡密无效")
    st.stop()

# ================= 3. 侧边栏：核心配置 =================

with st.sidebar:
    st.header("⚙️ 引擎与配置")
    st.caption(f"当前版本: {VERSION}")  # 显示版本号

    # AI 引擎切换逻辑
    engine_type = st.selectbox("选择 AI 引擎", list(ENGINE_CONFIGS.keys()))

    if 'prev_engine' not in st.session_state or st.session_state.prev_engine != engine_type:
        st.session_state.current_url = ENGINE_CONFIGS[engine_type]["base_url"]
        st.session_state.current_model = ENGINE_CONFIGS[engine_type]["model_name"]
        st.session_state.prev_engine = engine_type

    base_url = st.text_input("接口地址 (Base URL)", key="current_url")
    model_name = st.text_input("模型名称 (Model Name)", key="current_model")

    st.subheader("🔑 API 密钥池")
    raw_keys = st.text_area("输入 Keys (每行一个):", height=100)
    user_keys = [k.strip() for k in raw_keys.split('\n') if k.strip()]

    st.divider()

    st.subheader("📝 标题长度控制")
    st.session_state.char_limit = st.slider(
        "标题字符上限",
        min_value=10, max_value=200,
        value=st.session_state.char_limit,
        help="Mercado Libre 严格限制 60 字符"
    )
    st.caption(f"🎯 递归目标：{st.session_state.char_limit} 字符")

    st.divider()
    target_platform = st.selectbox("目标平台", ["Mercado Libre", "Amazon", "Shopee", "TikTok Shop"])
    target_lang = st.selectbox("目标语言", ["英语", "西班牙语", "葡萄牙语", "中文"])
    batch_size = st.slider("单批次处理数量", 1, 50, 20)
    sleep_time = st.slider("批次间休眠 (秒)", 1, 60, 5)

# ================= 4. 主界面布局 =================

st.title(f"🚀 跨境电商 AI 批量优化系统 `{VERSION}`")

col_info, col_main = st.columns([1, 2])

with col_info:
    st.info(f"""
    ### 📖 v2.0 更新说明
    - **递归质检**：AI 生成后若超长，系统会自动打回重做，直到合格（最多3轮）。
    - **品类感知**：自动识别手机壳加 `for`，汽车/家居产品不加 `for`。
    - **格式兼容**：现在支持 **Excel (.xlsx)** 和 **CSV** 文件。
    - **安全机制**：不再暴力截断单词，确保标题语义完整。
    """)
    if st.session_state.char_limit > 60 and target_platform == "Mercado Libre":
        st.warning("⚠️ 警告：检测到目标平台为 Mercado Libre，但限制超过了 60，可能导致上架失败。")

with col_main:
    st.subheader("📂 数据导入与执行")
    # 💡 增加对 csv 的支持
    uploaded_files = st.file_uploader("上传文件 (支持 .xlsx, .xls, .csv)", type=['xlsx', 'xls', 'csv'],
                                      accept_multiple_files=True)

    if not uploaded_files:
        st.warning("👈 请先上传文件以开启 AI 优化引擎。")
    else:
        total_rows = 0
        for f in uploaded_files:
            try:
                if f.name.endswith('.csv'):
                    df_temp = pd.read_csv(f, encoding='utf-8-sig')
                else:
                    df_temp = pd.read_excel(f)
                total_rows += len(df_temp)
            except:
                pass
        st.success(f"已加载 {len(uploaded_files)} 个文件，总计约 {total_rows} 条数据。")

        if st.button("🔥 启动 AI 多轮优化引擎", type="primary", use_container_width=True):
            if not user_keys:
                st.error("❌ 请在侧边栏配置 API Key！")
            else:
                with st.status("🚀 正在进行多轮递归优化...", expanded=True) as status:
                    log_area = st.empty()
                    all_logs = []

                    task_gen = start_optimization_task(
                        uploaded_files=uploaded_files,
                        platform=target_platform,
                        char_limit=st.session_state.char_limit,
                        language=target_lang,
                        api_keys=user_keys,
                        batch_size=batch_size,
                        sleep_time=sleep_time,
                        model_name=model_name,
                        base_url=base_url
                    )

                    for msg in task_gen:
                        if msg == "FINISH_SIGNAL":
                            final_results = next(task_gen)
                            status.update(label="✅ 所有文件优化完成！", state="complete")
                            st.divider()

                            # 下载区域
                            for file_name, df_result in final_results:
                                # 根据原文件名决定导出格式
                                is_csv = file_name.lower().endswith('.csv')

                                if is_csv:
                                    # CSV 导出
                                    csv_data = df_result.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                                    st.download_button(
                                        label=f"📥 下载 Optimized_{file_name}",
                                        data=csv_data,
                                        file_name=f"Optimized_{file_name}",
                                        mime="text/csv",
                                        key=file_name,
                                        use_container_width=True
                                    )
                                else:
                                    # Excel 导出
                                    output = io.BytesIO()
                                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                        df_result.to_excel(writer, index=False)
                                    st.download_button(
                                        label=f"📥 下载 Optimized_{file_name}",
                                        data=output.getvalue(),
                                        file_name=f"Optimized_{file_name}",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        key=file_name,
                                        use_container_width=True
                                    )
                        else:
                            all_logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
                            log_area.code("\n".join(all_logs[-15:]), language="bash")