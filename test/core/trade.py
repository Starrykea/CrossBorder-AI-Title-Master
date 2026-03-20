import pandas as pd
import time
import re
import itertools
from openai import OpenAI

# 定义版本号
VERSION = "v2.0.0-Recursive-SEO"


def ai_rewrite_engine(id_titles_dict, char_limit, platform, language, key_pool, model_name, base_url, is_retry=False):
    """
    v2.0.0 核心引擎：增加递归质检与逻辑重试
    """
    # --- 1. 内部去重逻辑 ---
    reverse_map = {}
    for idx, title in id_titles_dict.items():
        reverse_map.setdefault(title, []).append(idx)

    unique_titles = list(reverse_map.keys())
    unique_payload_dict = {i: unique_titles[i] for i in range(len(unique_titles))}
    input_payload = "\n".join([f"#{k}: {v}" for k, v in unique_payload_dict.items()])

    # 针对重试轮次的严厉提醒
    retry_warning = "⚠️ [重要] 之前的尝试依然超长，请这次务必舍弃更多次要描述，确保达标！" if is_retry else ""

    prompt = (
        f"你是{platform}专家。优化以下标题，语言：{language}：\n"
        f"{retry_warning}\n"
        f"1. **硬指标**：包含空格在内的最终结果绝对不能超过 {char_limit} 个字符。\n"
        f"2. **分类规则**：仅‘手机/平板配件(Case/Cover)’开头加'for '；汽车/家居等品类严禁加'for'。\n"
        f"3. **格式要求**：严禁使用逗号，严禁单词只写一半，必须是通顺短语。\n"
        f"4. **精简逻辑**：若超长，优先删除介词(With/From)、属性词(Polyester/Black)或描述性词汇。\n"
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
                    {"role": "system",
                     "content": "You are a professional SEO expert who strictly follows character limits."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            output = response.choices[0].message.content

            # --- 2. 结果解析与字符数质检 ---
            unique_results = {}
            matches = re.findall(r'#(\d+)[:：](.*)', output)

            final_batch_results = {}
            success_in_batch = 0

            for m_id, m_content in matches:
                u_id = int(m_id)
                optimized_text = m_content.strip()

                # 🛠️ 质检逻辑：计算字符长度
                current_len = len(optimized_text)

                if current_len <= char_limit:
                    status = "Optimized"
                    success_in_batch += 1
                else:
                    status = "Retry_Needed"  # 长度超标，标记为重试

                if u_id in unique_payload_dict:
                    original_ids = reverse_map[unique_payload_dict[u_id]]
                    for o_id in original_ids:
                        final_batch_results[o_id] = (optimized_text, status)

            if len(final_batch_results) > 0:
                return final_batch_results, f"OK({success_in_batch}/{len(matches)})"

        except Exception:
            if attempt < 3: time.sleep(5)
            continue

    fallback = {idx: (str(title), "Fallback_Error") for idx, title in id_titles_dict.items()}
    return fallback, "API_Error"


def start_optimization_task(uploaded_files, platform, char_limit, language, api_keys, batch_size, sleep_time,
                            model_name, base_url):
    key_pool = itertools.cycle(api_keys)
    yield f"🚀 系统启动 | 版本: {VERSION} | 多轮质检模式"

    processed_results = []

    for file_obj in uploaded_files:
        yield f"📂 正在读取: {file_obj.name}"
        try:
            df = pd.read_excel(file_obj)
        except:
            file_obj.seek(0)
            df = pd.read_csv(file_obj, encoding='utf-8-sig')

        target_col = next((c for c in df.columns if
                           any(k in str(c).lower() for k in ['标题', 'title', 'name', '商品名称', '商品标题'])), None)
        if not target_col:
            yield f"⚠️ 找不到标题列，跳过。"
            continue

        if 'AI_Status' not in df.columns:
            df['AI_Status'] = None

        # 记录处理版本
        df['Engine_Version'] = VERSION

        # --- 多轮递归循环 ---
        for round_idx in range(1, 4):  # 最多迭代 3 轮
            pending_mask = (df['AI_Status'] != 'Optimized')
            pending_indices = df[pending_mask].index.tolist()

            if not pending_indices:
                break

            total_pending = len(pending_indices)
            yield f"🔄 [第 {round_idx} 轮质检] 剩余待处理: {total_pending} 条"

            for i in range(0, total_pending, batch_size):
                batch_idx = pending_indices[i: i + batch_size]
                batch_dict = {idx: df.at[idx, target_col] for idx in batch_idx}

                results, log_msg = ai_rewrite_engine(
                    batch_dict, char_limit, platform, language, key_pool, model_name, base_url,
                    is_retry=(round_idx > 1)
                )

                for idx, (content, status) in results.items():
                    df.at[idx, target_col] = content
                    df.at[idx, 'AI_Status'] = status

                yield f"📝 [轮次{round_idx}] {log_msg}"
                if i + batch_size < total_pending:
                    time.sleep(sleep_time)

        final_stats = df['AI_Status'].value_counts()
        yield f"📊 文件完成：成功 {final_stats.get('Optimized', 0)} 条，超长待修 {final_stats.get('Retry_Needed', 0)} 条。"
        processed_results.append((file_obj.name, df))

    yield "FINISH_SIGNAL"
    yield processed_results