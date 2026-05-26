
import os
import google.generativeai as genai

# Gemini API Key
genai.configure(
    api_key=os.getenv("AIzaSyDCe7OkatnnPUaj_VtgY8XYgFKW-8lJJtg")
)

# 模型
model = genai.GenerativeModel(
    "gemini-1.5-flash"
)

# AI 聊天
def ask_ai(messages):

    try:

        prompt = ""

        for msg in messages:

            role = msg["role"]
            content = msg["content"]

            prompt += f"{role}: {content}\n"

        response = model.generate_content(prompt)

        return response.text

    except Exception as e:

        return f"❌ Gemini Error: {str(e)}"
