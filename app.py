import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import requests
import anthropic

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

app = App(token=SLACK_BOT_TOKEN)
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

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

@app.event("app_mention")
def handle_mention(event, say):
    user_question = event["text"]
    notion_context = search_notion(user_question)
    prompt = f"""あなたはブルーグース合同会社の社内AIアシスタントです。
以下の社内ナレッジを参考に質問に答えてください。

社内ナレッジ：
{notion_context}

質問：{user_question}"""
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    say(response.content[0].text)

if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
