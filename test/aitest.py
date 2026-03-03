from google import genai
import os

# --- 填入那个美国的 API Key ---
API_KEY = "AIzaSyDDB97htOYw9neVopci9LhgMBdffWTHW_I"


def test_connection():
    try:
        print("正在尝试连接 Google AI 服务器...")
        client = genai.Client(api_key=API_KEY)

        # 发送一个最简单的测试请求
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents="你好，如果你能收到这条消息，请回复：连接成功！"
        )

        if response.text:
            print("\n✅ 【恭喜】测试通过！")
            print(f"AI 回复内容: {response.text}")
            print("\n结论：你的台湾代理环境有效，且该美国 API Key 状态正常。")
        else:
            print("\n❌ 收到空返回。可能是配额被占满。")

    except Exception as e:
        print("\n❌ 【测试失败】")
        error_msg = str(e)
        if "429" in error_msg:
            print("错误原因：429 Resource Exhausted (配额不足/请求太快)")
        elif "403" in error_msg:
            print("错误原因：403 Forbidden (地区限制，请检查你的台湾代理是否为全局模式)")
        else:
            print(f"其他错误: {error_msg}")


if __name__ == "__main__":
    test_connection()