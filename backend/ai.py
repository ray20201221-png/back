import os
import google.generativeai as genai

# =====================
# Gemini API 設定
# =====================
genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)

# =====================
# 模型（免費穩定版）
# =====================
model = genai.GenerativeModel("gemini-1.5-flash")


# =====================
# AI Chat Function
# =====================
def ask_ai(messages):
    try:
        prompt = ""

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                prompt += f"[系統設定]\n{content}\n\n"
            elif role == "user":
                prompt += f"使用者: {content}\n"
            else:
                prompt += f"AI: {content}\n"

        response = model.generate_content(prompt)

        return response.text

    except Exception as e:
        return f"❌ Gemini Error: {str(e)}"
