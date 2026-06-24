import gc
import os

import pandas as pd
import time
import re
import itertools
import io

import psutil
from openai import OpenAI
import sqlite3
import datetime

# 定义版本号
VERSION = "v2.5.4-FilterRows"


def get_memory_info():
    process = psutil.Process(os.getpid())
    mem_mb = process.memory_info().rss / 1024 / 1024  # 转换为 MB
    return mem_mb


# --- 统一数据库路径 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 强制指向 test 目录下的那个有数据的数据库
db_path = os.path.abspath(os.path.join(BASE_DIR, "..", "seo_master.db"))


def ai_rewrite_engine(id_titles_dict, char_limit, platform, language, key_pool, model_name, base_url,
                      is_retry=False, temperature=0, opt_mode="AI优化标题", negative_keywords=""):
    """
    核心优化引擎：逻辑完全保持不变，仅修复违禁词，去除 self 错误引用
    """
    import re
    import time
    from openai import OpenAI  # 确保安全导入

    if not id_titles_dict:
        return {}, "Empty"

    input_payload = "\n".join([f"#{k}: {v}" for k, v in id_titles_dict.items()])

    # ─── 🛠️ 1. 违禁词指令解析（保持原生结构，仅增强提取） ───
    neg_instruction = ""
    neg_warning_flat = ""
    if negative_keywords and negative_keywords.strip():
        clean_neg_words = [w.strip() for w in negative_keywords.replace("，", ",").split(",") if w.strip()]
        if clean_neg_words:
            formatted_words = ", ".join([f"'{w}'" for w in clean_neg_words])
            neg_instruction = f"\n❌ **绝对禁止出现的词汇**：{negative_keywords} (严禁在任何情况下使用这些词)"
            neg_warning_flat = f"（绝对禁止包含违禁词：{formatted_words}）"

    retry_warning = ""
    if is_retry:
        retry_warning = f"\n⚠️ [重要] 之前的尝试依然超长，包含空格必须在 {char_limit} 字符以内，确保达标！"

    mode_instruction = ""
    if opt_mode == "列组合优化":
        mode_instruction = (
            "3. **强制关键词要求**：输入内容中包含 [原标题] 和 [附加关键词]。\n"
            "   - 你必须将 [附加关键词] 完整地整合进新标题中，不得遗漏或缩写。\n"
            "   - 在满足关键词存在的前提下，再进行SEO优化和长度控制。"
        )
    else:
        mode_instruction = "3. **SEO优化要求**：对原标题进行语义精简，提取核心卖点，提升点击率。"

    # ─── 🛠️ 2. 平台规则判断（内部每一句文案完全保持你原本的逻辑） ───
    if "乐天" in platform or "Rakuten.fr" in platform.lower():
        platform_instruction = (
            f"你现在是【乐天 Rakuten】SEO专家。要求如下：\n"
            f"1. **SEO最大化**：乐天流量高度依赖关键词。请在 {char_limit} 字符内尽量填满核心词及相关长尾词。删除原标题中的具体尺寸属性（如 30x40cm）。\n"
            f"2. **符号规范**：仅允许使用空格或分隔符 '-'，严禁使用逗号、分号或其他特殊符号。\n"
            f"3. **法语类目规则**：‘手机/平板配件’类目手机型号前必须加 'pour '，其他类目严禁出现 'pour'。\n"
            f"4. **多样化与结构逻辑**：确保同批标题句式不雷同，通过以下重心切换实现：\n"
            f"     * 重心A (属性优先): [图案/颜色] + [核心词] + [功能/数量]\n"
            f"     * 重心B (功能优先): [功能短语] + [核心词] + [数量/属性]\n"
            f"     * 重心C (核心优先): [核心词] + [数量] + [场景用语] + [属性]\n"
            f"     * 重心D (数量优先): [数量词] + [属性] + [核心词] + [功能] (注：仅当原标题明确包含数量时使用)\n"
            f"5. **数量与属性保护（红线原则）**：\n"
            f"   - **严禁无中生有**：如果原标题未提及数量，绝对禁止在优化标题中添加任何数量词（如 2pcs, 2 pièces, Set 等）。\n"
            f"   - **同义词替换**：仅在原标题已有数量时，才允许从 (2pcs, 2-Pack, Lot de 2, Lot de 2 pièces) 中随机选择。否则必须忽略。 \n"
            f"   - **精准保留**：删除 '1 pièce'。必须保留颜色(Color)、材质(Material)或图案(Pattern)。\n"
            f"{mode_instruction}\n"
        )
    elif "noon" in platform.lower() or "波兰" in platform:
        platform_instruction = (
            f"你现在是【波兰 noon 平台】SEO 专家。要求如下：\n"
            f"1. **核心布局**：波兰语单词较长，必须严格在 {char_limit} 字符内。**核心产品词必须置于标题最前面**。删除原标题中的具体尺寸/尺码（如 30x40cm 等）。\n"
            f"2. **符号指标**：仅允许使用空格。严禁使用逗号、分号、括号或任何特殊字符。\n"
            f"3. **多样化与结构控制**：同一批标题严禁句式雷同，通过以下重心切换实现多样化：\n"
            f"     * 重心A (属性优先): [图案/颜色] + [核心词] + [功能/数量]\n"
            f"     * 重心B (功能优先): [功能短语] + [核心词] + [数量/属性]\n"
            f"     * 重心C (核心优先): [核心词] + [数量] + [场景用语] + [属性]\n"
            f"     * 重心D (数量优先): [数量词] + [属性] + [核心词] + [功能] (注：仅当原标题有数量时才使用此模式)\n"
            f"4. **数量处理原则（关键）**：\n"
            f"   - **严禁虚构数量**：如果原标题未提及数量，绝对禁止在优化标题中加入任何数量词（如 2pcs, 1 Pair 等）。\n"
            f"   - **仅限同义旋转**：只有原标题存在数量时，才允许从 (2pcs, 2-Pack, Zestaw 2 szt) 中随机旋转，否则必须忽略这些词。\n"
            f"5. **属性保护**：删除 '1pc'。必须保留颜色(Color)、材质(Material)或图案(Pattern)。\n"
            f"{mode_instruction}\n"
        )
    elif "allegro" in platform.lower() or "波兰" in platform:
        platform_instruction = (
            f"你现在是【Allegro 官方 SEO 专家】。请严格遵守以下平台硬性规则：\n"
            f"1. **首位词原则**：**标题的第一个词必须是产品的核心名词**。严禁以形容词、品牌名或促销词开头。\n"
            f"2. **字符约束**：总长度严格控制在 {char_limit} 字符内（含空格）。请优先保留核心属性，删减无意义修饰词，删除原标题的尺寸/尺码属性。\n"
            f"3. **纯净格式**：禁止出现任何特殊符号（如：- , / * +），仅允许使用空格。不要使用所有字母大写。\n"
            f"4. **地道语法**：确保语法符合当地语言习惯，适配描述统一使用 'do [Model]' 格式。\n"
            f"5. **属性保护**：删除 '1 szt. '或'1pc'，如果本身有 '2 szt. 以上套装属性，则保留下来，如果没有不要随便添加。必须保留颜色(Color)、材质(Material)或图案(Pattern)。\n"
            f"{mode_instruction}\n"
        )
    else:
        platform_instruction = (
            f"你现在是【美克多 Mercado Libre】官方上架专家。要求如下：\n"
            f"1. **极致极简与尺寸清空**：严格控制在 {char_limit} 字符内。**必须彻底删除所有尺寸、尺码、规格参数**（例如：严禁出现 '13-17 inch', '40x40cm', 'Size S/M/L', '10.5mm' 等）。\n"
            f"2. **类目规则**：‘手机/平板配件’类目手机前面必须加 'for '，其他类目严禁出现 'for'。\n"
            f"3. **符号硬指标**：**严禁使用任何逗号、分号或特殊符号**，仅允许空格。\n"
            f"4. **多样化与结构打乱**：随机切换以下四种重心，确保句式不雷同：\n"
            f"     * 重心A (属性优先): [图案/颜色] + [核心词] + [功能/数量]\n"
            f"     * 重心B (功能优先): [功能短语] + [核心词] + [数量/属性]\n"
            f"     * 重心C (核心优先): [核心词] + [数量] + [场景用语] + [属性]\n"
            f"     * 重心D (数量优先): [数量词变体] + [属性] + [核心词] + [功能]\n"
            f"5. **数量与属性保护（核心原则）**：\n"
            f"   - **禁止虚构数量**：如果原标题中没有明确提及 '2pcs/1 pair/Set' 等数量，严禁在优化标题中添加任何数量词。\n"
            f"   - **禁止数字残留**：除数量词外，标题中不应出现任何代表长宽高的数字。\n"
            f"   - **同义词替换**：仅当原标题包含数量时，才可随机交替使用同义词（如将 2pcs 替换为 2-Pack 或 Set of 2）。\n"
            f"   - **必须保留**：颜色(Color)、材质(Material)或图案(Pattern)。删除无意义的 '1pc'。\n"
        )

    common_rules = (
        f"6. **列组合约束**：{'必须完整保留 [附加关键词] 内容，不得删减。' if opt_mode == '列组合优化' else '精简非核心修饰词。'}"
    )

    # ─── 🛠️ 3. Prompt 组装与 System 动态注入（增加禁词双层把控） ───
    prompt = (
        f"{platform_instruction}\n"
        f"{common_rules}\n"
        f"语言要求：{language}，句子要纯正语言，包括介词也要用相对应的语言\n"
        f"{neg_instruction}\n"  # 保持原位
        f"格式要求：只返回 '#ID: 结果'，每行一条。\n"
        f"待处理数据：\n{input_payload}\n{retry_warning}"
    )

    system_content = "Professional SEO expert. Strictly follows char limits."
    if neg_warning_flat:
        # 如果有违禁词，强行打到 System 大脑神经元上
        system_content += f" CRITICAL RULE: Under NO circumstances are you allowed to use these words: {neg_warning_flat}."

    # ─── 🛠️ 4. 循环调用与接口提取逻辑 ───
    for attempt in range(1, 4):
        try:
            current_key = next(key_pool)
            client = OpenAI(api_key=current_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                timeout=30
            )

            output = response.choices[0].message.content
            matches = re.findall(r'#(\d+)[:：](.*)', output)
            batch_results = {}
            success_count = 0

            for m_id, m_content in matches:
                u_id = int(m_id)
                optimized_text = " ".join(m_content.strip().replace(',', ' ').split())
                status = "Optimized" if len(optimized_text) <= char_limit else "Retry_Needed"

                # ─── 🛡️ 唯一核心进化：本地代码级防护盾（已去除 self 引用，改为 standard print） ───
                if negative_keywords and negative_keywords.strip():
                    for word in clean_neg_words:
                        if word.lower() in optimized_text.lower():
                            status = "Retry_Needed"  # 抓到违禁词，强行拦截打入重试队列
                            print(f"⚠️ [探针警报] 拦截到 AI 标题 #{u_id} 中漏出违禁词 '{word}'，已强行打回重试！")
                            break

                if status == "Optimized": success_count += 1
                batch_results[u_id] = (optimized_text, status)

            return batch_results, f"OK({success_count}/{len(id_titles_dict)})"
        except Exception as e:
            if attempt < 3: time.sleep(3); continue
            return {}, f"API_Error: {str(e)}"
    return {}, "Max_Retries_Exceeded"


