import os
import uuid
import google.generativeai as genai
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage

app = Flask(__name__)

# --- 設定區 (建議放環境變數) ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# 檢查環境變數，避免在執行時才報錯 (Check environment variables)
if not all([LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, GEMINI_API_KEY]):
    print("Warning: One or more environment variables are missing. The app may not function correctly.")

# --- 初始化 ---
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel('models/gemini-2.5-flash-lite')

# 確保 static 資料夾存在，用於暫存生成的圖片
if not os.path.exists('static'):
    os.makedirs('static')

@app.route("/")
def home():
    return "Agent is running!", 200

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text.strip()
    
    # 圖片生成功能：如果訊息以 "/畫圖" 開頭
    if user_msg.startswith("/畫圖"):
        prompt = user_msg.replace("/畫圖", "", 1).strip()
        if not prompt:
            return
        image_model = genai.GenerativeModel('models/gemini-2.0-flash-exp-image-generation')
        try:
            # 4. 呼叫 Gemini 生圖 API
            response = image_model.generate_content(prompt)
            
            # 檢查是否成功生成圖片
            if not response.parts or not response.parts[0].inline_data:
                 raise Exception("模型拒絕生成或生成失敗")

            image_data = response.parts[0].inline_data.data

            # 5. 將圖片存檔到 static 資料夾
            # 使用 uuid 產生隨機檔名，避免多人同時使用時蓋掉
            filename = f"{uuid.uuid4()}.png"
            file_path = os.path.join(app.root_path, 'static', filename)
            
            with open(file_path, "wb") as f:
                f.write(image_data)

            # 6. 產生圖片的公開網址
            # request.host_url 會抓到你現在的 Render 網址 (例如 https://xxxx.onrender.com/)
            image_url = request.host_url + 'static/' + filename
            print(f"Generated Image URL: {image_url}")

            # 7. 發送圖片給 LINE
            # preview_image_url 是縮圖，我們這裡直接用原圖網址
            line_bot_api.reply_message(
                event.reply_token,
                ImageSendMessage(original_content_url=image_url, preview_image_url=image_url)
            )

        except Exception as e:
            print(f"Image generation error: {e}")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"畫圖失敗了... 原因可能是涉及敏感內容或模型太忙碌。")
            )

    # 邏輯：只有開頭包含 "呼叫" 或是特定關鍵字才觸發 AI，避免群組太吵
    # 你也可以改成檢查是否被 @mention (需要解析 event 細節)
    trigger_word = "助手" 
    
    if trigger_word in user_msg:
        # 去掉觸發詞，剩下的丟給 AI
        prompt = user_msg.replace(trigger_word, "").strip()
        
        if not prompt:
            return

        try:
            # 呼叫 Gemini
            response = model.generate_content(prompt)
            reply_text = response.text
            
            # 回傳 LINE
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply_text)
            )
        except Exception as e:
            print(f"Error: {e}")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="大腦暫時短路了，請稍後再試。")
            )

if __name__ == "__main__":
    app.run()