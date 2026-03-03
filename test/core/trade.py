import os
import pandas as pd
import time
import re
import itertools
from google import genai
from tqdm import tqdm


def ai_rewrite_engine(id_titles_dict, char_limit, platform, language, key_pool):
    """支持多 Key 轮询的 AI 引擎 - 已接入 UI 参数"""
    input_payload = "\n".join([f"#{k}: {v}" for k, v in id_titles_dict.items()])

    # 动态构建 Prompt，加入 UI 传来的平台和语言
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
            # 如果是最后一次尝试也失败了，不在这里 sleep，直接跳出
            print(f"❌ 调试报错详情 (Attempt {attempt}): {str(e)}")
            if attempt < 3:
                time.sleep(5)  # 失败了等 5 秒换下一个 Key
            continue
    fallback_results = {}
    for idx, original_title in id_titles_dict.items():
        # 直接截断原始标题作为保底，确保程序能跑完
        fallback_results[idx] = str(original_title)[:char_limit].strip()

    return fallback_results, "⚠️ AI 调用失败，已启动保底截断逻辑"


# trade.py 核心逻辑修改
def start_optimization_task(folder_path, platform, char_limit, language, api_keys, batch_size, sleep_time):
    # 初始化轮询器
    key_pool = itertools.cycle(api_keys)

    yield f"🚀 系统启动 | 目标平台: {platform} | 字符限制: {char_limit} | 语言: {language}"
    yield f"🔑 密钥池状态: 已加载 {len(api_keys)} 个 API Key，准备轮询..."

    base_path = os.path.abspath(folder_path)
    output_dir = os.path.join(base_path, "Optimized_Output")
    if not os.path.exists(output_dir): os.makedirs(output_dir)

    files = [f for f in os.listdir(base_path) if f.endswith(('.xlsx', '.xls'))]

    for file_name in files:
        yield f"-------------------------------------------"
        yield f"📂 正在扫描文件: {file_name}"

        file_path = os.path.join(base_path, file_name)
        save_path = os.path.join(output_dir, f"Optimized_{file_name}")

        # 读取数据
        df = pd.read_excel(file_path)

        # 定位标题列
        target_col = next((c for c in df.columns if any(k in str(c) for k in ['标题', 'Title', 'Name','商品名称'])), None)
        if not target_col:
            yield f"⚠️ 警告: 文件 {file_name} 找不到标题列，已跳过。"
            continue

        # 检查是否已有备份列，没有则创建
        if 'Original_Backup' not in df.columns:
            df['Original_Backup'] = df[target_col]
            yield f"🛡️ 已创建原始标题备份列 [Original_Backup]"

        # 筛选待处理（检查是否已经有 AI_Status 标记）
        if 'AI_Status' not in df.columns:
            df['AI_Status'] = None

        pending_indices = df[df['AI_Status'].isna()].index.tolist()
        total = len(pending_indices)

        if total == 0:
            yield f"✅ 文件 {file_name} 已处理完毕，无需重复优化。"
            continue

        yield f"📊 待优化条数: {total} 条 | 预计批次: {(total // batch_size) + 1} 批"

        # 批量循环
        for i in range(0, total, batch_size):
            # 获取当前使用的 Key 并脱敏处理
            current_key = next(key_pool)
            masked_key = f"{current_key[:6]}****{current_key[-4:]}"

            yield f"⚡ [批次执行] 正在调用 Key: {masked_key}"
            yield f"🔄 [当前动作] 正在优化第 {i + 1} 到 {min(i + batch_size, total)} 条数据..."

            batch_idx = pending_indices[i: i + batch_size]
            batch_dict = {idx: df.at[idx, target_col] for idx in batch_idx}

            # 调用 AI 引擎 (这里传入你改好的 3 次重试+保底逻辑)
            results, status_msg = ai_rewrite_engine(batch_dict, char_limit, platform, language, key_pool)

            yield f"📝 [反馈结果] {status_msg}"

            # 覆盖原标题
            for idx, content in results.items():
                df.at[idx, target_col] = content
                df.at[idx, 'AI_Status'] = "Optimized"

            # 实时保存进度
            df.to_excel(save_path, index=False)
            yield f"💾 [自动保存] 进度已写入 Optimized_{file_name}"

            # 频率控制
            if i + batch_size < total:
                yield f"⏳ [频率控制] 为了防止 429 报错，休眠 {sleep_time} 秒..."
                time.sleep(sleep_time)

    yield f"==========================================="
    yield f"🎉 所有任务已全部完成！请到 Optimized_Output 文件夹查看结果。"