import pandas as pd
import time
import re
import itertools
import io  # 用于处理内存中的文件流
from google import genai


# ai_rewrite_engine 保持不变，它只负责逻辑，不涉及路径
def ai_rewrite_engine(id_titles_dict, char_limit, platform, language, key_pool):
    input_payload = "\n".join([f"#{k}: {v}" for k, v in id_titles_dict.items()])
    prompt = (
        f"你是{platform}专家。优化以下标题为{language}：\n"
        f"1. 严格控制在 {char_limit} 字符内。格式：'#ID: 结果'。\n"
        f"2. 结构：品牌 + 核心产品名 + 卖点 + 型号 + 颜色。\n"
        f"3. 规则：仅删除开头的 'For'/'Brand New'/'1pcs'；保留中间的 'for'。如果是手机壳(Phone Case)，则必须保留开头的 For。\n"
        f"4. 权重：核心词置于前 30 字符。\n"
        f"待处理：\n{input_payload}"
    )

    for attempt in range(1, 4):
        current_key = next(key_pool)
        client = genai.Client(api_key=current_key)
        try:
            response = client.models.generate_content(
                model="models/gemini-2.0-flash",
                contents=prompt
            )
            output = response.text
            batch_results = {}
            matches = re.findall(r'#(\d+)[:：](.*)', output)
            for m_id, m_content in matches:
                batch_results[int(m_id)] = m_content.strip()[:char_limit]
            if len(batch_results) > 0:
                return batch_results, f"✅ 第 {attempt} 次尝试成功"
        except Exception as e:
            print(f"❌ 调试报错详情 (Attempt {attempt}): {str(e)}")
            if attempt < 3: time.sleep(5)
            continue

    fallback_results = {idx: str(original)[:char_limit].strip() for idx, original in id_titles_dict.items()}
    return fallback_results, "⚠️ AI 调用失败，已启动保底截断逻辑"


# --- 重点修改：start_optimization_task 现在接收文件对象列表 ---
def start_optimization_task(uploaded_files, platform, char_limit, language, api_keys, batch_size, sleep_time):
    """
    uploaded_files: Streamlit 传来的文件对象列表
    """
    key_pool = itertools.cycle(api_keys)
    yield f"🚀 云端系统启动 | 目标平台: {platform} | 字符限制: {char_limit}"

    # 存储处理后的结果，供下载使用
    processed_results = []

    for file_obj in uploaded_files:
        yield f"-------------------------------------------"
        yield f"📂 正在处理上传文件: {file_obj.name}"

        # 💡 直接从内存读取文件对象
        df = pd.read_excel(file_obj)

        target_col = next((c for c in df.columns if any(k in str(c) for k in ['标题', 'Title', 'Name', '商品名称'])),
                          None)
        if not target_col:
            yield f"⚠️ 警告: 文件 {file_obj.name} 找不到标题列，已跳过。"
            continue

        if 'Original_Backup' not in df.columns:
            df['Original_Backup'] = df[target_col]
            yield f"🛡️ 已创建原始标题备份"

        if 'AI_Status' not in df.columns:
            df['AI_Status'] = None

        pending_indices = df[df['AI_Status'].isna()].index.tolist()
        total = len(pending_indices)

        if total == 0:
            yield f"✅ 文件 {file_obj.name} 无需重复优化。"
            processed_results.append((file_obj.name, df))
            continue

        yield f"📊 待优化条数: {total} 条"

        for i in range(0, total, batch_size):
            current_key = next(key_pool)
            masked_key = f"{current_key[:6]}****{current_key[-4:]}"
            yield f"🔄 [动作] 优化进度: {i + 1}/{total} (Key: {masked_key})"

            batch_idx = pending_indices[i: i + batch_size]
            batch_dict = {idx: df.at[idx, target_col] for idx in batch_idx}

            results, status_msg = ai_rewrite_engine(batch_dict, char_limit, platform, language, key_pool)
            yield f"📝 [反馈] {status_msg}"

            for idx, content in results.items():
                df.at[idx, target_col] = content
                df.at[idx, 'AI_Status'] = "Optimized"

            if i + batch_size < total:
                yield f"⏳ 休眠 {sleep_time} 秒..."
                time.sleep(sleep_time)

        # 💡 处理完后，将结果存入列表
        processed_results.append((file_obj.name, df))
        yield f"✅ {file_obj.name} 处理完毕！"

    # 💡 最终通过 yield 传出一个特殊标记和处理好的数据
    yield "FINISH_SIGNAL"
    yield processed_results