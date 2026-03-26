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

# ================= 侧边栏 (已添加去重开关) =================
with st.sidebar:
    st.header("⚙️ 引擎配置")
    engine_type = st.selectbox("AI 引擎", ["Google Gemini", "DeepSeek"])

    # 默认 URL 处理
    default_url = "https://generativelanguage.googleapis.com/v1beta/openai/" if engine_type == "Google Gemini" else "https://api.deepseek.com"
    base_url = st.text_input("API URL", value=default_url)

    # 模型切换
    if engine_type == "Google Gemini":
        gemini_opts = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-1.5-flash", "gemini-1.5-pro","gemini-2.0-flash"]
        sel_m = st.selectbox("模型切换", gemini_opts, index=0)
        model_name = st.text_input("当前模型名称", value=sel_m)
    else:
        model_name = st.text_input("当前模型名称", value="deepseek-chat")

    raw_keys = st.text_area("🔑 Keys (每行一个)", height=100)
    user_keys = [k.strip() for k in raw_keys.split('\n') if k.strip()]

    st.divider()

    # --- 核心优化逻辑开关 ---
    st.subheader("🛠️ 任务逻辑控制")
    # 【新增开关】：全局去重开关
    use_deduplicate = st.checkbox("开启全局去重", value=True,
                                  help="开启：相同原始标题只消耗一次Token；关闭：每行独立优化，配合高Temperature可生成不同标题。")
    # 【新增】：AI 创造力滑块
    # 0.0 是最严谨，1.0 是正常，1.5 以上就开始起飞了
    user_temperature = st.slider(
        "🎨 AI 创造力 (Temperature)",
        min_value=0.0,
        max_value=1.5,
        value=0.7,
        step=0.1,
        help="0.0 最稳定；值越高，生成的标题差异越大，但太高可能会乱说话。"
    )
    # --- 优化参数 ---
    char_limit = st.slider("标题字符上限", 10, 200, 60)
    sleep_time = st.slider("🔥 间隔休眠时间 (秒)", 0.0, 50.0, 10.0, step=0.5)

    target_platform = st.selectbox("目标平台", ["Mercado Libre", "Amazon", "Shopee"])
    target_lang = st.selectbox("目标语言", ["英语", "西班牙语", "葡萄牙语", "中文"])

    # 批量处理个数
    batch_size = st.number_input("📦 每批次处理个数", min_value=1, max_value=100, value=50)

    st.info(f"💡 当前模式：{'🚀 高效去重模式' if use_deduplicate else '🎨 多样化铺货模式'}")
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
                        target_lang, user_keys, batch_size, sleep_time, model_name, base_url,use_deduplicate=use_deduplicate,temperature=user_temperature  # <--- 把滑块的值传进去
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

