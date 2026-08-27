import re

def migrate_bot_py():
    with open('bot.py', 'r', encoding='utf-8') as f:
        code = f.read()

    # 1. Update Imports
    code = code.replace("import google.generativeai as genai", "from google import genai")

    # 2. Update Configuration and Initialization
    init_old = """genai.configure(api_key=GEMINI_API_KEY)

generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    generation_config=generation_config,
)"""
    init_new = """# genai Client
client = genai.Client(api_key=GEMINI_API_KEY)"""
    code = code.replace(init_old, init_new)

    # 3. Update get_gemini_response
    old_get_resp = """def get_gemini_response(query, user_id=None):
    try:
        final_query = query
        if user_id:
            personas = load_json(PERSONAS_FILE)
            if str(user_id) in personas:
                final_query = f"[SYSTEM INSTRUCTION: Mulai sekarang kamu HARUS berbicara dan bertingkah sepenuhnya dengan persona/gaya ini: '{personas[str(user_id)]}'. Jangan pernah keluar dari karakter.]\\n\\nPesan User: {query}"
                
            if user_id not in chat_sessions:
                chat_sessions[user_id] = model.start_chat(history=[])
            response = chat_sessions[user_id].send_message(final_query)
        else:
            chat_session = model.start_chat(history=[])
            response = chat_session.send_message(final_query)
        return response.text
    except Exception as e:
        logging.error(f"Error getting Gemini response: {str(e)}")
        return "Error getting response from Gemini." """

    new_get_resp = """def get_gemini_response(query, user_id=None):
    try:
        final_query = query
        if user_id:
            personas = load_json(PERSONAS_FILE)
            if str(user_id) in personas:
                final_query = f"[SYSTEM INSTRUCTION: Mulai sekarang kamu HARUS berbicara dan bertingkah sepenuhnya dengan persona/gaya ini: '{personas[str(user_id)]}'. Jangan pernah keluar dari karakter.]\\n\\nPesan User: {query}"
                
            if user_id not in chat_sessions:
                chat_sessions[user_id] = client.chats.create(model='gemini-2.5-flash')
            response = chat_sessions[user_id].send_message(final_query)
        else:
            chat_session = client.chats.create(model='gemini-2.5-flash')
            response = chat_session.send_message(final_query)
        return response.text
    except Exception as e:
        logging.error(f"Error getting Gemini response: {str(e)}")
        return "Error getting response from Gemini." """
    code = code.replace(old_get_resp, new_get_resp)

    # 4. Update the analyze/vision function (genai.upload_file -> client.files.upload)
    # Wait, let's use regex to find and replace the upload and generate content for vision
    # The old code usually looks like:
    # uploaded_file = genai.upload_file(path=file_path)
    # response = model.generate_content([query, uploaded_file])
    code = re.sub(
        r'uploaded_file = genai\.upload_file\(path=(.*?)\)', 
        r'uploaded_file = client.files.upload(file=\1)', 
        code
    )
    
    code = re.sub(
        r'response = model\.generate_content\(\[(.*?), uploaded_file\]\)',
        r"response = client.models.generate_content(model='gemini-2.5-flash', contents=[\1, uploaded_file])",
        code
    )

    with open('bot.py', 'w', encoding='utf-8') as f:
        f.write(code)

if __name__ == "__main__":
    migrate_bot_py()
