import requests

OLLAMA_URL = "http://localhost:11434/api/chat"

MODEL = "llama3.2"

def ask_ai(messages):

    try:

        res = requests.post(

            OLLAMA_URL,

            json={
                "model": MODEL,
                "messages": messages,
                "stream": False
            }

        )

        data = res.json()

        return data["message"]["content"]

    except Exception as e:

        return f"❌ AI Error: {str(e)}"