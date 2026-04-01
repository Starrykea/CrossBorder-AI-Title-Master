import pandas as pd
import time
import re
import itertools
import io
from openai import OpenAI

# 定义版本号
VERSION = "v2.3.1-Checkpoint-Ready"  # 增加了断点存盘支持


def ai_rewrite_engine(id_titles_dict, char_limit, platform, language, key_pool, model_name, base_url, is_retry=False,
                      temperature=0):
    """
    核心优化引擎：保持不变
    """
    if not id_titles_dict:
        return {}, "Empty"

    input_payload = "\n".join([f"#{k}: {v}" for k, v in id_titles_dict.items()])

    retry_warning = ""
    if is_retry:
        retry_warning = f"⚠️ [重要] 之前的尝试依然超长，包含空格必须在 {char_limit} 字符以内，确保达标！"

    prompt = (
        f"你是{platform}专家。优化以下标题，语言：{language}。要求如下：\n"
        f"1. **硬指标**：包含空格在内必须 < {char_limit} 字符。**严禁使用任何逗号或分号**，省略1pc，保留2pc以上套装属性。\n"
        f"2. **保留区分度**：必须保留颜色(Color)、材质(Material)、或图案(Pattern)等关键属性。\n"
        f"3. **极限多样化要求**：\n"
        f"   - **禁止雷同**：这一组标题严禁使用相同的开头和句式结构。\n"
        f"   - **同义词旋转**：随机交替使用 (2pcs, 1 Pair, 2-Pack, Set of 2) 以及 (Oven Mitts, Baking Gloves, Kitchen Mittens)。\n"
        f"   - **结构打乱**：随机切换以下四种重心：\n"
        f"     * 重心A (属性优先): [图案/颜色] + [核心词] + [功能/数量]\n"
        f"     * 重心B (功能优先): [功能短语] + [核心词] + [数量/属性]\n"
        f"     * 重心C (场景优先): [核心词] + [数量] + [场景用语] + [属性]\n"
        f"     * 重心D (数量优先): [数量词变体] + [属性] + [核心词] + [功能]\n"
        f"4. **精简逻辑**：若超长，删除多余修饰词(High Quality, Durable)，但严禁删除颜色词。\n"
        f"5. **分类规则**：仅‘手机/平板配件’开头加'for '，其他严禁。\n"
        f"格式：'#ID: 结果'。\n"
        f"待处理：\n{input_payload}\n{retry_warning}"
    )

    for attempt in range(1, 4):
        try:
            current_key = next(key_pool)
            client = OpenAI(api_key=current_key, base_url=base_url)

            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "Professional SEO expert. Strictly follows char limits. No commas."},
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
                optimized_text = m_content.strip().replace(',', ' ')
                optimized_text = " ".join(optimized_text.split())

                if len(optimized_text) <= char_limit:
                    status = "Optimized"
                    success_count += 1
                else:
                    status = "Retry_Needed"

                batch_results[u_id] = (optimized_text, status)

            return batch_results, f"OK({success_count}/{len(id_titles_dict)})"

        except Exception as e:
            if attempt < 3:
                time.sleep(5)
                continue
            return {}, f"API_Error: {str(e)[:50]}"

    return {}, "Max_Retries_Exceeded"


