import re
import sys
import streamlit as st
import pandas as pd
import os
import time
import io
import openpyxl
import json
root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_path not in sys.path:
    sys.path.insert(0, root_path)
try:
    # 此时 Python 就能在根目录下找到 core 文件夹了
    from core.trade import start_optimization_task, VERSION
    from core.listing_logic import process_mercado_listing, get_column_options
except ImportError as e:
    st.error(f"核心模块导入失败: {e}")
    st.info(f"当前搜索路径: {sys.path[0]}") # 方便你在云端调试路径
    st.stop()

st.set_page_config(page_title=f"跨境AI大师 {VERSION}", layout="wide", page_icon="🚀")

# --- 核心状态初始化 ---
if 'optimization_done' not in st.session_state: st.session_state.optimization_done = False
if 'final_results' not in st.session_state: st.session_state.final_results = []
if 'process_logs' not in st.session_state: st.session_state.process_logs = []

# ================= 权限校验 =================
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if not st.session_state.authenticated:
    st.title("🔐 软件授权验证")
    auth_code = st.text_input("请输入卡密", type="password")
    if st.button("立即登录"):
        if auth_code == "888888":
            st.session_state.authenticated = True
            st.rerun()
    st.stop()

# ================= 侧边栏 (所有功能复原) =================
with st.sidebar:
    st.header("⚙️ 引擎配置")
    engine_type = st.selectbox("AI 引擎", ["Google Gemini", "DeepSeek"])
    base_url = st.text_input("API URL", value="https://generativelanguage.googleapis.com/v1beta/openai/")

    # 模型切换
    if engine_type == "Google Gemini":
        gemini_opts = ["gemini-2.5-flash", "gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-2.5-pro"]
        sel_m = st.selectbox("模型切换", gemini_opts, index=0)
        model_name = st.text_input("当前模型", value=sel_m if sel_m != "自定义" else "gemini-2.5-flash")
    else:
        model_name = st.text_input("模型", value="deepseek-chat")

    raw_keys = st.text_area("🔑 Keys (每行一个)", height=100)
    user_keys = [k.strip() for k in raw_keys.split('\n') if k.strip()]

    st.divider()
    # --- 复原：调整参数 ---
    char_limit = st.slider("标题字符上限", 10, 200, 60)
    # 【关键复原】：休眠时间滑块
    sleep_time = st.slider("🔥 间隔休眠时间 (秒)", 0.0, 50.0, 10.0, step=0.5)

    target_platform = st.selectbox("目标平台", ["Mercado Libre", "Amazon", "Shopee"])
    target_lang = st.selectbox("目标语言", ["英语", "西班牙语", "葡萄牙语", "中文"])
    # --- 新增：批量处理个数 ---
    batch_size = st.number_input("📦 每批次处理个数", min_value=1, max_value=100, value=50)
# ================= 主界面 =================
tab_seo, tab_listing = st.tabs(["🔥 标题批量优化轮", "📦 美克多列表自动上架"])

# --- TAB 1: 标题优化 (日志 & 清除 & 任务逻辑) ---
with tab_seo:
    st.title("🚀 AI 标题优化引擎")

    if st.session_state.optimization_done:
        if st.button("🗑️ 清空所有结果与日志", use_container_width=True):
            st.session_state.optimization_done = False
            st.session_state.final_results = []
            st.session_state.process_logs = []
            st.rerun()

    uploaded_files = st.file_uploader("上传待处理文件", type=['xlsx', 'csv'], accept_multiple_files=True)

    if uploaded_files and not st.session_state.optimization_done:
        if st.button("🔥 启动多轮优化", type="primary", use_container_width=True):
            if not user_keys:
                st.error("❌ 请先配置 API Key")
            else:
                st.session_state.process_logs = []
                with st.status("🚀 AI 正在努力工作中...", expanded=True) as status:
                    log_area = st.empty()
                    # 传入 sleep_time 给后端任务
                    task_gen = start_optimization_task(
                        uploaded_files, target_platform, char_limit,
                        target_lang, user_keys, batch_size, sleep_time, model_name, base_url
                    )

                    for msg in task_gen:
                        if msg == "FINISH_SIGNAL":
                            st.session_state.final_results = next(task_gen)
                            st.session_state.optimization_done = True
                            status.update(label="✅ 任务圆满完成！", state="complete")
                        else:
                            l_entry = f"[{time.strftime('%H:%M:%S')}] {msg}"
                            st.session_state.process_logs.append(l_entry)
                            log_area.code("\n".join(st.session_state.process_logs[-15:]), language="bash")
                st.rerun()

    # 显示结果和持久化日志
    if st.session_state.optimization_done:
        st.subheader("✅ 优化结果清单")
        with st.expander("查看完整处理日志"):
            st.code("\n".join(st.session_state.process_logs), language="bash")

        d_cols = st.columns(3)
        for idx, (f_name, df_res) in enumerate(st.session_state.final_results):
            with d_cols[idx % 3]:
                st.download_button(f"📥 下载 {f_name}", df_res.to_csv(index=False).encode('utf-8-sig'), f"Opt_{f_name}",
                                   key=f"dl_{idx}")

