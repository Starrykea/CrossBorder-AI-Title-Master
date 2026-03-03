from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google import genai

app = FastAPI()
client = genai.Client(api_key="AIzaSyDDB97htOYw9neVopci9LhgMBdffWTHW_I")


class RewriteRequest(BaseModel):
    auth_code: str  # 授权码
    titles: dict  # 待处理标题 {id: title}
    platform: str


@app.post("/optimize")
async def optimize(request: RewriteRequest):
    # 1. 授权验证逻辑
    if request.auth_code != "888888":  # 这里以后接数据库查询卡密
        raise HTTPException(status_code=403, detail="授权码无效或已过期")

    # 2. 核心 Prompt (这是你的商业机密，藏在服务器里)
    prompt = f"针对{request.platform}优化以下标题，严格限60字符..."

    try:
        # 调用 Gemini (用户看不见这一步)
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt + str(request.titles))
        return {"status": "success", "results": response.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}