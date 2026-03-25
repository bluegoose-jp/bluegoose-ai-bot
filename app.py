import os
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request
from notion_client import Client as NotionClient
import anthropic

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

slack_app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
notion = NotionClient(auth=NOTION_TOKEN)
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
flask_app = Flask(__name__)
handler = SlackRequestHandler(slack_app)

def search_notion(query):
    results = notion.search(query=query, filter={"property": "object", "value": "page"})
    texts = []
    for page in results["results"][:3]:
        page_id = page["id"]
        blocks = notion.blocks.children.list(block_id=page_id)
        for block in blocks["results"]:
            if block["type"] == "paragraph":
                rich_text = block["paragraph"].get("rich_text", [])
                for rt in rich_text:
                    texts.append(rt.get("plain_text", ""))
    return "\n".join(texts[:3000])

@slack_app.event("app_mention")
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

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))
