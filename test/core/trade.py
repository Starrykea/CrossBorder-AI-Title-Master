import os

import pandas as pd
import time
import re
import itertools
import io
from openai import OpenAI
import sqlite3
import datetime
# 定义版本号
VERSION = "v2.5.3-Deduplicate"

# --- 统一数据库路径 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 强制指向 test 目录下的那个有数据的数据库
db_path = os.path.abspath(os.path.join(BASE_DIR, "..", "seo_master.db"))
def ai_rewrite_engine(id_titles_dict, char_limit, platform, language, key_pool, model_name, base_url,
                      is_retry=False, temperature=0, opt_mode="AI优化标题", negative_keywords=""):
    """
    核心优化引擎：逻辑保持不变
    """
    if not id_titles_dict:
        return {}, "Empty"

    input_payload = "\n".join([f"#{k}: {v}" for k, v in id_titles_dict.items()])
    retry_warning = ""
    if is_retry:
        retry_warning = f"\n⚠️ [重要] 之前的尝试依然超长，包含空格必须在 {char_limit} 字符以内，确保达标！"
    neg_instruction = ""
    if negative_keywords and negative_keywords.strip():
        neg_instruction = f"\n❌ **绝对禁止出现的词汇**：{negative_keywords} (严禁在任何情况下使用这些词)"
    mode_instruction = ""
    if opt_mode == "列组合优化":
        mode_instruction = (
            "3. **强制关键词要求**：输入内容中包含 [原标题] 和 [附加关键词]。\n"
            "   - 你必须将 [附加关键词] 完整地整合进新标题中，不得遗漏或缩写。\n"
            "   - 在满足关键词存在的前提下，再进行SEO优化和长度控制。"
        )
    else:
        mode_instruction = "3. **SEO优化要求**：对原标题进行语义精简，提取核心卖点，提升点击率。"
    if "乐天" in platform or "Rakuten.fr" in platform.lower():
        # 乐天逻辑：强调 SEO 堆砌、长尾词、允许特定符号
        platform_instruction = (
            f"你现在是【乐天 Rakuten】SEO专家。要求如下：\n"
            f"1. **SEO最大化**：乐天流量依赖关键词，请在 {char_limit} 字符内尽量填满核心词及相关长尾词,，删除原标题的尺寸/尺码属性。。\n"
            f"2. **符号限制**：允许使用空格或分隔符 '-'。\n"
            f"3. **类目规则**：‘手机/平板配件’类目手机前面必须加 'pour '，其他类目严禁出现 'pour'。\n"
            f"4. **多样化**：同一批标题严禁句式雷同，随机切换重心（属性优先/功能优先/场景优先）。\n"
            f"   - **同义词旋转**：随机交替使用 (2pcs, 1 Pair, 2-Pack, Set of 2) 以及 (Oven Mitts, Baking Gloves, Kitchen Mittens)。\n"
            f"   - **结构打乱**：随机切换以下四种重心：\n"
            f"     * 重心A (属性优先): [图案/颜色] + [核心词] + [功能/数量]\n"
            f"     * 重心B (功能优先): [功能短语] + [核心词] + [数量/属性]\n"
            f"     * 重心C (核心优先): [核心词] + [数量] + [场景用语] + [属性]\n"
            f"     * 重心D (数量优先): [数量词变体] + [属性] + [核心词] + [功能]\n"
            f"5. **属性保护**：删除 '1 pièces '，如果本身有 '2 pièces ' 以上套装属性，则保留下来，如果没有不要随便添加，必须保留颜色(Color)、材质(Material)或图案(Pattern)。\n"
            f"{mode_instruction}\n"
        )
    elif "noon" in platform.lower() or "波兰" in platform:
        # 波兰 Allegro 逻辑：强调标题可读性、核心词置前、语法地道
        platform_instruction = (
            f"你现在是【波兰 noon平台】SEO专家。要求如下：\n"
            f"1. **核心逻辑**：波兰语单词较长，请在 {char_limit} 字符内合理布局。**核心产品词必须放在标题最前面**,，删除原标题的尺寸/尺码属性。。\n"
            f"2. **符号指标**：仅允许使用空格，禁止使用任何特殊符号或表情。\n"
            f"3. **多样化**：同一批标题严禁句式雷同，随机切换重心（属性优先/功能优先/场景优先）。\n"
            f"   - **同义词旋转**：随机交替使用 (2pcs, 1 Pair, 2-Pack, Set of 2) 以及 (Oven Mitts, Baking Gloves, Kitchen Mittens)。\n"
            f"   - **结构打乱**：随机切换以下四种重心：\n"
            f"     * 重心A (属性优先): [图案/颜色] + [核心词] + [功能/数量]\n"
            f"     * 重心B (功能优先): [功能短语] + [核心词] + [数量/属性]\n"
            f"     * 重心C (核心优先): [核心词] + [数量] + [场景用语] + [属性]\n"
            f"     * 重心D (数量优先): [数量词变体] + [属性] + [核心词] + [功能]\n"
            f"5. **属性保护**：删除 '1pc'，如果本身有 '2pcs' 以上套装属性词，则保留下来，没有不要随便添加。必须保留颜色(Color)、材质(Material)或图案(Pattern)。\n"
            f"{mode_instruction}\n"
        )
    elif "allegro" in platform.lower() or "波兰" in platform:
        # 波兰 Allegro 逻辑：极致强调首位核心词，处理波兰语长单词
        platform_instruction = (
            f"你现在是【波兰 Allegro 官方 SEO 专家】。请严格遵守以下平台硬性规则：\n"
            f"1. **首位词原则**：**标题的第一个词必须是产品的核心名词**（如：Etui, Lampa, Uchwyt）。严禁以形容词、品牌名或促销词开头。\n"
            f"2. **字符约束**：总长度严格控制在 {char_limit} 字符内（含空格）。波兰语单词较长，请优先保留核心属性，删减无意义修饰词,，删除原标题的尺寸/尺码属性。\n"
            f"3. **纯净格式**：禁止出现任何特殊符号（如：- , / * +），仅允许使用空格。不要使用所有字母大写。\n"
            f"4. **地道语法**：确保名词变格（Deklinacja）符合波兰语习惯，适配描述统一使用 'do [Model]' 格式。\n"
            f"5. **属性保护**：删除 '1 szt. '，如果本身有 '2 szt.' 以上套装属性，则保留下来，如果没有不要随便添加。必须保留颜色(Color)、材质(Material)或图案(Pattern)。\n"
            f"{mode_instruction}\n"
        )
    else:
        # 美克多逻辑：强调极简、严禁促销词、严格遵守介词规则
        platform_instruction = (
            f"你现在是【美克多 Mercado Libre】官方上架专家。要求如下：\n"
            f"1. **极致极简**：严格控制在 {char_limit} 字符内，删除原标题的尺寸/尺码属性。\n"
            f"2. **类目规则**：‘手机/平板配件’类目手机前面必须加 'for '，其他类目严禁出现 'for'。\n"
            f"3. **符号硬指标**：**严禁使用任何逗号、分号或特殊符号**，仅允许空格。\n"
            f"4. **多样化**：同一批标题严禁句式雷同，随机切换重心（属性优先/功能优先/场景优先）。\n"
            f"   - **同义词旋转**：随机交替使用 (2pcs, 1 Pair, 2-Pack, Set of 2) 以及 (Oven Mitts, Baking Gloves, Kitchen Mittens)。\n"
            f"   - **结构打乱**：随机切换以下四种重心：\n"
            f"     * 重心A (属性优先): [图案/颜色] + [核心词] + [功能/数量]\n"
            f"     * 重心B (功能优先): [功能短语] + [核心词] + [数量/属性]\n"
            f"     * 重心C (核心优先): [核心词] + [数量] + [场景用语] + [属性]\n"
            f"     * 重心D (数量优先): [数量词变体] + [属性] + [核心词] + [功能]\n"
            f"5. **属性保护**：删除 '1pc'，如果本身有 '2pcs' 以上套装属性词，则保留下来，如果没有不要随便添加。必须保留颜色(Color)、材质(Material)或图案(Pattern)。\n"

        )
    common_rules = (
        f"6. **列组合约束**：{'必须完整保留 [附加关键词] 内容，不得删减。' if opt_mode == '列组合优化' else '精简非核心修饰词。'}"
    )

    prompt = (
        f"{platform_instruction}\n"
        f"{common_rules}\n"
        f"语言要求：{language}，句子要纯正语言，包括介词也要用相对应的语言\n"
        f"{neg_instruction}\n"  # <--- 禁词指令放在显眼位置
        f"格式要求：只返回 '#ID: 结果'，每行一条。\n"
        f"待处理数据：\n{input_payload}\n{retry_warning}"
    )
    for attempt in range(1, 4):
        try:
            current_key = next(key_pool)
            client = OpenAI(api_key=current_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "Professional SEO expert. Strictly follows char limits."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                timeout=120
            )
            output = response.choices[0].message.content
            matches = re.findall(r'#(\d+)[:：](.*)', output)
            batch_results = {}
            success_count = 0

            for m_id, m_content in matches:
                u_id = int(m_id)
                optimized_text = " ".join(m_content.strip().replace(',', ' ').split())
                status = "Optimized" if len(optimized_text) <= char_limit else "Retry_Needed"
                if status == "Optimized": success_count += 1
                batch_results[u_id] = (optimized_text, status)

            return batch_results, f"OK({success_count}/{len(id_titles_dict)})"
        except Exception as e:
            if attempt < 3: time.sleep(3); continue
            return {}, f"API_Error: {str(e)}"
    return {}, "Max_Retries_Exceeded"


