import sys
import streamlit as st
import pandas as pd
import os
import time
import io

# --- 跨目录导入逻辑 ---
# 获取当前文件的绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))

# 无论在本地还是云端，直接定位到 'test' 这一层作为根目录
# 假设你的 client_app.py 在 test/ui/ 目录下，那么上一级就是根
project_root = os.path.abspath(os.path.join(current_dir, ".."))

if project_root not in sys.path:
    # 使用 insert(0, ...) 确保你的项目路径优先级最高
    sys.path.insert(0, project_root)

try:
    # 只要 project_root 在路径里，这里就能通过 文件夹名.文件名 导入
    from core.trade import start_optimization_task
except ImportError as e:
    st.error(f"❌ 云端导入失败！\n根目录: {project_root}\n已加载路径: {sys.path[:3]}\n错误: {e}")
    st.stop()

# --- 基础配置 ---
st.set_page_config(page_title="跨境AI大师专业版", layout="wide", page_icon="🚀")

# --- 初始化 Session State ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'char_limit' not in st.session_state:
    st.session_state.char_limit = 60

# ================= 1. 权限校验层 =================
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

# ================= 2. 主业务层 =================

with st.sidebar:
    st.header("⚙️ 引擎与配置")

    # --- 💡 新增：AI 引擎切换逻辑 ---
    engine_type = st.selectbox(
        "选择 AI 引擎",
        ["Google Gemini (官方)", "DeepSeek (推荐)", "自定义中转"]
    )

    if engine_type == "Google Gemini ":
        # Google 的 OpenAI 兼容地址
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        model_name = "gemini-2.5-flash"  # 或者是你喜欢的其他版本
        st.info("💡 请在下方输入你的 Google AI Studio API Key")
    elif engine_type == "DeepSeek ":
        base_url = "https://api.deepseek.com"
        model_name = "deepseek-chat"
        st.info("💡 请在下方输入 DeepSeek API Key")
    else:
        base_url = st.text_input("中转地址 (Base URL)", value="https://api.xxx.com/v1")
        model_name = st.text_input("模型名称 (Model Name)", value="gpt-4o")

    # API 密钥池
    st.subheader("🔑 API 密钥池")
    raw_keys = st.text_area("输入 Keys (每行一个):", height=100)
    user_keys = [k.strip() for k in raw_keys.split('\n') if k.strip()]

    st.divider()

    # 数据导入
    uploaded_files = st.file_uploader("上传 Excel 文件", type=['xlsx', 'xls'], accept_multiple_files=True)

    st.divider()
    # --- 💡 新增：字符限制调节器 ---
    st.subheader("📝 标题长度控制")
    # 动态更新 session_state 中的 char_limit
    st.session_state.char_limit = st.slider(
        "标题字符上限 (Character Limit)",
        min_value=10,
        max_value=200,
        value=st.session_state.char_limit,  # 初始值为之前定义的 60
        help="建议：Mercado Libre 设为 60-80，Amazon 设为 80-120"
    )

    # 也可以加个数字显示，方便精确调整
    st.caption(f"当前限制：{st.session_state.char_limit} 字符")

    st.divider()
    # 其他任务参数
    target_platform = st.selectbox("目标平台", ["Mercado Libre", "Amazon", "Shopee", "TikTok Shop"])
    target_lang = st.selectbox("目标语言", [ "英语", "西班牙语", "葡萄牙语", "中文"])

    batch_size = st.slider("单批次处理数量", 1, 50, 30)
    sleep_time = st.slider("批次间休眠 (秒)", 1, 120, 30)

# --- 主界面 ---
st.title("🚀 跨境电商 AI 批量优化系统")

if not uploaded_files:
    st.info("💡 请在侧边栏上传文件。")
    st.stop()

if st.button("🔥 启动 AI 批量优化引擎", type="primary", use_container_width=True):
    if not user_keys:
        st.error("❌ 请输入 API Key！")
    else:
        with st.status("🚀 正在执行...", expanded=True) as status:
            log_area = st.empty()
            all_logs = []

            # 💡 传入了新增的 model_name 和 base_url
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
                    for file_name, df_result in final_results:
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df_result.to_excel(writer, index=False)
                        st.download_button(
                            label=f"📥 下载 Optimized_{file_name}",
                            data=output.getvalue(),
                            file_name=f"Optimized_{file_name}",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=file_name
                        )
                else:
                    all_logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
                    log_area.code("\n".join(all_logs[-15:]), language="bash")