def start_optimization_task(uploaded_files, platform, char_limit, language, api_keys, batch_size, sleep_time,
                            model_name, base_url, user_id, current_sid, use_deduplicate=True, deduplicate_limit=99,
                            temperature=0.7,
                            existing_df=None, opt_mode="AI优化标题", selected_extra_cols=None, selected_sheet=None,
                            negative_keywords=None,
                            delete_negative_rows=False):  # 🎯 核心新增参数：delete_negative_rows 控制开关
    """
    任务分发函数：修复断点续传下的文件名丢失与结果合并问题
    """
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    try:
        key_pool = itertools.cycle(api_keys)
        processed_results = []
        # --- 0. 权限与会话预检 ---
        try:
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE optimized_history ADD COLUMN opt_mode TEXT")
            cursor.execute("ALTER TABLE optimized_history ADD COLUMN language TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass

        cursor.execute("SELECT expiry_date, last_session_id, is_active FROM users WHERE user_id = ?", (user_id,))
        user_info = cursor.fetchone()

        if not user_info:
            yield "❌ 用户不存在，任务终止"
            return

        expiry_date_str, last_sid, is_active = user_info

        if is_active == 0:
            yield "🛑 账号已被管理员禁用或注销，任务终止。"
            return

        if datetime.datetime.strptime(expiry_date_str, '%Y-%m-%d').date() < datetime.date.today():
            yield "❌ 账号已过期，请续费后使用"
            return

        yield f"🚀 引擎启动 | 用户ID: {user_id} | 模式: {opt_mode}"

        if existing_df is not None:
            files_to_process = [("BUFFER_TASK", existing_df)]
        else:
            files_to_process = [(f.name, f) for f in uploaded_files] if uploaded_files else []

        for fname_raw, file_source in files_to_process:
            df = None
            if fname_raw == "BUFFER_TASK":
                df = file_source
                fname = "Recovered_Task.xlsx"
                yield f"🔄 正在从断点恢复任务..."
            else:
                fname = fname_raw
                yield f"📂 正在读取: {fname}"
                try:
                    if fname.lower().endswith(('.xlsx', '.xls')):
                        sheet_to_read = selected_sheet if selected_sheet else 0
                        df = pd.read_excel(file_source, sheet_name=sheet_to_read)
                    else:
                        encodings_to_try = ['utf-8-sig', 'gb18030', 'utf-8']
                        df = None
                        last_err = None

                        for enc in encodings_to_try:
                            try:
                                file_source.seek(0)
                                df = pd.read_csv(file_source, encoding=enc)
                                break
                            except Exception as e:
                                last_err = e
                                continue

                        if df is None:
                            raise Exception(f"所有常用编码(UTF8/GBK)均无法解析: {last_err}")

                    df = df.dropna(axis=1, how='all').dropna(axis=0, how='all')
                    df = df.reset_index(drop=True)

                except Exception as e:
                    yield f"❌ 读取失败: {repr(e)}"
                    continue

            yield f"✅ 成功载入 {len(df)} 条数据"

            # --- 2. 标题列定位 (严格表头模式) ---
            target_col = None
            title_keywords = ['标题', 'title', 'name', '商品名称', '名称']

            for col_name in df.columns:
                clean_name = str(col_name).strip().lower()
                if any(k in clean_name for k in title_keywords) and "unnamed" not in clean_name:
                    target_col = col_name
                    break

            if target_col:
                yield f"✅ 已锁定标题列: {target_col}"
            else:
                yield "❌ 错误：未能在表格中找到有效的【标题】列，任务终止。"
                return

                # ─── 🎯 新增核心逻辑：违禁词包含则彻底剔除整行数据 ───
            if delete_negative_rows and negative_keywords and negative_keywords.strip():
                clean_neg_words = [w.strip() for w in negative_keywords.replace("，", ",").split(",") if w.strip()]
                if clean_neg_words:
                    yield f"🛡️ 已开启敏感词整行剔除，正在扫描原生标题违禁词..."
                    initial_count = len(df)

                    # 构造过滤条件：如果标题包含任意一个违禁词，返回 True
                    def has_negative_word(val):
                        if pd.isna(val):
                            return False
                        title_str = str(val).lower()
                        return any(word.lower() in title_str for word in clean_neg_words)

                    # 找出所有包含违禁词的行掩码
                    drop_mask = df[target_col].apply(has_negative_word)

                    # 剔除这些行，并重新重置索引
                    df = df[~drop_mask].reset_index(drop=True)
                    deleted_count = initial_count - len(df)
                    if deleted_count > 0:
                        yield f"🚨 [前置过滤] 发现并彻底踢除了 {deleted_count} 行包含违禁词的数据，剩余可优化数据: {len(df)} 条。"
                    else:
                        yield f"✅ 前置扫描完成，未发现包含违禁词的原生行数据。"

            if 'AI_Status' not in df.columns:
                df['AI_Status'] = "Pending"
            else:
                df['AI_Status'] = df['AI_Status'].fillna("Pending").astype(str)

            def prepare_input(row):
                val = row.get(target_col, "")
                original_title = str(val).strip() if pd.notna(val) else ""
                if not original_title or original_title.lower() == 'nan':
                    return ""
                if opt_mode == "列组合优化" and selected_extra_cols:
                    extra_parts = []
                    for col in selected_extra_cols:
                        if col in row and pd.notna(row[col]):
                            c_val = str(row[col]).strip()
                            if c_val.lower() != 'nan' and c_val != "":
                                extra_parts.append(c_val)
                    extra_info = " ".join(extra_parts)
                    return f"[原标题]: {original_title} | [附加关键词]: {extra_info}"
                return original_title

            # --- 3. 轮次优化逻辑 (1-3轮) ---
            for round_idx in range(1, 4):
                pending_mask = (df['AI_Status'] != 'Optimized')
                pending_df = df[pending_mask].copy()
                if pending_df.empty:
                    break

                title_to_indices = {}
                if use_deduplicate:
                    raw_groups = {}
                    for idx, row in pending_df.iterrows():
                        input_str = prepare_input(row)
                        raw_groups.setdefault(input_str, []).append(idx)

                    for input_val, all_indices in raw_groups.items():
                        for i in range(0, len(all_indices), deduplicate_limit):
                            chunk = all_indices[i: i + deduplicate_limit]
                            unique_key = f"{input_val}__grp{i}"
                            title_to_indices[unique_key] = chunk
                else:
                    for idx, row in pending_df.iterrows():
                        input_str = prepare_input(row)
                        title_to_indices[f"{input_str}__row{idx}"] = [idx]

                unique_keys = list(title_to_indices.keys())
                total_unique = len(unique_keys)
                yield f"🔄 [第 {round_idx} 轮] 待处理项: {total_unique}"

                # --- 4. Batch 批处理执行 ---
                for i in range(0, total_unique, batch_size):
                    current_batch_keys = unique_keys[i: i + batch_size]
                    batch_payload = {}

                    for b_idx, k in enumerate(current_batch_keys):
                        raw_input = k.split("__grp")[0].split("__row")[0]
                        cursor.execute("""
                                            SELECT optimized_title FROM optimized_history 
                                            WHERE user_id = ? 
                                            AND original_input = ? 
                                            AND platform = ? 
                                            AND char_limit = ?
                                            AND opt_mode = ?
                                        """, (user_id, raw_input, platform, char_limit, opt_mode))
                        cache = cursor.fetchone()

                        if cache:
                            opt_text = cache[0]
                            for row_idx in title_to_indices[k]:
                                df.at[row_idx, target_col] = opt_text
                                df.at[row_idx, 'AI_Status'] = "Optimized"
                        else:
                            batch_payload[b_idx] = raw_input

                    total_count = len(current_batch_keys)
                    cache_hit_count = total_count - len(batch_payload)

                    if cache_hit_count > 0 and len(batch_payload) > 0:
                        yield f"💾 缓存命中：已自动恢复 {cache_hit_count} 条记录，剩余 {len(batch_payload)} 条请求 AI..."
                    if batch_payload:
                        results, log_msg = ai_rewrite_engine(
                            id_titles_dict=batch_payload,
                            char_limit=char_limit,
                            platform=platform,
                            language=language,
                            key_pool=key_pool,
                            model_name=model_name,
                            base_url=base_url,
                            is_retry=(round_idx > 1),
                            temperature=temperature,
                            opt_mode=opt_mode,
                            negative_keywords=negative_keywords
                        )
                        current_mem = get_memory_info()
                        print(f"DEBUG: 用户 {user_id} 进度 {i}/{total_unique} | 内存: {current_mem:.2f} MB")

                        if current_mem > 400:
                            yield f"⚠️ 系统内存警告: {current_mem:.0f}MB / 512MB。检测到内存极高，正在尝试清理..."
                            gc.collect()
                            time.sleep(0.2)
                        for batch_id, (opt_text, status) in results.items():
                            target_key = current_batch_keys[batch_id]
                            clean_text = target_key.split("__grp")[0].split("__row")[0]
                            for row_idx in title_to_indices[target_key]:
                                df.at[row_idx, target_col] = opt_text
                                df.at[row_idx, 'AI_Status'] = status

                            if status == "Optimized":
                                now_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                                cursor.execute("""
                                    INSERT OR REPLACE INTO optimized_history 
                                    (user_id, original_input, optimized_title, platform, char_limit, opt_mode, timestamp) 
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (user_id, clean_text, opt_text, platform, char_limit, opt_mode, now_time))
                        conn.commit()
                    else:
                        log_msg = "⚡ 100% 缓存命中（零秒恢复）"

                    yield df
                    yield f"📝 {log_msg} | 进度: {min(i + batch_size, total_unique)}/{total_unique}"
                    if i + batch_size < total_unique and batch_payload:
                        time.sleep(sleep_time)

            final_stats = df['AI_Status'].value_counts()
            yield f"📊 {fname} 处理完成！成功: {final_stats.get('Optimized', 0)} 条。"
            processed_results.append((fname, df))

        yield "FINISH_SIGNAL"
        yield processed_results

    except Exception as e:
        yield f"❌ 任务运行出错: {str(e)}"

    finally:
        conn.close()