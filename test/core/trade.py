import pandas as pd
import time
import re
import itertools
import io
from openai import OpenAI

# 定义版本号
VERSION = "v2.1.0-Global-Unique-SEO"


def ai_rewrite_engine(id_titles_dict, char_limit, platform, language, key_pool, model_name, base_url, is_retry=False):
    """
    核心优化引擎：处理传入的字典，返回优化后的结果
    """
    if not id_titles_dict:
        return {}, "Empty"

    input_payload = "\n".join([f"#{k}: {v}" for k, v in id_titles_dict.items()])

    # 针对重试轮次的严厉提醒
    retry_warning = ""
    if is_retry:
        # 针对重试轮次的严厉提醒
        retry_warning = "⚠️ [重要] 之前的尝试依然超长，包含空格要在60字符以内，确保达标！" if is_retry else ""

    prompt = (

        f"你是{platform}专家。优化以下标题，语言：{language}：\n"

        f"{retry_warning}\n"

        f"1. **硬指标**：包含空格在内的最终结果绝对不能超过 {char_limit} 个字符。\n"

        f"2. **分类规则**：仅‘手机/平板配件(Case/Cover)’开头加'for '；汽车/家居等品类严禁加'for'。\n"

        f"3. **格式要求**：严禁使用逗号，严禁单词只写一半，必须是通顺短语。\n"

        f"4. **精简逻辑**：若超长，优先删除介词(With/From)、属性词(Polyester/Black)，保留2pc以上的数量属性，1pc数量词删除。\n"

        f"格式：'#ID: 结果'。\n"

        f"待处理：\n{input_payload}"

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
                temperature=0,
                timeout=60
            )
            output = response.choices[0].message.content

            # 解析结果
            matches = re.findall(r'#(\d+)[:：](.*)', output)
            batch_results = {}
            success_count = 0

            for m_id, m_content in matches:
                u_id = int(m_id)
                optimized_text = m_content.strip()

                # 长度检查
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
                            model_name, base_url):
    key_pool = itertools.cycle(api_keys)
    yield f"🚀 引擎启动 | {VERSION} | 模式: 全局去重分发"

    processed_results = []

    for file_obj in uploaded_files:
        yield f"📂 读取文件: {file_obj.name}"
        try:
            df = pd.read_excel(file_obj)
        except:
            file_obj.seek(0)
            df = pd.read_csv(file_obj, encoding='utf-8-sig')

        target_col = next((c for c in df.columns if any(k in str(c).lower() for k in ['标题', 'title', 'name'])), None)
        if not target_col:
            yield f"⚠️ 找不到标题列，跳过 {file_obj.name}"
            continue

        if 'AI_Status' not in df.columns:
            df['AI_Status'] = "Pending"

        # --- 递归轮次开始 ---
        for round_idx in range(1, 4):
            # 1. 提取所有非 Optimized 的行
            pending_df = df[df['AI_Status'] != 'Optimized'].copy()
            if pending_df.empty:
                break

            # 2. 全局去重映射：原始标题 -> [索引列表]
            title_to_indices = {}
            for idx, row in pending_df.iterrows():
                original_t = str(row[target_col])
                title_to_indices.setdefault(original_t, []).append(idx)

            unique_titles = list(title_to_indices.keys())
            total_unique = len(unique_titles)

            yield f"🔄 [第 {round_idx} 轮] 唯一标题: {total_unique} 条 (关联原始数据: {len(pending_df)} 行)"

            # 3. 按 batch_size 分批处理唯一标题
            for i in range(0, total_unique, batch_size):
                current_batch_titles = unique_titles[i: i + batch_size]
                # 构造 ID:Title 字典用于发送
                batch_payload = {idx: t for idx, t in enumerate(current_batch_titles)}

                results, log_msg = ai_rewrite_engine(
                    batch_payload, char_limit, platform, language, key_pool, model_name, base_url,
                    is_retry=(round_idx > 1)
                )

                # 4. 结果分发回原始 DataFrame
                for u_idx, (opt_text, status) in results.items():
                    original_t = current_batch_titles[u_id] if (u_id := u_idx) < len(current_batch_titles) else None
                    if original_t:
                        target_rows = title_to_indices[original_t]
                        for row_idx in target_rows:
                            df.at[row_idx, target_col] = opt_text
                            df.at[row_idx, 'AI_Status'] = status

                yield f"📝 [轮次{round_idx}] {log_msg} | 进度: {min(i + batch_size, total_unique)}/{total_unique}"

                if i + batch_size < total_unique:
                    time.sleep(sleep_time)

        # --- 最终保底：强制截断 ---
        final_fail = df[df['AI_Status'] != 'Optimized'].index
        if not final_fail.empty:
            yield f"⚠️ 强制截断剩余 {len(final_fail)} 条超长标题以确保上架..."
            df.loc[final_fail, target_col] = df.loc[final_fail, target_col].str[:char_limit]
            df.loc[final_fail, 'AI_Status'] = 'Optimized'

        final_stats = df['AI_Status'].value_counts()
        yield f"📊 完成！成功: {final_stats.get('Optimized', 0)} 条。"
        processed_results.append((file_obj.name, df))

    yield "FINISH_SIGNAL"
    yield processed_results