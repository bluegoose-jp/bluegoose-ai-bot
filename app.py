import os
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request
import requests
import anthropic

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SCREENPIPE_DATABASE_ID = os.environ["SCREENPIPE_DATABASE_ID"]

app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

def search_notion(query):
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    data = {"query": query, "filter": {"property": "object", "value": "page"}}
    res = requests.post("https://api.notion.com/v1/search", headers=headers, json=data)
    results = res.json().get("results", [])
    texts = []
    for page in results[:3]:
        page_id = page["id"]
        blocks_res = requests.get(f"https://api.notion.com/v1/blocks/{page_id}/children", headers=headers)
        blocks = blocks_res.json().get("results", [])
        for block in blocks:
            if block["type"] == "paragraph":
                for rt in block["paragraph"].get("rich_text", []):
                    texts.append(rt.get("plain_text", ""))
    return "\n".join(texts[:3000])

def get_screenpipe_context():
    """Screenpipe Daily Logの直近3件を取得してナレッジ化"""
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    # データベースから直近3件を取得
    data = {
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        "page_size": 3
    }
    res = requests.post(
        f"https://api.notion.com/v1/databases/{SCREENPIPE_DATABASE_ID}/query",
        headers=headers,
        json=data
    )
    pages = res.json().get("results", [])
    summaries = []
    for page in pages:
        page_id = page["id"]
        title = ""
        # タイトル取得
        props = page.get("properties", {})
        for prop in props.values():
            if prop.get("type") == "title":
                title_list = prop.get("title", [])
                if title_list:
                    title = title_list[0].get("plain_text", "")
        # ページ本文取得
        blocks_res = requests.get(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=headers
        )
        blocks = blocks_res.json().get("results", [])
        content = []
        for block in blocks:
            btype = block.get("type")
            if btype in ["paragraph", "bulleted_list_item", "heading_2", "heading_3"]:
                rich_texts = block.get(btype, {}).get("rich_text", [])
                for rt in rich_texts:
                    content.append(rt.get("plain_text", ""))
        summaries.append(f"【{title}】\n" + "\n".join(content[:500]))
    return "\n\n".join(summaries)

@app.event("app_mention")
def handle_mention(event, say):
    user_question = event["text"]
    notion_context = search_notion(user_question)
    screenpipe_context = get_screenpipe_context()

    prompt = f"""あなたはブルーグース合同会社の社内AIアシスタントです。
以下の社内ナレッジと直近の作業ログを参考に質問に答えてください。

【社内ナレッジ】
{notion_context}

【直近の作業ログ（Screenpipe）】
{screenpipe_context}

質問：{user_question}"""

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    say(response.content[0].text)

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))
```
