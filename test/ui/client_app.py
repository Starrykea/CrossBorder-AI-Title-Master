import sys

import streamlit as st
import pandas as pd
import os
import time
# --- 跨目录导入逻辑 ---
script_dir = r'E:\qq\PyCharmMiscProject\PyCharmMiscProject\test\core'
if script_dir not in sys.path:
    sys.path.append(script_dir)

try:
    from trade import start_optimization_task
except ImportError:
    st.error(f"❌ 找不到 trade.py。请确保该文件在路径: {script_dir}")
    st.stop()
# --- 基础配置 ---
st.set_page_config(page_title="跨境AI大师专业版", layout="wide", page_icon="🚀")

# 初始化 Session State
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'char_limit' not in st.session_state:
    st.session_state.char_limit = 60
if 'folder_path' not in st.session_state:
    st.session_state.folder_path = r'C:\Users\Administrator\Desktop\text'

# ================= 1. 权限校验层 (EXE 启动首屏) =================
if not st.session_state.authenticated:
    st.title("🔐 软件授权验证")
    # 居中布局尝试
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

# ================= 2. 主业务层 (授权后可见) =================

# 侧边栏：全局任务配置
with st.sidebar:
    st.header("⚙️ 全局配置")

    # --- 动态 Key 管理区 ---
    st.subheader("🔑 API 密钥池")
    st.caption("一行一个 Key，系统会自动轮询使用")

    # 使用 text_area 让用户一行输入一个 Key
    raw_keys = st.text_area(
        "请输入 Gemini API Keys:",
        height=150,
        placeholder="AIzaSyA...\nAIzaSyB...\nAIzaSyC...",
        help="支持多个 Key 轮询，每行一个"
    )

    # 自动过滤掉空行和空格
    user_keys = [k.strip() for k in raw_keys.split('\n') if k.strip()]

    if not user_keys:
        st.warning("⚠️ 请输入至少一个有效的 API Key")
    else:
        st.success(f"✅ 已加载 {len(user_keys)} 个密钥")

    st.divider()

    # --- A. 优化内容多选 ---
    st.subheader("1. 优化目标字段")
    selected_tasks = st.multiselect(
        "请勾选需要优化的内容：",
        ["商品名称 (Title/Name)", "商品描述 (Description)", "五点描述 (Bullet Points)", "搜索关键词 (Keywords)"],
        default=["商品名称 (Title/Name)"]
    )

    st.divider()
    # --- client_app.py 侧边栏新增部分 ---
    st.subheader("⚡ 性能与频率限制")

    # 批量大小：一次发给 AI 多少条
    batch_size = st.slider("单批次处理数量", min_value=1, max_value=50, value=30,
                           help="免费版建议 15-30，付费版可设为 50")

    # 睡眠时间：每批次处理完等多久
    sleep_time = st.slider("批次间睡眠时间 (秒)", min_value=1, max_value=120, value=60,
                           help="针对 429 错误：免费版建议 65秒，付费版设为 1-3秒")
    # --- B. 平台与字符限制 ---
    st.subheader("2. 平台与长度控制")
    target_platform = st.selectbox(
        "目标电商平台",
        ["Mercado Libre", "Amazon", "Shopee", "Lazada", "TikTok Shop"]
    )

    st.write("📏 标题长度限制")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        if st.button("➖"): st.session_state.char_limit -= 1
    with c3:
        if st.button("➕"): st.session_state.char_limit += 1
    with c2:
        # 实时同步数字输入框
        st.session_state.char_limit = st.number_input(
            "Limit", value=st.session_state.char_limit, label_visibility="collapsed"
        )

    st.divider()

    # --- C. 多语言翻译 ---
    st.subheader("3. 翻译配置")
    target_lang = st.selectbox(
        "翻译为目标语言：",
        ["保持原样", "English (英语)", "Chinese (中文)", "French (法语)", "Japanese (日语)", "German (德语)"]
    )

    st.divider()
    st.info(f"已选任务：{len(selected_tasks)} 项")

