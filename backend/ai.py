import os
import google.generativeai as genai

# =====================
# Gemini API 設定
# =====================
genai.configure(
    api_key=os.getenv("AIzaSyDCe7OkatnnPUaj_VtgY8XYgFKW-8lJJtg")
)

# Gemini 模型
model = genai.GenerativeModel("gemini-1.5-flash")


# =====================
# AI Chat Function
# =====================
def ask_ai(messages):
    try:
        # 把 chat history 轉成 Gemini prompt
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

        # 呼叫 Gemini
        response = model.generate_content(prompt)

        return response.text

    except Exception as e:
        return f"❌ Gemini Error: {str(e)}"
