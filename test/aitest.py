# from google import genai
# import os
#
# # --- 填入那个美国的 API Key ---
# API_KEY = "AIzaSyDDB97htOYw9neVopci9LhgMBdffWTHW_I"
#
#
# def test_connection():
#     try:
#         print("正在尝试连接 Google AI 服务器...")
#         client = genai.Client(api_key=API_KEY)
#
#         # 发送一个最简单的测试请求
#         response = client.models.generate_content(
#             model="models/gemini-2.5-flash",
#             contents="你好，如果你能收到这条消息，请回复：连接成功！"
#         )
#
#         if response.text:
#             print("\n✅ 【恭喜】测试通过！")
#             print(f"AI 回复内容: {response.text}")
#             print("\n结论：你的台湾代理环境有效，且该美国 API Key 状态正常。")
#         else:
#             print("\n❌ 收到空返回。可能是配额被占满。")
#
#     except Exception as e:
#         print("\n❌ 【测试失败】")
#         error_msg = str(e)
#         if "429" in error_msg:
#             print("错误原因：429 Resource Exhausted (配额不足/请求太快)")
#         elif "403" in error_msg:
#             print("错误原因：403 Forbidden (地区限制，请检查你的台湾代理是否为全局模式)")
#         else:
#             print(f"其他错误: {error_msg}")
#
#
# if __name__ == "__main__":
#     test_connection()
import os
from openai import OpenAI

# 💡 直接把字符串写在这里，去掉 os.environ.get
# client = OpenAI(
#     api_key="sk-31f78a4558894868b0f0b93773483154",
#     base_url="https://api.deepseek.com"
# )
#
# try:
#     response = client.chat.completions.create(
#         model="deepseek-chat",
#         messages=[
#             {"role": "system", "content": "You are a helpful assistant"},
#             {"role": "user", "content": "Hello"},
#         ],
#         stream=False
#     )
#     print("✅ 测试成功！AI 回复：")
#     print(response.choices[0].message.content)
# except Exception as e:
#     print(f"❌ 测试失败，错误详情：{e}")
# import google.generativeai as genai
# import os
#
# # ================= 配置区 =================
# # 请在此处填入你的 API Key
# API_KEY = "AIzaSyAo4EMeqi2nidC7Gt8s09UJMRc0AQP-Q9U"
# # 指定模型
# MODEL_NAME = "gemini-2.5-flash"
#
#
# # ==========================================
#
# def test_gemini_connection():
#     print(f"正在尝试连接 {MODEL_NAME} 接口...")
#
#     # 1. 配置 API Key
#     genai.configure(api_key=API_KEY)
#
#     try:
#         # 2. 初始化模型
#         model = genai.GenerativeModel(MODEL_NAME)
#
#         # 3. 发起一个简单的文本请求
#         response = model.generate_content("你好，如果你收到了这条消息，请回复：接口调用正常。")
#
#         # 4. 输出结果
#         print("-" * 30)
#         print("测试成功！")
#         print(f"模型回复: {response.text}")
#         print("-" * 30)
#
#     except Exception as e:
#         print("-" * 30)
#         print("测试失败！请检查以下可能的原因：")
#         print(f"错误信息: {e}")
#         print("\n[排查提示]:")
#         print("1. 503 错误：服务器过载或 VPN 节点被拦截，请尝试更换美国/新加坡节点。")
#         print("2. 401 错误：API Key 无效。")
#         print("3. 403 错误：地区不受支持，请确认 VPN 已开启全局模式并切换至支持国家。")
#         print("-" * 30)
#
#
# if __name__ == "__main__":
#     test_gemini_connection()
# import random
#
#
# def generate_valid_upc():
#     # 1. 随机生成前 11 位
#     digits = [random.randint(0, 9) for _ in range(11)]
#
#     # 2. 计算第 12 位校验码
#     # 步骤：(奇数位之和 * 3 + 偶数位之和) % 10，再用 10 减去余数
#     odd_sum = sum(digits[0::2])
#     even_sum = sum(digits[1::2])
#     total = (odd_sum * 3) + even_sum
#     check_digit = (10 - (total % 10)) % 10
#
#     digits.append(check_digit)
#     return "".join(map(str, digits))
#
#
# # 生成 5 个测试用 UPC
# for _ in range(218):
#     print(generate_valid_upc())