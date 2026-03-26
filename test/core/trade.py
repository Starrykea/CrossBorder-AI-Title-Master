import pandas as pd
import time
import re
import itertools
import io
from openai import OpenAI

# 定义版本号
VERSION = "v2.2.0-Multi-Mode-SEO"


def ai_rewrite_engine(id_titles_dict, char_limit, platform, language, key_pool, model_name, base_url, is_retry=False,
                      temperature=0):
    """
    核心优化引擎：处理传入的字典，返回优化后的结果
    """
    if not id_titles_dict:
        return {}, "Empty"

    # 将待处理数据格式化为 #ID: Title 形式
    input_payload = "\n".join([f"#{k}: {v}" for k, v in id_titles_dict.items()])

    # 针对重试轮次的严厉提醒
    retry_warning = ""
    if is_retry:
        retry_warning = f"⚠️ [重要] 之前的尝试依然超长，包含空格必须在 {char_limit} 字符以内，确保达标！"

    # 构造 Prompt
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
                temperature=temperature,
                timeout=60
            )
            output = response.choices[0].message.content

            # 解析返回结果
            matches = re.findall(r'#(\d+)[:：](.*)', output)
            batch_results = {}
            success_count = 0

            for m_id, m_content in matches:
                u_id = int(m_id)
                optimized_text = m_content.strip()

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
                            model_name, base_url, use_deduplicate=True, temperature=0.7):
    """
    任务分发函数
    """
    key_pool = itertools.cycle(api_keys)
    mode_label = "全局去重" if use_deduplicate else "逐行独立"
    yield f"🚀 引擎启动 | {VERSION} | 模式: {mode_label}"

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

        for round_idx in range(1, 4):
            pending_mask = df['AI_Status'] != 'Optimized'
            pending_df = df[pending_mask].copy()

            if pending_df.empty:
                yield f"✅ 所有标题已达标，提前结束优化。"
                break

            # 1. 任务映射逻辑
            title_to_indices = {}
            if use_deduplicate:
                for idx, row in pending_df.iterrows():
                    original_t = str(row[target_col])
                    title_to_indices.setdefault(original_t, []).append(idx)
            else:
                for idx, row in pending_df.iterrows():
                    # 关键：加上行号后缀确保每行唯一，不被合并
                    unique_key = f"{row[target_col]}__row{idx}"
                    title_to_indices[unique_key] = [idx]

            unique_keys = list(title_to_indices.keys())
            total_unique = len(unique_keys)

            yield f"🔄 [第 {round_idx} 轮] 待处理任务: {total_unique} 条"

            # 2. 按批次处理
            for i in range(0, total_unique, batch_size):
                current_batch_keys = unique_keys[i: i + batch_size]

                batch_payload = {}
                id_to_key = {}
                for idx, key in enumerate(current_batch_keys):
                    # 还原原始标题用于发送给AI
                    original_title = key.split("__row")[0] if "__row" in key else key
                    batch_payload[idx] = original_title
                    id_to_key[idx] = key

                    # 调用 AI 引擎
                # 注意：如果开启去重，强制温控为0确保一致性；如果不去重，使用UI传入的温度
                current_temp = 0 if use_deduplicate else temperature

                results, log_msg = ai_rewrite_engine(
                    batch_payload, char_limit, platform, language, key_pool, model_name, base_url,
                    is_retry=(round_idx > 1),
                    temperature=current_temp
                )

                # 3. 结果分发：使用映射精确写回对应行
                for batch_id, (opt_text, status) in results.items():
                    final_status = "Optimized" if len(opt_text) <= char_limit else "Length_Exceeded"
                    target_key = id_to_key.get(batch_id)

                    if target_key:
                        target_rows = title_to_indices[target_key]
                        for row_idx in target_rows:
                            df.at[row_idx, target_col] = opt_text
                            df.at[row_idx, 'AI_Status'] = final_status

                yield f"📝 [轮次{round_idx}] {log_msg} | 进度: {min(i + batch_size, total_unique)}/{total_unique}"

                if i + batch_size < total_unique:
                    time.sleep(sleep_time)

        final_stats = df['AI_Status'].value_counts()
        success = final_stats.get('Optimized', 0)
        failed = final_stats.get('Length_Exceeded', 0)

        if failed > 0:
            yield f"⚠️ 注意：经过3轮优化，仍有 {failed} 条标题超长。"

        yield f"📊 文件 {file_obj.name} 处理完成！成功: {success}，失败: {failed}。"
        processed_results.append((file_obj.name, df))

    yield "FINISH_SIGNAL"
    yield processed_results