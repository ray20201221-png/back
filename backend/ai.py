import os

import google.generativeai as genai


genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel("gemini-2.5-flash")


def generate_text(prompt: str) -> str:
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini Error: {str(e)}"


def ask_ai(messages):
    prompt = ""

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "system":
            prompt += f"[System]\n{content}\n\n"
        elif role == "user":
            prompt += f"User: {content}\n"
        else:
            prompt += f"AI: {content}\n"

    return generate_text(prompt)
