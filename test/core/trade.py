import pandas as pd
import time
import re
import itertools
from openai import OpenAI


def ai_rewrite_engine(id_titles_dict, char_limit, platform, language, key_pool, model_name, base_url):
    """
    修改后的引擎：增加状态标识返回
    """
    # --- 1. 内部去重逻辑 ---
    reverse_map = {}
    for idx, title in id_titles_dict.items():
        reverse_map.setdefault(title, []).append(idx)

    unique_titles = list(reverse_map.keys())
    unique_payload_dict = {i: unique_titles[i] for i in range(len(unique_titles))}
    input_payload = "\n".join([f"#{k}: {v}" for k, v in unique_payload_dict.items()])

    prompt = (
        f"你是{platform}专家。优化以下标题，语言是{language}：\n"
        f"1. 要求重写优化标题，中间不要有逗号否则浪费字符。\n"
        f"2. 严格控制在 {char_limit} 字符内。格式：'#ID: 结果'。\n"
        f"3. 严禁出现不完整的词汇，严禁有侵权词汇\n"
        f"4. 手机、平板配件前面必须加for，防止侵权\n"
        f"待处理：\n{input_payload}"
    )

    for attempt in range(1, 4):
        try:
            current_key = next(key_pool)
            client = OpenAI(api_key=current_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a professional e-commerce SEO expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            output = response.choices[0].message.content

            # --- 2. 结果解析 ---
            unique_results = {}
            matches = re.findall(r'#(\d+)[:：](.*)', output)
            for m_id, m_content in matches:
                unique_results[int(m_id)] = m_content.strip()[:char_limit]

            # 检查解析数量是否匹配，确保AI没有漏掉数据
            if len(unique_results) > 0:
                final_batch_results = {}
                for u_idx, optimized_text in unique_results.items():
                    if u_idx in unique_payload_dict:
                        original_ids = reverse_map[unique_payload_dict[u_idx]]
                        for o_id in original_ids:
                            final_batch_results[o_id] = optimized_text

                # 成功返回：结果，状态码，日志
                return final_batch_results, "Optimized", f"✅ {model_name} 处理成功"

        except Exception as e:
            if attempt < 3:
                time.sleep(5)
            continue

    # --- 💡 核心改动：触发保底逻辑时的返回 ---
    fallback_results = {idx: str(original)[:char_limit].strip() for idx, original in id_titles_dict.items()}
    return fallback_results, "Fallback_Truncated", "⚠️ AI调用失败，已执行保底截断"


def start_optimization_task(uploaded_files, platform, char_limit, language, api_keys, batch_size, sleep_time,
                            model_name, base_url):
    key_pool = itertools.cycle(api_keys)
    yield f"🚀 系统启动 | 引擎: {model_name}"

    processed_results = []

    for file_obj in uploaded_files:
        yield f"📂 正在处理: {file_obj.name}"
        df = pd.read_excel(file_obj)

        target_col = next(
            (c for c in df.columns if any(k in str(c).lower() for k in ['标题', 'title', 'name', '商品名称','商品标题'])), None)
        if not target_col:
            yield f"⚠️ 警告: 找不到标题列，跳过。"
            continue

        if 'AI_Status' not in df.columns:
            df['AI_Status'] = None

        pending_indices = df[df['AI_Status'].isna()].index.tolist()
        total = len(pending_indices)

        if total == 0:
            yield f"✅ 无需重复优化。"
            processed_results.append((file_obj.name, df))
            continue

        for i in range(0, total, batch_size):
            batch_idx = pending_indices[i: i + batch_size]
            batch_dict = {idx: df.at[idx, target_col] for idx in batch_idx}

            # 接收三个返回值
            results, status_code, log_msg = ai_rewrite_engine(
                batch_dict, char_limit, platform, language, key_pool, model_name, base_url
            )
            yield f"📝 [进度 {i + len(batch_idx)}/{total}] {log_msg}"

            # 将内容和对应的状态（Optimized 或 Fallback_Truncated）写入 Excel
            for idx, content in results.items():
                df.at[idx, target_col] = content
                df.at[idx, 'AI_Status'] = status_code

            if i + batch_size < total:
                time.sleep(sleep_time)

        # --- 💡 核心新增：统计功能 ---
        stats = df['AI_Status'].value_counts()
        fallback_count = stats.get('Fallback_Truncated', 0)
        optimized_count = stats.get('Optimized', 0)
        yield f"📊 文件统计：正常优化 {optimized_count} 条，保底截断 {fallback_count} 条。"

        processed_results.append((file_obj.name, df))

    yield "FINISH_SIGNAL"
    yield processed_results