def start_optimization_task(uploaded_files, platform, char_limit, language, api_keys, batch_size, sleep_time,
                            model_name, base_url, user_id,current_sid,use_deduplicate=True, deduplicate_limit=99, temperature=0.7,
                            existing_df=None, opt_mode="AI优化标题", selected_extra_cols=None, selected_sheet=None,negative_keywords=None):
    """
    任务分发函数：修复断点续传下的文件名丢失与结果合并问题
    """
    conn = sqlite3.connect(db_path, check_same_thread=False,timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    try:  # <--- 【必须添加 try 块】
        key_pool = itertools.cycle(api_keys)
        processed_results = []
        # --- 0. 权限与会话预检 ---
        cursor = conn.cursor()
        # 一次性查出：到期时间、SessionID、是否活跃 (is_active)
        cursor.execute("SELECT expiry_date, last_session_id, is_active FROM users WHERE user_id = ?", (user_id,))
        user_info = cursor.fetchone()

        if not user_info:
            yield "❌ 用户不存在，任务终止"
            return

        # 一次性解构三个字段
        expiry_date_str, last_sid, is_active = user_info

        # 1. 检查是否被禁用
        if is_active == 0:
            yield "🛑 账号已被管理员禁用或注销，任务终止。"
            return

        # 2. 检查到期时间
        if datetime.datetime.strptime(expiry_date_str, '%Y-%m-%d').date() < datetime.date.today():
            yield "❌ 账号已过期，请续费后使用"
            return

        # # 3. 检查 Session ID (防止多端登录)
        # if last_sid != current_sid:
        #     yield "🛑 检测到账号在别处登录，当前任务已安全停止。"
        #     return

        yield f"🚀 引擎启动 | 用户ID: {user_id} | 模式: {opt_mode}"

        # 如果有断点数据，优先处理断点
        if existing_df is not None:
            files_to_process = [("BUFFER_TASK", existing_df)]
        else:
            files_to_process = [(f.name, f) for f in uploaded_files] if uploaded_files else []

        for fname_raw, file_source in files_to_process:
            # --- 1. 数据载入与文件名恢复 ---
            if fname_raw == "BUFFER_TASK":
                df = file_source
                # 尝试从 st.session_state 恢复文件名，否则给个默认带后缀的名字
                fname = "Recovered_Task.xlsx"
                yield f"🔄 正在从断点恢复任务..."
            else:
                fname = fname_raw
                yield f"📂 正在读取: {fname}"
                try:
                    if fname.endswith(('.xlsx', '.xls')):
                        sheet_to_read = selected_sheet if selected_sheet else 0
                        content = pd.read_excel(file_source, sheet_name=sheet_to_read)
                        df = content[selected_sheet] if isinstance(content, dict) else content
                    else:
                        file_source.seek(0)
                        df = pd.read_csv(file_source, encoding='utf-8-sig')
                except Exception as e:
                    yield f"❌ 读取失败: {e}"
                    continue

            # --- 2. 标题列定位 ---
            target_col = next(
                (c for c in df.columns if any(k in str(c).lower() for k in ['标题', 'title', 'name', '商品名称', '名称'])),
                None)

            if not target_col:
                yield f"⚠️ 找不到标题列，跳过 {fname}"
                continue

            if 'AI_Status' not in df.columns:
                df['AI_Status'] = "Pending"

            # 内部函数：处理列组合输入
            def prepare_input(row):
                original_title = str(row[target_col]).strip()
                if opt_mode == "列组合优化" and selected_extra_cols:
                    # 过滤掉 nan 值并拼接
                    extra_info = " ".join(
                        [str(row[col]).strip() for col in selected_extra_cols if str(row[col]).lower() != 'nan'])
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

                    # 分组切片逻辑 (deduplicate_limit)
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
                    # 【防多端登录校验】
                    cursor.execute("SELECT last_session_id FROM users WHERE user_id = ?", (user_id,))
                    # if cursor.fetchone()[0] != current_sid:
                    #     yield "🛑 检测到账号在别处登录，当前任务已安全停止。"
                    #     return  # 进入 finally 关闭连接

                    current_batch_keys = unique_keys[i: i + batch_size]
                    batch_payload = {}

                    # 【数据库缓存预检】
                    for b_idx, k in enumerate(current_batch_keys):
                        raw_input = k.split("__grp")[0].split("__row")[0]
                        cursor.execute("""
                                            SELECT optimized_title FROM optimized_history 
                                            WHERE user_id = ? AND original_input = ? AND platform = ? AND char_limit = ?
                                        """, (user_id, raw_input, platform, char_limit))
                        cache = cursor.fetchone()

                        if cache:
                            opt_text = cache[0]
                            for row_idx in title_to_indices[k]:
                                df.at[row_idx, target_col] = opt_text
                                df.at[row_idx, 'AI_Status'] = "Optimized"
                        else:
                            batch_payload[b_idx] = raw_input

                    # 【调用 AI 引擎】
                    total_count = len(current_batch_keys)
                    cache_hit_count = total_count - len(batch_payload)

                    if cache_hit_count > 0 and len(batch_payload) > 0:
                        yield f"💾 缓存命中：已自动恢复 {cache_hit_count} 条记录，剩余 {len(batch_payload)} 条请求 AI..."
                    if batch_payload:
                        results, log_msg = ai_rewrite_engine(
                            id_titles_dict=batch_payload,  # 1. 这一批次的原始标题
                            char_limit=char_limit,  # 2. 字符限制 (从函数参数来)
                            platform=platform,  # 3. 平台 (从函数参数来)
                            language=language,  # 4. 语言 (从函数参数来)
                            key_pool=key_pool,  # 5. API密钥池
                            model_name=model_name,  # 6. 模型名称
                            base_url=base_url,  # 7. 接口地址
                            is_retry=(round_idx > 1),  # 8. 是否重试
                            temperature=temperature,  # 9. 随机度
                            opt_mode=opt_mode,  # 10. 模式
                            negative_keywords=negative_keywords  # 11. 违禁词
                        ) # 此处传入你的参数

                        # 回填并存入数据库
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
                                    (user_id, original_input, optimized_title, platform, char_limit, timestamp) 
                                    VALUES (?, ?, ?, ?, ?, ?)
                                """, (user_id, clean_text, opt_text, platform, char_limit, now_time))
                        conn.commit()
                    else:
                        log_msg = "⚡ 100% 缓存命中（零秒恢复）"

                    yield df
                    yield f"📝 {log_msg} | 进度: {min(i + batch_size, total_unique)}/{total_unique}"
                    if i + batch_size < total_unique and batch_payload:
                        time.sleep(sleep_time)

                # 单个文件处理完成
            final_stats = df['AI_Status'].value_counts()
            yield f"📊 {fname} 处理完成！成功: {final_stats.get('Optimized', 0)} 条。"
            processed_results.append((fname, df))

            # --- 6. 全部文件处理结束信号 (放在循环外) ---
        yield "FINISH_SIGNAL"
        yield processed_results

    except Exception as e:
        # 捕获运行中的任何崩溃
        yield f"❌ 任务运行出错: {str(e)}"

    finally:
        # --- 7. 无论如何，确保连接关闭 ---
        conn.close()