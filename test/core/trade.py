import pandas as pd
import time
import re
import itertools
import io
from openai import OpenAI  # 💡 切换为通用 OpenAI 协议库


def ai_rewrite_engine(id_titles_dict, char_limit, platform, language, key_pool, model_name, base_url):
    """
    通用 AI 引擎：支持多模型、多 Key 轮询及中转地址
    """
    input_payload = "\n".join([f"#{k}: {v}" for k, v in id_titles_dict.items()])

    prompt = (
        f"你是{platform}专家。优化以下标题，语言是{language}：\n"
        f"1. 要求重写优化标题。\n"
        f"1. 严格控制在 {char_limit} 字符内。格式：'#ID: 结果'。\n"
        f"2. 严禁出现不完整的词汇\n"
        f"待处理：\n{input_payload}"
    )

    for attempt in range(1, 4):
        current_key = next(key_pool)

        # 💡 初始化通用客户端
        client = OpenAI(api_key=current_key, base_url=base_url)

        try:
            # 💡 使用 Chat Completion 接口（全网 AI 通用格式）
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a professional e-commerce SEO expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            output = response.choices[0].message.content

            batch_results = {}
            # 兼容中文和英文冒号
            matches = re.findall(r'#(\d+)[:：](.*)', output)

            for m_id, m_content in matches:
                batch_results[int(m_id)] = m_content.strip()[:char_limit]

            if len(batch_results) > 0:
                return batch_results, f"✅ {model_name} 第 {attempt} 次尝试成功"

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
    uploaded_files: Streamlit 传来的文件对象列表
    model_name: UI 传来的模型名称 (如 gemini-2.0-flash 或 deepseek-chat)
    base_url: UI 传来的 API 地址
    """
    key_pool = itertools.cycle(api_keys)
    yield f"🚀 系统启动 | 引擎: {model_name} | 平台: {platform} | 字符限制: {char_limit}"

    processed_results = []

    for file_obj in uploaded_files:
        yield f"-------------------------------------------"
        yield f"📂 正在处理上传文件: {file_obj.name}"

        # 直接从内存读取
        df = pd.read_excel(file_obj)

        target_col = next((c for c in df.columns if any(k in str(c) for k in ['标题', 'Title', 'Name', '商品名称','title','name'])),
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

            # 💡 传入 model_name 和 base_url
            results, status_msg = ai_rewrite_engine(
                batch_dict, char_limit, platform, language, key_pool, model_name, base_url
            )
            yield f"📝 [反馈] {status_msg}"

            for idx, content in results.items():
                df.at[idx, target_col] = content
                df.at[idx, 'AI_Status'] = "Optimized"

            if i + batch_size < total:
                yield f"⏳ 休眠 {sleep_time} 秒..."
                time.sleep(sleep_time)

        processed_results.append((file_obj.name, df))
        yield f"✅ {file_obj.name} 处理完毕！"

    yield "FINISH_SIGNAL"
    yield processed_results