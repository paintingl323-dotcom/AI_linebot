import google.generativeai as genai

# Configure Gemini API
genai.configure(api_key='AIzaSyC7zxk9HlxorgzQbY5vfd2kVPgBpQ_HKwg')

# Test the API connection
try:
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
    response = model.generate_content(
        "你好,請用繁體中文回覆。",
        generation_config={'max_output_tokens': 50}
    )
    print("✅ Gemini API 連接成功!")
    print(f"回應: {response.text}")
except Exception as e:
    print(f"❌ 錯誤: {e}")
