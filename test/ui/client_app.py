import sys
import streamlit as st
import pandas as pd
import os
import time
import io

# --- 跨目录导入逻辑 (兼容本地与云端) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

if project_root not in sys.path:
    sys.path.append(project_root)
core_path = os.path.join(project_root, "core")
if core_path not in sys.path:
    sys.path.append(core_path)

try:
    from core.trade import start_optimization_task
except ImportError:
    try:
        from trade import start_optimization_task
    except ImportError:
        st.error("❌ 无法加载核心逻辑模块。请检查项目结构是否包含 core/trade.py")
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
        auth_code = st.text_input("请输入卡密 (License Key)", type="password", help="请输入 6 位授权码")
        if st.button("立即验证并登录", use_container_width=True):
            if auth_code == "888888":
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ 卡密无效，请联系管理员")
    st.stop()

# ================= 2. 主业务层 =================

# --- 侧边栏：全局配置 ---
with st.sidebar:
    st.header("⚙️ 全局配置")

    # A. 数据导入 (云端专用：文件上传器)
    st.subheader("📁 数据导入")
    uploaded_files = st.file_uploader(
        "选择 Excel 文件 (支持多选)",
        type=['xlsx', 'xls'],
        accept_multiple_files=True,
        help="请上传需要优化的 Excel 表格"
    )

    st.divider()

    # B. API 密钥管理
    st.subheader("🔑 API 密钥池")
    raw_keys = st.text_area(
        "请输入 Gemini API Keys (一行一个):",
        height=120,
        placeholder="AIzaSy...",
        help="系统将自动轮询使用这些 Key"
    )
    user_keys = [k.strip() for k in raw_keys.split('\n') if k.strip()]

    if user_keys:
        st.success(f"✅ 已加载 {len(user_keys)} 个密钥")
    else:
        st.warning("⚠️ 需填入 API Key 才能启动")

    st.divider()

    # C. 任务参数
    target_platform = st.selectbox("目标平台", ["Mercado Libre", "Amazon", "Shopee", "TikTok Shop"])

    st.write("📏 标题字符限制")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        if st.button("➖"): st.session_state.char_limit -= 1
    with c3:
        if st.button("➕"): st.session_state.char_limit += 1
    with c2:
        st.session_state.char_limit = st.number_input("Limit", value=st.session_state.char_limit,
                                                      label_visibility="collapsed")

    target_lang = st.selectbox("目标语言", ["保持原样", "English", "Spanish", "Portuguese", "Chinese"])

    st.divider()

    batch_size = st.slider("单批次处理数量", 1, 50, 20)
    sleep_time = st.slider("批次间休眠 (秒)", 1, 120, 65)

# --- 主界面 ---
st.title("🚀 跨境电商 AI 批量优化系统")

# 检查上传情况
if not uploaded_files:
    st.info("💡 请在左侧侧边栏上传 Excel 文件以开始任务。")
    st.stop()

# 任务看板
st.subheader("📊 待处理清单")
file_info = [{"文件名": f.name, "大小": f"{f.size / 1024:.2f} KB"} for f in uploaded_files]
st.table(pd.DataFrame(file_info))

# --- 任务处理中心 ---
st.divider()
if st.button("🔥 启动 AI 批量优化引擎", type="primary", use_container_width=True):
    if not user_keys:
        st.error("❌ 请先在左侧配置 API Key！")
    else:
        with st.status("🚀 正在执行 AI 优化任务...", expanded=True) as status:
            log_area = st.empty()
            all_logs = []

            # 调用核心逻辑
            # 注意：传入的是 uploaded_files 对象列表，而不是路径
            task_gen = start_optimization_task(
                uploaded_files=uploaded_files,
                platform=target_platform,
                char_limit=st.session_state.char_limit,
                language=target_lang,
                api_keys=user_keys,
                batch_size=batch_size,
                sleep_time=sleep_time
            )

            # 迭代生成器获取日志和结果
            for msg in task_gen:
                if msg == "FINISH_SIGNAL":
                    # 获取最终的处理结果数据
                    final_results = next(task_gen)
                    status.update(label="✅ 任务全部完成！请下载结果", state="complete")

                    st.divider()
                    st.subheader("📥 下载优化后的文件")

                    # 为每个文件生成下载按钮
                    for file_name, df_result in final_results:
                        # 将 DataFrame 转换为 Excel 字节流
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df_result.to_excel(writer, index=False)

                        st.download_button(
                            label=f"点击下载: Optimized_{file_name}",
                            data=output.getvalue(),
                            file_name=f"Optimized_{file_name}",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=file_name  # 唯一键防止冲突
                        )
                    st.balloons()
                else:
                    # 正常的进度日志显示
                    current_time = time.strftime("%H:%M:%S", time.localtime())
                    all_logs.append(f"[{current_time}] {msg}")
                    log_area.code("\n".join(all_logs[-15:]), language="bash")