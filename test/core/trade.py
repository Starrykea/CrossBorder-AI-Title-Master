import pandas as pd
import time
import re
import itertools
import io
from openai import OpenAI


def ai_rewrite_engine(id_titles_dict, char_limit, platform, language, key_pool, model_name, base_url):
    """
    加固后的 AI 引擎：引入去重映射逻辑，保证相同输入必有相同输出
    """
    # --- 1. 内部去重逻辑 ---
    # 建立 反向映射 {原始标题: [ID1, ID2...]}
    reverse_map = {}
    for idx, title in id_titles_dict.items():
        reverse_map.setdefault(title, []).append(idx)

    # 提取唯一的标题进行处理
    unique_titles = list(reverse_map.keys())
    # 重新编号，发给 AI 的 Payload 只包含不重复的内容
    unique_payload_dict = {i: unique_titles[i] for i in range(len(unique_titles))}
    input_payload = "\n".join([f"#{k}: {v}" for k, v in unique_payload_dict.items()])

    prompt = (
        f"你是{platform}专家。优化以下标题，语言是{language}：\n"
        f"1. 要求重写优化标题，中间不要有逗号否则浪费字符。\n"
        f"2. 严格控制在 {char_limit} 字符内。格式：'#ID: 结果'。\n"
        f"3. 严禁出现不完整的词汇，严禁有侵权词汇\n"
        f"4. 必须保持一致性：对于内容相同的输入，必须给出完全相同的优化结果。\n"
        f"待处理：\n{input_payload}"
    )

    for attempt in range(1, 4):
        current_key = next(key_pool)
        client = OpenAI(api_key=current_key, base_url=base_url)

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system",
                     "content": "You are a professional e-commerce SEO expert. You output stable and consistent titles."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0  # 💡 关键：设置为 0 保证确定性输出
            )
            output = response.choices[0].message.content

            # --- 2. 结果解析与分发 ---
            unique_results = {}
            matches = re.findall(r'#(\d+)[:：](.*)', output)
            for m_id, m_content in matches:
                unique_results[int(m_id)] = m_content.strip()[:char_limit]

            # 将 AI 返回的唯一结果，根据 reverse_map 回填给所有原始 ID
            final_batch_results = {}
            for u_idx, optimized_text in unique_results.items():
                original_title = unique_payload_dict[u_idx]
                original_ids = reverse_map[original_title]
                for o_id in original_ids:
                    final_batch_results[o_id] = optimized_text

            if len(final_batch_results) > 0:
                return final_batch_results, f"✅ {model_name} 第 {attempt} 次尝试成功 (已处理重复内容)"

        except Exception as e:
            print(f"❌ 调试报错详情 (Attempt {attempt}): {str(e)}")
            if attempt < 3:
                time.sleep(5)
            continue

    fallback_results = {idx: str(original)[:char_limit].strip() for idx, original in id_titles_dict.items()}
    return fallback_results, "⚠️ AI 调用失败，已启动保底截断逻辑"


def start_optimization_task(uploaded_files, platform, char_limit, language, api_keys, batch_size, sleep_time,
                            model_name, base_url):
    """
    Streamlit 任务启动器
    """
    key_pool = itertools.cycle(api_keys)
    yield f"🚀 系统启动 | 引擎: {model_name} | 确定性模式: ON (Temp=0)"

    processed_results = []

    for file_obj in uploaded_files:
        yield f"-------------------------------------------"
        yield f"📂 正在处理: {file_obj.name}"

        df = pd.read_excel(file_obj)
        # 自动识别列名
        target_col = next(
            (c for c in df.columns if any(k in str(c).lower() for k in ['标题', 'title', 'name', '商品名称'])), None)

        if not target_col:
            yield f"⚠️ 警告: 找不到标题列，跳过文件。"
            continue

        if 'Original_Backup' not in df.columns:
            df['Original_Backup'] = df[target_col]

        if 'AI_Status' not in df.columns:
            df['AI_Status'] = None

        pending_indices = df[df['AI_Status'].isna()].index.tolist()
        total = len(pending_indices)

        if total == 0:
            yield f"✅ 无需重复优化。"
            processed_results.append((file_obj.name, df))
            continue

        yield f"📊 待优化: {total} 条"

        for i in range(0, total, batch_size):
            batch_idx = pending_indices[i: i + batch_size]
            batch_dict = {idx: df.at[idx, target_col] for idx in batch_idx}

            results, status_msg = ai_rewrite_engine(
                batch_dict, char_limit, platform, language, key_pool, model_name, base_url
            )
            yield f"📝 [进度 {i + len(batch_idx)}/{total}] {status_msg}"

            for idx, content in results.items():
                df.at[idx, target_col] = content
                df.at[idx, 'AI_Status'] = "Optimized"

            if i + batch_size < total:
                time.sleep(sleep_time)

        processed_results.append((file_obj.name, df))

    yield "FINISH_SIGNAL"
    yield processed_results