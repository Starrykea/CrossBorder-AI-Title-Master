import streamlit as st
import pandas as pd
import sqlite3
import os
import requests
import time


# --- 数据库初始化 ---
def init_db():
    conn = sqlite3.connect('local_cache.db')
    cursor = conn.cursor()
    # 存储原始标题、优化后标题、处理状态、所属文件
    cursor.execute('''CREATE TABLE IF NOT EXISTS titles
                      (
                          id
                          INTEGER
                          PRIMARY
                          KEY
                          AUTOINCREMENT,
                          file_name
                          TEXT,
                          raw_text
                          TEXT,
                          optimized_text
                          TEXT,
                          status
                          INTEGER
                          DEFAULT
                          0
                      )''')
    conn.commit()
    return conn


# --- 核心 UI 界面 ---
st.set_page_config(page_title="跨境AI大师 - 商业版", layout="wide")
conn = init_db()

st.title("🚀 跨境电商 AI 标题批量优化 (专业版)")

with st.sidebar:
    st.header("🔑 授权与配置")
    auth_code = st.text_input("输入授权卡密", type="password")
    platform = st.selectbox("目标平台", ["MercadoLibre", "Amazon", "Shopee"])
    server_url = "http://你的云服务器IP:8000/optimize"  # 你的大脑地址

# --- 1. 数据导入 ---
st.subheader("📂 数据导入")
folder_path = st.text_input("输入待处理 Excel 文件夹路径")

if st.button("🔍 扫描并准备数据"):
    if not folder_path or not os.path.exists(folder_path):
        st.error("路径无效！")
    else:
        files = [f for f in os.listdir(folder_path) if f.endswith(('.xlsx', '.xls'))]
        for f in files:
            df = pd.read_excel(os.path.join(folder_path, f))
            # 假设标题在第一列，实际可做下拉框选择
            for title in df.iloc[:, 0]:
                conn.execute("INSERT INTO titles (file_name, raw_text) VALUES (?, ?)", (f, str(title)))
        conn.commit()
        st.success(f"已将 {len(files)} 个文件的数据入库，准备开始。")

# --- 2. 状态统计 ---
pending_count = pd.read_sql("SELECT count(*) FROM titles WHERE status = 0", conn).iloc[0, 0]
done_count = pd.read_sql("SELECT count(*) FROM titles WHERE status = 1", conn).iloc[0, 0]

st.metric("待处理", pending_count, delta=f"已完成: {done_count}")

# --- 3. 执行优化 (断点续传核心) ---
if st.button("⚡ 开始/恢复 批量优化"):
    if not auth_code:
        st.warning("请先输入授权码！")
    else:
        # 每次取 20 条（Batch 处理，效率最高）
        while True:
            batch_df = pd.read_sql("SELECT * FROM titles WHERE status = 0 LIMIT 20", conn)
            if batch_df.empty:
                st.balloons()
                st.success("全部处理完毕！")
                break

            # 构造请求发给你的云端后端
            payload = {
                "auth_code": auth_code,
                "titles": batch_df.set_index('id')['raw_text'].to_dict(),
                "platform": platform
            }

            try:
                # 访问你的云端大脑
                resp = requests.post(server_url, json=payload, timeout=30)
                if resp.status_code == 200:
                    results = resp.json()['results']  # 假设后端返回 {id: text}
                    # 更新数据库状态
                    for tid, opt_text in results.items():
                        conn.execute("UPDATE titles SET optimized_text = ?, status = 1 WHERE id = ?", (opt_text, tid))
                    conn.commit()
                    st.write(f"✅ 已完成一批 (20条)...")
                else:
                    st.error(f"服务器报错: {resp.text}")
                    break
            except Exception as e:
                st.error(f"连接中断: {e}")
                break

            time.sleep(1)  # 适当频率控制

# --- 4. 结果导出 ---
if done_count > 0:
    if st.button("📥 导出所有已完成数据"):
        final_df = pd.read_sql("SELECT file_name, raw_text, optimized_text FROM titles WHERE status = 1", conn)
        st.download_button("点击下载 Excel", final_df.to_csv(index=False), "optimized_results.csv")