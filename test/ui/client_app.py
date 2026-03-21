import sys
import streamlit as st
import pandas as pd
import os
import time
import io
import openpyxl

# --- 跨目录导入逻辑 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    # 确保从 core 导入对应的逻辑函数
    from core.trade import start_optimization_task, VERSION
    from core.listing_logic import process_mercado_listing, get_column_options
except ImportError as e:
    st.error(f"❌ 核心逻辑导入失败！请确保 core 目录下有 trade.py 和 listing_logic.py\n错误: {e}")
    st.stop()

# --- 基础配置 ---
st.set_page_config(page_title=f"跨境AI大师 {VERSION}", layout="wide", page_icon="🚀")

# --- 1. AI 引擎预设数据 ---
ENGINE_CONFIGS = {
    "Google Gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model_name": "gemini-2.5-flash"
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
if 'user_features' not in st.session_state:
    st.session_state.user_features = ["SEO", "Listing"]

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
    st.caption(f"当前版本: {VERSION}")

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
    st.session_state.char_limit = st.slider("标题字符上限", 10, 200, 60)

    st.divider()
    target_platform = st.selectbox("目标平台", ["Mercado Libre", "Amazon", "Shopee", "TikTok Shop"])
    target_lang = st.selectbox("目标语言", ["英语", "西班牙语", "葡萄牙语", "中文"])
    batch_size = st.slider("单批次数量", 1, 50, 20)
    sleep_time = st.slider("批次间休眠 (秒)", 1, 60, 5)

# ================= 4. 主界面布局 =================

tab_seo, tab_listing = st.tabs(["🔥 标题批量优化", "📦 美克多列表自动上架"])

# --- TAB 1: 标题优化 (恢复完整逻辑) ---
with tab_seo:
    st.title(f"🚀 AI 标题优化引擎 `{VERSION}`")
    col_info, col_main = st.columns([1, 2])

    with col_info:
        st.info(f"""
        ### 📖 核心功能
        - **递归质检**：AI 生成后若超长，系统自动重做（最多3轮）。
        - **格式兼容**：支持 **Excel (.xlsx)** 和 **CSV**。
        - **安全机制**：不截断单词，确保语义完整。
        """)
        if st.session_state.char_limit > 60 and target_platform == "Mercado Libre":
            st.warning("⚠️ 限制超过了 60 字符，ML平台可能会上架失败。")

    with col_main:
        st.subheader("📂 数据导入与执行")
        uploaded_files = st.file_uploader("上传文件 (支持 .xlsx, .xls, .csv)", type=['xlsx', 'xls', 'csv'],
                                          accept_multiple_files=True, key="seo_uploader")

        if uploaded_files:
            total_rows = 0
            for f in uploaded_files:
                try:
                    df_temp = pd.read_csv(f) if f.name.endswith('.csv') else pd.read_excel(f)
                    total_rows += len(df_temp)
                except:
                    pass
            st.success(f"已加载 {len(uploaded_files)} 个文件，共 {total_rows} 条数据。")

            if st.button("🔥 启动 AI 多轮优化引擎", type="primary", use_container_width=True):
                if not user_keys:
                    st.error("❌ 请在侧边栏配置 API Key！")
                else:
                    with st.status("🚀 正在进行递归优化...", expanded=True) as status:
                        log_area = st.empty()
                        all_logs = []

                        # 调用 core/trade.py 中的生成器
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

                                # 下载结果
                                for file_name, df_result in final_results:
                                    if file_name.lower().endswith('.csv'):
                                        csv_data = df_result.to_csv(index=False, encoding='utf-8-sig').encode(
                                            'utf-8-sig')
                                        st.download_button(f"📥 下载 Optimized_{file_name}", data=csv_data,
                                                           file_name=f"Opt_{file_name}", mime="text/csv")
                                    else:
                                        output = io.BytesIO()
                                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                            df_result.to_excel(writer, index=False)
                                        st.download_button(f"📥 下载 Optimized_{file_name}", data=output.getvalue(),
                                                           file_name=f"Opt_{file_name}",
                                                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                            else:
                                all_logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
                                log_area.code("\n".join(all_logs[-15:]), language="bash")

# --- TAB 2: 美克多列表上架 (动态解析逻辑) ---
with tab_listing:
    st.title("📦 美克多列表自动化填充 (Pro)")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        src_file = st.file_uploader("1. 上传【AI优化后的采集表】", type=['xlsx', 'csv'], key="final_src")
    with col2:
        tpl_file = st.file_uploader("2. 上传【美克多官方空模板】", type=['xlsx'], key="final_tpl")

    if src_file and tpl_file:
        # 读取数据
        src_df = pd.read_csv(src_file) if src_file.name.endswith('.csv') else pd.read_excel(src_file)
        tpl_bytes = tpl_file.getvalue()

        # 加载模板
        tpl_wb = openpyxl.load_workbook(io.BytesIO(tpl_bytes))
        target_sheet = st.selectbox("📑 请选择要填充的类目页 (Sheet)：", tpl_wb.sheetnames,
                                    index=len(tpl_wb.sheetnames) - 1)
        ws = tpl_wb[target_sheet]

        # 解析表头位置
        ml_headers = []
        header_row_idx = 0
        for r in range(1, 10):
            row_vals = [str(ws.cell(row=r, column=c).value) for c in range(1, ws.max_column + 1)]
            if any("Title" in (x or "") for x in row_vals):
                ml_headers = row_vals
                header_row_idx = r
                break

        if ml_headers:
            st.divider()
            m1, m2 = st.columns(2)
            with m1:
                st.subheader("🔗 字段映射")
                t_col = st.selectbox("哪一列是优化后的【标题】？", src_df.columns)
                i_col = st.selectbox("哪一列是【图片URL】？", src_df.columns)

            with m2:
                st.subheader("⚙️ 属性批量填充")
                # 过滤公式列和无效列
                clean_h = [h for h in ml_headers if h and "None" not in h and "Number of characters" not in h]
                to_fill = st.multiselect("点击勾选需要统一填充的属性 (如 Brand, Length unit)：", clean_h)

                static_data = {}
                if to_fill:
                    st.info("💡 提示：'Number of characters' 已设为自动计算，无需手动填写。")
                    for h in to_fill:
                        col_idx = ml_headers.index(h) + 1
                        # 核心：动态探测下拉选项
                        opts = get_column_options(ws, tpl_wb, col_idx, header_row_idx)

                        if opts:
                            static_data[h] = st.selectbox(f"选择 [{h}]", options=opts, key=f"sel_{h}")
                        else:
                            static_data[h] = st.text_input(f"手动输入 [{h}]", key=f"ipt_{h}")

            st.divider()
            if st.button("🚀 生成美克多上架表格", use_container_width=True, type="primary"):
                with st.spinner("正在精准填充，保留公式中..."):
                    try:
                        final_xlsx = process_mercado_listing(
                            src_df, tpl_bytes, target_sheet,
                            {'title_col': t_col, 'img_col': i_col},
                            static_data
                        )
                        st.success("✅ 生成成功！已避开描述行与示例行，并保留了字数统计公式。")
                        st.download_button(
                            label="📥 点击下载上架表",
                            data=final_xlsx,
                            file_name=f"ML_Ready_{target_sheet}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    except Exception as e:
                        st.error(f"填充失败，错误代码: {e}")
        else:
            st.error("未能识别出模板中的 Title 列，请确认是否为美克多原始模板。")