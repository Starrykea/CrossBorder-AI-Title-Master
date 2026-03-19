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
    from core.trade import start_optimization_task
except ImportError as e:
    st.error(f"❌ 云端导入失败！\n错误: {e}")
    st.stop()

# --- 基础配置 ---
st.set_page_config(page_title="跨境AI大师专业版", layout="wide", page_icon="🚀")

# --- 1. AI 引擎预设数据 ---
ENGINE_CONFIGS = {
    "Google Gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model_name": "gemini-2.5-flash"  # 建议使用稳定版，2.5目前非公开主版本
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

    # AI 引擎切换逻辑
    engine_type = st.selectbox("选择 AI 引擎", list(ENGINE_CONFIGS.keys()))

    # 联动更新：当切换引擎时，自动刷新 Session State 中的地址和模型名
    if 'prev_engine' not in st.session_state or st.session_state.prev_engine != engine_type:
        st.session_state.current_url = ENGINE_CONFIGS[engine_type]["base_url"]
        st.session_state.current_model = ENGINE_CONFIGS[engine_type]["model_name"]
        st.session_state.prev_engine = engine_type

    # 这里的输入框绑定了 key，切换引擎时会自动变，但也支持用户手动打字覆盖
    base_url = st.text_input("接口地址 (Base URL)", key="current_url")
    model_name = st.text_input("模型名称 (Model Name)", key="current_model")

    # API 密钥池
    st.subheader("🔑 API 密钥池")
    raw_keys = st.text_area("输入 Keys (每行一个):", height=100)
    user_keys = [k.strip() for k in raw_keys.split('\n') if k.strip()]

    st.divider()

    # 字符限制调节器
    st.subheader("📝 标题长度控制")
    st.session_state.char_limit = st.slider(
        "标题字符上限",
        min_value=10, max_value=200,
        value=st.session_state.char_limit,
        help="建议：Mercado Libre 设为 60"
    )
    st.caption(f"当前限制：{st.session_state.char_limit} 字符")

    st.divider()
    # 其他任务参数
    target_platform = st.selectbox("目标平台", ["Mercado Libre", "Amazon", "Shopee", "TikTok Shop"])
    target_lang = st.selectbox("目标语言", ["英语", "西班牙语", "葡萄牙语", "中文"])
    batch_size = st.slider("单批次处理数量", 1, 50, 30)
    sleep_time = st.slider("批次间休眠 (秒)", 1, 120, 30)

# ================= 4. 主界面布局 =================

st.title("🚀 跨境电商 AI 批量优化系统")

# 布局：左边显示提示，右边放置上传和执行
col_info, col_main = st.columns([1, 2])

with col_info:
    st.info("""
    ### 📖 使用说明
    1. 在侧边栏配置 **API Key** 和 **AI 引擎**。
    2. 在右侧上传需要处理的 **Excel**。
    3. 点击启动按钮开始批量优化。
    4. 完成后点击生成的按钮下载文件。
    """)
    if st.session_state.char_limit > 60 and target_platform == "Mercado Libre":
        st.warning("⚠️ 提示：Mercado Libre 标题建议不要超过 60 字符。")

with col_main:
    # --- 💡 按照要求：将选择文件放在右侧执行栏上方 ---
    st.subheader("📂 数据导入与执行")
    uploaded_files = st.file_uploader("上传 Excel 文件 (支持批量)", type=['xlsx', 'xls'], accept_multiple_files=True)

    if not uploaded_files:
        st.warning("👈 请先上传 Excel 文件以开启执行功能。")
    else:
        # 显示已上传文件的基本条数信息
        total_rows = 0
        for f in uploaded_files:
            try:
                df_temp = pd.read_excel(f)
                total_rows += len(df_temp)
            except:
                pass
        st.success(f"已加载 {len(uploaded_files)} 个文件，总计约 {total_rows} 条待处理访问。")

        # 执行按钮
        if st.button("🔥 启动 AI 批量优化引擎", type="primary", use_container_width=True):
            if not user_keys:
                st.error("❌ 请先在侧边栏输入 API Key！")
            else:
                with st.status("🚀 正在执行 AI 优化...", expanded=True) as status:
                    log_area = st.empty()
                    all_logs = []

                    # 传入动态获取的 model_name 和 base_url
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
                            status.update(label="✅ 任务完成！", state="complete")
                            st.divider()
                            # 结果下载
                            for file_name, df_result in final_results:
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