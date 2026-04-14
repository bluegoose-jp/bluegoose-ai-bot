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

# ========================================
# Notionからクライアント一覧を動的取得
# ========================================
def get_client_list():
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    data = {
        "query": "クライアント別SOP",
        "filter": {"property": "object", "value": "page"}
    }
    res = requests.post("https://api.notion.com/v1/search", headers=headers, json=data)
    pages = res.json().get("results", [])

    clients = []
    for page in pages:
        for prop in page.get("properties", {}).values():
            if prop.get("type") == "title":
                title_list = prop.get("title", [])
                if title_list:
                    name = title_list[0].get("plain_text", "").strip()
                    if name:
                        clients.append(f"- {name}")

    if not clients:
        # Notionから取得できない場合のフォールバック
        return """- SteelSeries
- STEAMS LAB JAPAN（SLJ）
- 尾張まるはち（OM）
- スカイル（旧ロジェールジャパン）
- Pipelines
- Belkin
- UTプロダクツ
- 丸平かつおぶし"""

    return "\n".join(clients)


# ========================================
# 会社コンテキストを動的に構築
# ========================================
def build_company_context():
    client_list = get_client_list()
    return f"""
【会社情報】
会社名：ブルーグース合同会社
代表：及川謙一
事業：日本国内のAmazonセラー・ベンダー向けコンサルティング・運用代行エージェンシー
主なサービス：Amazon広告運用、カタログ改善、セラーセントラル・ベンダーセントラル運用代行、月次レポート作成
チーム：代表1名＋社員3名（主にAmazon商品登録・カタログ改善・トラブルシューティング担当）

【現在のクライアント】
{client_list}

【会社の方針・最終目標】
- 最終目標1：定型業務（カタログ改善・広告運用）のAI・Botによる完全自動化
- 最終目標2：クライアントワーク（顧客折衝・定例MTG・戦略提案）を将来採用する人間に移譲
- マニュアルはNotionに蓄積し、このBotも参照する
- AIインフラ：Claude（主要AI）＋Notion＋Slack＋GAS＋Screenpipe＋Railway/Flask

【回答方針】
- 日本語で回答すること
- 結論を先に、簡潔に答えること
- 不明な場合は推測せず「Notionに該当情報がありません」と明示すること
- クライアント固有の情報を聞かれた場合は、そのクライアントのSOPを優先参照すること
- Amazon業務に関する質問には具体的な手順を答えること
"""


# ========================================
# Notion全ページ取得
# ========================================
def get_all_notion_pages():
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    all_texts = []
    start_cursor = None

    while True:
        data = {
            "filter": {"property": "object", "value": "page"},
            "page_size": 100
        }
        if start_cursor:
            data["start_cursor"] = start_cursor

        res = requests.post("https://api.notion.com/v1/search", headers=headers, json=data)
        result = res.json()
        pages = result.get("results", [])

        for page in pages:
            page_id = page["id"]
            title = ""
            for prop in page.get("properties", {}).values():
                if prop.get("type") == "title":
                    title_list = prop.get("title", [])
                    if title_list:
                        title = title_list[0].get("plain_text", "")

            blocks_res = requests.get(
                f"https://api.notion.com/v1/blocks/{page_id}/children",
                headers=headers
            )
            blocks = blocks_res.json().get("results", [])
            content = []
            for block in blocks:
                btype = block.get("type")
                if btype in ["paragraph", "bulleted_list_item", "numbered_list_item",
                             "heading_1", "heading_2", "heading_3", "quote", "callout"]:
                    rich_texts = block.get(btype, {}).get("rich_text", [])
                    for rt in rich_texts:
                        content.append(rt.get("plain_text", ""))

            if content:
                all_texts.append(f"【{title}】\n" + "\n".join(content))

        if not result.get("has_more"):
            break
        start_cursor = result.get("next_cursor")

    return "\n\n".join(all_texts)[:80000]


# ========================================
# Screenpipe直近ログ取得
# ========================================
def get_screenpipe_context():
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
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
        for prop in page.get("properties", {}).values():
            if prop.get("type") == "title":
                title_list = prop.get("title", [])
                if title_list:
                    title = title_list[0].get("plain_text", "")
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


# ========================================
# Slackメンション応答
# ========================================
@app.event("app_mention")
def handle_mention(event, say):
    user_question = event["text"]

    # 毎回動的に会社コンテキストを構築（クライアント一覧が自動更新される）
    company_context = build_company_context()
    notion_context = get_all_notion_pages()
    screenpipe_context = get_screenpipe_context()

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        system=company_context,
        messages=[{
            "role": "user",
            "content": f"""以下の社内ナレッジと直近の作業ログを参考に質問に答えてください。

【社内ナレッジ（Notion全ページ）】
{notion_context}

【直近の作業ログ（Screenpipe）】
{screenpipe_context}

質問：{user_question}"""
        }]
    )
    say(response.content[0].text)


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))