def start_optimization_task(uploaded_files, platform, char_limit, language, api_keys, batch_size, sleep_time,
                            model_name, base_url, use_deduplicate=True, deduplicate_limit=99, temperature=0.7,
                            existing_df=None):  # 新增 existing_df 参数支持断点续传
    """
    任务分发函数：支持实时进度保存
    """
    key_pool = itertools.cycle(api_keys)
    processed_results = []
    mode_label = f"分组去重(上限:{deduplicate_limit})" if use_deduplicate else "逐行独立"
    yield f"🚀 引擎启动 | {VERSION} | 模式: {mode_label}"

    # 如果是从 session_state 恢复的，uploaded_files 可能是空的，我们直接用 existing_df
    files_to_process = uploaded_files if uploaded_files else [None]

    for file_obj in files_to_process:
        if existing_df is not None:
            df = existing_df
            fname = "上次未完成的任务"
        else:
            yield f"📂 读取文件: {file_obj.name}"
            fname = file_obj.name
            try:
                df = pd.read_excel(file_obj)
            except:
                file_obj.seek(0)
                df = pd.read_csv(file_obj, encoding='utf-8-sig')

        target_col = next((c for c in df.columns if any(k in str(c).lower() for k in ['标题', 'title', 'name'])), None)
        if not target_col:
            yield f"⚠️ 找不到标题列，跳过 {fname}"
            continue

        df[target_col] = df[target_col].astype(str).replace('nan', '')

        # --- 修改点：如果列已存在，不覆盖原有状态 (实现断点续传的关键) ---
        if 'AI_Status' not in df.columns:
            df['AI_Status'] = "Pending"

        for round_idx in range(1, 4):
            # 只选出还没成功的行
            pending_mask = (df['AI_Status'] != 'Optimized')
            pending_df = df[pending_mask].copy()

            if pending_df.empty:
                yield f"✅ 所有标题已达标。"
                break

            title_to_indices = {}
            if use_deduplicate:
                raw_groups = {}
                for idx, row in pending_df.iterrows():
                    original_t = str(row[target_col])
                    raw_groups.setdefault(original_t, []).append(idx)

                for original_t, all_indices in raw_groups.items():
                    for i in range(0, len(all_indices), deduplicate_limit):
                        chunk = all_indices[i: i + deduplicate_limit]
                        chunk_id = i // deduplicate_limit
                        unique_key = f"{original_t}__chunk{chunk_id}"
                        title_to_indices[unique_key] = chunk
            else:
                for idx, row in pending_df.iterrows():
                    unique_key = f"{row[target_col]}__row{idx}"
                    title_to_indices[unique_key] = [idx]

            unique_keys = list(title_to_indices.keys())
            total_unique = len(unique_keys)

            yield f"🔄 [第 {round_idx} 轮] 待处理: {total_unique} 条"

            for i in range(0, total_unique, batch_size):
                current_batch_keys = unique_keys[i: i + batch_size]
                batch_payload = {}
                id_to_key = {}
                for b_idx, key in enumerate(current_batch_keys):
                    original_title = re.split(r"__(chunk|row)", key)[0]
                    batch_payload[b_idx] = original_title
                    id_to_key[b_idx] = key

                current_temp = temperature if (not use_deduplicate or deduplicate_limit < 500) else 0

                results, log_msg = ai_rewrite_engine(
                    batch_payload, char_limit, platform, language, key_pool, model_name, base_url,
                    is_retry=(round_idx > 1),
                    temperature=current_temp
                )

                for batch_id, (opt_text, status) in results.items():
                    final_status = "Optimized" if len(opt_text) <= char_limit else "Length_Exceeded"
                    target_key = id_to_key.get(batch_id)

                    if target_key:
                        target_rows = title_to_indices[target_key]
                        for row_idx in target_rows:
                            df.at[row_idx, target_col] = opt_text
                            df.at[row_idx, 'AI_Status'] = final_status

                # --- 修改点：每个 Batch 处理完后，直接 yield 当前的 DF ---
                # 这允许 UI 捕获并更新 st.session_state
                yield df

                yield f"📝 [轮次{round_idx}] {log_msg} | 进度: {min(i + batch_size, total_unique)}/{total_unique}"

                if i + batch_size < total_unique:
                    time.sleep(sleep_time)

            # 统计并返回
            final_stats = df['AI_Status'].value_counts()
            yield f"📊 {fname} 处理完成！成功: {final_stats.get('Optimized', 0)} 条。"
            fname = file_obj.name if file_obj else "Recovered_Task.xlsx"
            processed_results.append((fname, df))
            # 处理完一个文件后重置 existing_df 防止干扰下一个文件
            existing_df = None
        yield "FINISH_SIGNAL"
        yield processed_results  # 💡 最后一次 yield，直接把列表丢出去