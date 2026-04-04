import pandas as pd
import time
import re
import itertools
import io
from openai import OpenAI

# 定义版本号
VERSION = "v2.4.1-Deduplicate-Fixed"


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
        neg_instruction = f"\n❌ **绝对禁止出现的词汇**：{negative_keywords} (严禁在任何情况下使用这些词或其近义词)"
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
            f"1. **SEO最大化**：乐天流量依赖关键词，请在 {char_limit} 字符内尽量填满核心词及相关长尾词。\n"
            f"2. **符号限制**：允许使用空格或分隔符 '-'。\n"
            f"3. **类目规则**：‘手机/平板配件’类目手机前面必须加 'pour '，其他类目严禁出现 'pour'。\n"
            f"{mode_instruction}\n"
        )
    else:
        # 美克多逻辑：强调极简、严禁促销词、严格遵守介词规则
        platform_instruction = (
            f"你现在是【美克多 Mercado Libre】官方上架专家。要求如下：\n"
            f"1. **极致极简**：严格控制在 {char_limit} 字符内。\n"
            f"2. **类目规则**：‘手机/平板配件’类目手机前面必须加 'for '，其他类目严禁出现 'for'。\n"
            f"3. **符号硬指标**：**严禁使用任何逗号、分号或特殊符号**，仅允许空格。\n"
        )
    common_rules = (
        f"4. **属性保护**：删除 '1pc'，保留 '2pcs' 以上套装属性。必须保留颜色(Color)、材质(Material)或图案(Pattern)。\n"
        f"5. **多样化**：同一批标题严禁句式雷同，随机切换重心（属性优先/功能优先/场景优先）。\n"
        f"   - **同义词旋转**：随机交替使用 (2pcs, 1 Pair, 2-Pack, Set of 2) 以及 (Oven Mitts, Baking Gloves, Kitchen Mittens)。\n"
        f"   - **结构打乱**：随机切换以下四种重心：\n"
        f"     * 重心A (属性优先): [图案/颜色] + [核心词] + [功能/数量]\n"
        f"     * 重心B (功能优先): [功能短语] + [核心词] + [数量/属性]\n"
        f"     * 重心C (核心优先): [核心词] + [数量] + [场景用语] + [属性]\n"
        f"     * 重心D (数量优先): [数量词变体] + [属性] + [核心词] + [功能]\n"
        f"7. **列组合约束**：{'必须完整保留 [附加关键词] 内容，不得删减。' if opt_mode == '列组合优化' else '精简非核心修饰词。'}"
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
                timeout=60
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
            return {}, f"API_Error: {str(e)[:50]}"
    return {}, "Max_Retries_Exceeded"


def start_optimization_task(uploaded_files, platform, char_limit, language, api_keys, batch_size, sleep_time,
                            model_name, base_url, use_deduplicate=True, deduplicate_limit=99, temperature=0.7,
                            existing_df=None, opt_mode="AI优化标题", selected_extra_cols=None, selected_sheet=None):
    """
    任务分发函数：修复断点续传下的文件名丢失与结果合并问题
    """
    key_pool = itertools.cycle(api_keys)
    processed_results = []
    yield f"🚀 引擎启动 | 模式: {opt_mode}"

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
                current_batch_keys = unique_keys[i: i + batch_size]
                # 提取 AI 实际需要的文本内容 (剥离后缀)
                batch_payload = {b_idx: k.split("__grp")[0].split("__row")[0] for b_idx, k in
                                 enumerate(current_batch_keys)}

                results, log_msg = ai_rewrite_engine(
                    batch_payload, char_limit, platform, language, key_pool, model_name, base_url,
                    is_retry=(round_idx > 1), temperature=temperature, opt_mode=opt_mode
                )

                # 回填结果
                for batch_id, (opt_text, status) in results.items():
                    target_key = current_batch_keys[batch_id]
                    target_rows = title_to_indices[target_key]
                    for row_idx in target_rows:
                        df.at[row_idx, target_col] = opt_text
                        df.at[row_idx, 'AI_Status'] = status

                # 每一组 batch 完成后 yield 一次 df，用于 UI 实时存盘
                yield df
                yield f"📝 {log_msg} | 进度: {min(i + batch_size, total_unique)}/{total_unique}"

                if i + batch_size < total_unique:
                    time.sleep(sleep_time)

        # --- 5. 单个文件处理完成 ---
        final_stats = df['AI_Status'].value_counts()
        yield f"📊 {fname} 处理完成！成功: {final_stats.get('Optimized', 0)} 条。"
        processed_results.append((fname, df))

    # --- 6. 全部结束信号 ---
    yield "FINISH_SIGNAL"
    yield processed_results