# --- TAB 2: Listing (同步 Mexico 命名与逻辑定位) ---
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
            try:
                if src_file.name.endswith('.csv'):
                    try:
                        src_df = pd.read_csv(src_file, encoding='utf-8-sig')
                    except UnicodeDecodeError:
                        src_file.seek(0)
                        src_df = pd.read_csv(src_file, encoding='gbk')
                else:
                    src_df = pd.read_excel(src_file)

                data_count = len(src_df)
                st.info(f"📈 表格已加载：**{data_count}** 行数据")

                t_col = st.selectbox("选择标题列", src_df.columns)
                i_col = st.selectbox("选择图片列", src_df.columns)
                s_col = st.selectbox("选择商品ID列 (用于生成SKU)", src_df.columns)

                st.divider()
                st.subheader("🔢 UPC 计数器")
                upc_raw = st.text_area("在此粘贴 UPC (一行一个)", height=150)
                u_list = [u.strip() for u in upc_raw.split('\n') if u.strip()]

                if u_list:
                    upc_count = len(u_list)
                    if upc_count < data_count:
                        st.warning(f"⚠️ UPC 不足！还差 {data_count - upc_count} 个")
                    else:
                        st.success(f"✅ UPC 充足 (共 {upc_count} 个)")

            except Exception as e:
                st.error(f"❌ 文件读取失败: {str(e)}")
                st.stop()

    with c2:
        tpl_file = st.file_uploader("上传美克多模板", type=['xlsx'], key="l_tpl")

        # --- 持久化状态初始化 ---
        if "gen_xlsx" not in st.session_state:
            st.session_state.gen_xlsx = None
        if "gen_json" not in st.session_state:
            st.session_state.gen_json = None
        if "gen_success" not in st.session_state:
            st.session_state.gen_success = False

        if tpl_file and src_file:
            tpl_bytes = tpl_file.getvalue()
            tpl_wb = openpyxl.load_workbook(io.BytesIO(tpl_bytes))
            target_sheet = st.selectbox("选择 Sheet", tpl_wb.sheetnames, index=len(tpl_wb.sheetnames) - 1)
            ws = tpl_wb[target_sheet]

            # 1. 完全保留你的原表头识别逻辑
            ml_headers, h_counts, header_row_idx = [], {}, None
            start_data_row = None
            char_col_idx = 2

            for r in range(1, 15):
                row_v_str = [str(ws.cell(row=r, column=c).value or "").replace('\n', ' ').replace('\r', ' ').strip() for
                             c in range(1, 100)]
                if any("Title" in x for x in row_v_str):
                    header_row_idx = r
                    for i, val in enumerate(row_v_str):
                        if "Number of characters" in val:
                            char_col_idx = i + 1
                            break

                    for v in row_v_str:
                        n = v if v != "None" and v != "" else ""
                        if n == "Mexico":
                            h_counts["Mexico"] = h_counts.get("Mexico", 0) + 1
                            if h_counts["Mexico"] == 1:
                                final_name = "Mexico (full)"
                            elif h_counts["Mexico"] == 2:
                                final_name = "Mexico"
                            else:
                                final_name = f"Mexico_{h_counts['Mexico']}"
                        else:
                            h_counts[n] = h_counts.get(n, 0) + 1
                            final_name = f"{n}_{h_counts[n]}" if h_counts[n] > 1 else n
                        ml_headers.append(final_name)
                    break

            if header_row_idx:
                for r in range(header_row_idx + 1, 40):
                    val_raw = ws.cell(row=r, column=char_col_idx).value
                    val_str = str(val_raw or "").strip()
                    if "=LEN" in val_str.upper():
                        start_data_row = r
                        break
                if not start_data_row: start_data_row = header_row_idx + 4

            st.success(f"📍 识别结果：字符限制在第 {char_col_idx} 列，起始行锁定为第 **{start_data_row}** 行")


            # 2. 完全保留你的属性匹配逻辑
            def super_clean(text):
                if not text: return ""
                t = str(text).lower()
                t = t.replace("(full)", "").replace("english", "")
                t = re.sub(r'\(.*?\)', '', t)
                t = re.sub(r'[^a-z0-9]', '', t)
                return t


            def should_show_header(h_name):
                h_low = h_name.lower()
                ch = super_clean(h_name)
                core_units = ["length", "width", "height", "package", "weight", "depth", "volume"]
                if "unit" in h_low and any(k in h_low for k in core_units):
                    return True
                if "mexico" in h_low: return True
                for jk in preset_vals.keys():
                    cjk = super_clean(jk)
                    if cjk == ch: return True
                    if len(cjk) > 5 and (cjk in ch or ch in cjk):
                        if "package" not in h_low and "package" in jk.lower():
                            if any(core in h_low for core in ["weight", "length", "width", "height"]):
                                continue
                        return True
                if re.search(r'_\d+$', h_name): return False
                garbage = ["select a value", "none", "english", "inform product"]
                if any(g in h_low for g in garbage): return False
                return True


            clean_h = [h for h in ml_headers if h and h != "" and should_show_header(h)]

            # 3. 完全保留你的自动勾选逻辑
            auto_sel = []
            for h in clean_h:
                if "Title:" in h and "inform product" in h: continue
                if "(full)" in h.lower(): continue
                h_low, ch = h.lower(), super_clean(h)
                is_matched = False
                if "unit" in h_low and any(k in h_low for k in ["length", "width", "height", "weight", "volume"]):
                    for jk, jv in preset_vals.items():
                        jk_low = jk.lower()
                        if "unit" in jk_low:
                            if ("package" in h_low) == ("package" in jk_low):
                                if any(k in h_low and k in jk_low for k in
                                       ["length", "width", "height", "weight", "volume"]):
                                    auto_sel.append(h)
                                    is_matched = True
                                    break
                if not is_matched:
                    for jk in preset_vals.keys():
                        if super_clean(jk) == ch:
                            auto_sel.append(h)
                            is_matched = True
                            break
                    if not is_matched:
                        for jk in preset_vals.keys():
                            cjk = super_clean(jk)
                            if (len(cjk) > 3 and (cjk in ch or ch in cjk)) or (
                                    "description" in cjk and "description" in ch):
                                if "package" in jk.lower() and "package" not in h_low:
                                    if any(core in h_low for core in ["weight", "length", "width", "height"]):
                                        continue
                                auto_sel.append(h)
                                break

            auto_sel = list(dict.fromkeys(auto_sel))
            to_fill = st.multiselect("确认填充属性：", clean_h, default=auto_sel)

            # 4. 完全保留你的静态值匹配逻辑
            static_data = {}
            for i, h in enumerate(to_fill):
                h_low, ch = h.lower(), super_clean(h)
                matched_val = None
                for jk, jv in preset_vals.items():
                    if super_clean(jk) == ch: matched_val = jv; break
                if matched_val is None and "unit" in h_low:
                    for jk, jv in preset_vals.items():
                        jk_low = jk.lower()
                        if "unit" in jk_low:
                            if ("package" in h_low) == ("package" in jk_low):
                                if any(k in h_low and k in jk_low for k in
                                       ["length", "width", "height", "weight", "volume"]):
                                    matched_val = jv;
                                    break
                if matched_val is None:
                    for jk, jv in preset_vals.items():
                        cjk = super_clean(jk)
                        if "unit" in h_low and "unit" not in jk.lower(): continue
                        if (len(cjk) > 3 and (cjk in ch or ch in cjk)) or (
                                "description" in cjk and "description" in ch):
                            if "package" in jk.lower() and "package" not in h_low:
                                if any(core in h_low for core in ["weight", "length", "width", "height"]):
                                    continue
                            matched_val = jv;
                            break

                col_idx = ml_headers.index(h) + 1
                opts = get_column_options(ws, tpl_wb, col_idx, header_row_idx)
                val_str = str(matched_val) if matched_val is not None else ""

                safe_key = f"input_{h}"  # 属性名是唯一的，不会因为删除其他行而变动

                if "description" in h_low or "description" in ch:
                    static_data[h] = st.text_area(f"[{h}]", value=val_str, key=f"area_{safe_key}", height=180)
                elif opts:
                    try:
                        d_idx = opts.index(val_str)
                        static_data[h] = st.selectbox(f"[{h}]", opts, index=d_idx, key=f"select_{safe_key}")
                    except:
                        static_data[h] = st.text_input(f"[{h}]", value=val_str, key=f"input_manual_{safe_key}")
                else:
                    static_data[h] = st.text_input(f"[{h}]", value=val_str, key=f"text_{safe_key}")
            # --- 5. 功能按钮区 (生成 & 清除) ---
            st.divider()
            b1, b2 = st.columns(2)
            with b1:
                if st.button("🚀 开始生成上架表", type="primary", use_container_width=True, key="btn_run"):
                    if not static_data:
                        st.warning("⚠️ 没选属性！")
                    else:
                        with st.spinner("生成中..."):
                            # 调用 Logic 生成 Excel
                            res_xlsx, _ = process_mercado_listing(
                                source_df=src_df,
                                template_bytes=tpl_bytes,
                                sheet_name=target_sheet,
                                mapping_config={'title_col': t_col, 'img_col': i_col, 'sku_col': s_col},
                                static_fills=static_data,
                                upc_list=u_list,
                                start_row=start_data_row
                            )
                            # 生成 JSON
                            clean_json_dict = {re.sub(r'_\d+$', '', k): v for k, v in static_data.items()}

                            # 存入缓存
                            st.session_state.gen_xlsx = res_xlsx
                            st.session_state.gen_json = json.dumps(clean_json_dict, ensure_ascii=False, indent=4)
                            st.session_state.gen_success = True

            with b2:
                if st.button("🗑️ 清除生成结果", use_container_width=True, key="btn_clear"):
                    st.session_state.gen_xlsx = None
                    st.session_state.gen_json = None
                    st.session_state.gen_success = False
                    st.rerun()

            # --- 6. 结果持久化展示 ---
            if st.session_state.gen_success and st.session_state.gen_xlsx:
                st.success("✅ 文件已就绪")
                dl1, dl2 = st.columns(2)
                import time

                ts = int(time.time())
                with dl1:
                    st.download_button("📥 下载 Excel", data=st.session_state.gen_xlsx, file_name=f"Ready_{ts}.xlsx",
                                       key="dl_x")
                with dl2:
                    st.download_button("📄 下载 JSON", data=st.session_state.gen_json, file_name=f"Config_{ts}.json",
                                       key="dl_j")