# 主页面内容
st.title("🚀 跨境电商 AI 批量优化系统")

tab_excel, tab_process = st.tabs(["📂 数据导入与路径", "⚡ 任务监控中心"])

# --- Tab 1: 数据导入 (改为手动路径输入) ---
with tab_excel:
    st.subheader("第一步：指定数据存放路径")

    # 使用输入框替代弹窗，提高 EXE 稳定性
    path_input = st.text_input(
        "请输入或粘贴存放 Excel 的文件夹绝对路径：",
        value=st.session_state.folder_path,
        placeholder="例如: C:\\Users\\Desktop\\Project"
    )

    # 自动保存路径到 session
    st.session_state.folder_path = path_input

    if st.button("🔍 扫描并预处理文件夹"):
        if os.path.exists(path_input):
            files = [f for f in os.listdir(path_input) if f.endswith(('.xlsx', '.xls'))]
            if files:
                st.success(f"✅ 扫描成功！在路径下发现 {len(files)} 个 Excel 文件。")
                for f in files:
                    st.text(f"  📄 {f}")
            else:
                st.warning("⚠️ 路径正确，但文件夹内没有找到 Excel 文件。")
        else:
            st.error("❌ 路径不存在，请检查是否输入正确。")

# --- Tab 2: 处理中心 ---
with tab_process:
    st.subheader("第二步：确认任务清单")

    if not selected_tasks:
        st.error("请在左侧侧边栏至少勾选一项优化任务。")
    else:
        # 任务看板
        task_str = " -> ".join(selected_tasks)
        st.warning(f"当前流水线：{task_str}")

        col_info1, col_info2 = st.columns(2)
        with col_info1:
            st.markdown(f"""
            **任务明细：**
            - 目标平台: `{target_platform}`
            - 目标语言: `{target_lang}`
            - 处理目录: `{st.session_state.folder_path}`
            """)
        with col_info2:
            st.markdown(f"""
            **限制规范：**
            - 名称限制: `{st.session_state.char_limit}` 字符
            - 描述策略: `智能保留 HTML 标签`
            """)

        st.divider()

        # --- client_app.py 修复后的启动逻辑 ---

        if st.button("🔥 启动 AI 批量优化引擎", type="primary"):

            # 1. 检查 API Key 是否为空
            if not user_keys:
                st.error("❌ 错误：请在左侧边栏输入至少一个 API Key！")
            else:
                with st.status("🚀 实时任务监控后台", expanded=True) as status:
                    log_area = st.empty()  # 这里的空位用来放滚动日志
                    all_logs = []

                    # 2. 【关键修复】：将变量填入括号，对应你 UI 上的定义
                    # 注意：这里的变量名必须和你前面定义的 selectbox/slider 名一致
                    for log_msg in start_optimization_task(
                            folder_path=st.session_state.folder_path,  # 来自 Tab 1 的输入
                            platform=target_platform,  # 来自侧边栏 selectbox
                            char_limit=st.session_state.char_limit,  # 来自侧边栏 number_input
                            language=target_lang,  # 来自侧边栏 selectbox
                            api_keys=user_keys,  # 来自侧边栏 text_area 解析后的列表
                            batch_size=batch_size,  # 来自侧边栏 slider
                            sleep_time=sleep_time  # 来自侧边栏 slider
                    ):
                        # 3. 实时滚动显示日志
                        current_time = time.strftime("%H:%M:%S", time.localtime())
                        all_logs.append(f"[{current_time}] {log_msg}")

                        # 始终只展示最新的 12 行，保持界面整洁
                        log_area.code("\n".join(all_logs[-12:]), language="bash")

                        # 如果任务结束，更新状态
                        if "全部完成" in log_msg:
                            status.update(label="✅ 任务圆满结束", state="complete", expanded=False)
                            st.balloons()