# --- TAB 2: Listing (完整版：含 Mexico 命名、极致清洗、数据统计、UPC 计数器) ---
with tab_listing:
    st.title("📦 自动化填充 (JSON+UPC)")

    json_conf_file = st.file_uploader("导入类目 JSON 配置", type=['json'])
    preset_vals = {}
    if json_conf_file:
        try:
            preset_vals = json.loads(json_conf_file.read().decode('utf-8-sig'))
            st.success("✅ JSON 加载成功")
        except:
            st.error("❌ JSON 格式错误")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        src_file = st.file_uploader("上传结果表", type=['xlsx', 'csv'], key="l_src")
        data_count = 0
        if src_file:
            src_df = pd.read_csv(src_file) if src_file.name.endswith('.csv') else pd.read_excel(src_file)
            data_count = len(src_df)

            # --- 数据统计展示 ---
            st.info(f"📈 表格已加载：**{data_count}** 行数据")

            t_col = st.selectbox("选择标题列", src_df.columns)
            i_col = st.selectbox("选择图片列", src_df.columns)

            st.divider()
            st.subheader("🔢 批量导入 UPC 码")
            upc_raw = st.text_area("在此粘贴 UPC (一行一个)", height=150, placeholder="粘贴UPC列表...")
            u_list = [u.strip() for u in upc_raw.split('\n') if u.strip()]

            # --- UPC 计数器逻辑 ---
            if u_list:
                upc_count = len(u_list)
                if upc_count < data_count:
                    st.warning(f"⚠️ UPC 数量不足！现有 **{upc_count}** 个，缺 **{data_count - upc_count}** 个")
                elif upc_count == data_count:
                    st.success(f"✅ UPC 数量完美匹配 (共 {upc_count} 个)")
                else:
                    st.success(f"✅ UPC 充足 (共有 {upc_count} 个，多出 {upc_count - data_count} 个)")
            else:
                st.write("请粘贴 UPC 码以开始计数")

    with c2:
        tpl_file = st.file_uploader("上传美克多模板", type=['xlsx'], key="l_tpl")
        if tpl_file and src_file:
            tpl_bytes = tpl_file.getvalue()
            tpl_wb = openpyxl.load_workbook(io.BytesIO(tpl_bytes))
            target_sheet = st.selectbox("选择 Sheet", tpl_wb.sheetnames, index=len(tpl_wb.sheetnames) - 1)
            ws = tpl_wb[target_sheet]

            # 1. 提取并重命名表头 (针对 Mexico 进行 full 命名)
            ml_headers, h_counts, header_row_idx = [], {}, 1
            for r in range(1, 11):
                row_v = [str(ws.cell(row=r, column=c).value) for c in range(1, ws.max_column + 1)]
                if any("Title" in (x or "") for x in row_v):
                    for v in row_v:
                        raw_n = str(v).strip()
                        if raw_n == "Mexico":
                            h_counts["Mexico"] = h_counts.get("Mexico", 0) + 1
                            if h_counts["Mexico"] == 1:
                                final_name = "Mexico (full)"
                            elif h_counts["Mexico"] == 2:
                                final_name = "Mexico"
                            else:
                                final_name = f"Mexico_{h_counts['Mexico']}"
                        else:
                            h_counts[raw_n] = h_counts.get(raw_n, 0) + 1
                            final_name = f"{raw_n}_{h_counts[raw_n]}" if h_counts[raw_n] > 1 else raw_n
                        ml_headers.append(final_name)
                    header_row_idx = r;
                    break

            clean_h = [h for h in ml_headers if h and "None" not in h]


            # 极致清洗函数：排除 (full)、星号、换行、空格、English 关键字干扰
            def super_clean(text):
                if not text: return ""
                t = str(text).replace("(full)", "").replace("English", "")
                return re.sub(r'\(.*?\)|[\*\n\r\s]', '', t).lower()


            # 2. 自动勾选逻辑 (收紧规则，防止误选 Title)
            auto_sel = []
            for h in clean_h:
                # --- 新增排除逻辑 ---
                if "Mexico (full)" in h: continue  # 强制排除 Mexico (full)
                if "Title:" in h and "inform product" in h: continue  # 排除长标题
                # ------------------

                ch = super_clean(h)
                for jk in preset_vals.keys():
                    cjk = super_clean(jk)
                    if cjk == ch and len(cjk) > 0:
                        auto_sel.append(h)
                        break
                    elif "description" in cjk and "description" in ch:
                        auto_sel.append(h)
                        break

            to_fill = st.multiselect("确认填充属性：", clean_h, default=auto_sel)

            static_data = {}
            for i, h in enumerate(to_fill):
                ch = super_clean(h)
                matched_val = None
                for jk, jv in preset_vals.items():
                    cjk = super_clean(jk)
                    if cjk == ch or ("description" in cjk and "description" in ch):
                        matched_val = jv;
                        break

                col_idx = ml_headers.index(h) + 1
                opts = get_column_options(ws, tpl_wb, col_idx, header_row_idx)
                val_str = str(matched_val) if matched_val is not None else ""

                if opts:
                    try:
                        d_idx = opts.index(val_str)
                        static_data[h] = st.selectbox(f"[{h}]", opts, index=d_idx, key=f"s_{i}")
                    except ValueError:
                        static_data[h] = st.text_input(f"[{h}] (手动填入)", value=val_str, key=f"s_in_{i}")
                else:
                    if "description" in h.lower() or "description" in ch:
                        static_data[h] = st.text_area(f"[{h}]", value=val_str, key=f"t_{i}", height=180)
                    else:
                        static_data[h] = st.text_input(f"[{h}]", value=val_str, key=f"t_{i}")

            if st.button("🚀 开始生成上架表", type="primary", use_container_width=True):
                res = process_mercado_listing(src_df, tpl_bytes, target_sheet,
                                              {'title_col': t_col, 'img_col': i_col}, static_data, u_list)
                st.success(f"✅ 生成成功！已处理 {len(src_df)} 条数据。")
                st.download_button("📥 立即下载生成的表格", res, f"ML_Ready.xlsx", use_container_width=True)