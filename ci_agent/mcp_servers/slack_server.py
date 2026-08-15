from fastmcp import FastMCP
from slack_sdk import WebClient
import os

mcp = FastMCP("slack-notifier")
client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])

@mcp.tool()
def post_digest(channel: str, markdown_text: str) -> dict:
    """Post the weekly competitive brief to a Slack channel."""
    resp = client.chat_postMessage(channel=channel, text=markdown_text, mrkdwn=True)
    return {"ok": resp["ok"], "ts": resp.get("ts")}

if __name__ == "__main__":
    mcp.run(transport="stdio", show_banner=False)