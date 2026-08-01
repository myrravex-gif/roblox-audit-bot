import os
import threading
import discord
from discord.ext import commands
import requests
from flask import Flask

# 1. Flask 웹 서버 설정 (Render 웹 서비스 포트 바인딩용)
app = Flask('')

@app.route('/')
def home():
    return "Roblox Audit Log Bot (Python) is running!"

def run_flask():
    port = int(os.environ.get("PORT", 3000))
    app.run(host='0.0.0.0', port=port)

# 2. 디스코드 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!감사로그', intents=intents)

GROUP_ID = int(os.environ.get("GROUP_ID", 0))
ROBLOSECURITY = os.environ.get("ROBLOSECURITY", "")

def get_roblox_user_id(username):
    url = "https://users.roblox.com/v1/usernames/users"
    payload = {"usernames": [username], "excludeBannedUsers": True}
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        data = response.json().get("data", [])
        if data:
            return data[0]["id"]
    return None

def get_audit_logs():
    url = f"https://groups.roblox.com/v1/groups/{GROUP_ID}/audit-log?limit=100"
    cookies = {".ROBLOSECURITY": ROBLOSECURITY}
    response = requests.get(url, cookies=cookies)
    if response.status_code == 200:
        return response.json().get("data", [])
    return []

@bot.event
async def on_ready():
    print(f'Discord Bot Logged in as {bot.user}!')

@bot.command(name='')
async def audit_log(ctx, target_username: str = None):
    if not target_username:
        await ctx.send("사용법: `!감사로그 [대상자 로블록스 닉네임]`")
        return

    status_msg = await ctx.send(f'🔍 "{target_username}"님의 그룹 감사 로그를 검색 중입니다...')

    try:
        target_user_id = get_roblox_user_id(target_username)
        if not target_user_id:
            await status_msg.edit(content=f'❌ "{target_username}" 로블록스 유저를 찾을 수 없습니다.')
            return

        logs = get_audit_logs()
        if not logs:
            await status_msg.edit(content='⚠️ 감사 로그를 불러오지 못했거나 쿠키 권한을 확인해주세요.')
            return

        user_logs = []
        for log in logs:
            target_info = log.get("target")
            description = str(log.get("description", ""))
            if (target_info and target_info.get("id") == target_user_id) or (target_username.lower() in description.lower()):
                user_logs.append(log)

        if not user_logs:
            await status_msg.edit(content=f'❌ "{target_username}"님과 관련된 최근 감사 로그를 찾지 못했습니다.')
            return

        response_text = f'📋 **[ {targetUsername} ] 관련 감사 로그 (최근 기록)**\n\n'
        for i, log in enumerate(user_logs[:5]):
            actor = log.get("actor", {}).get("user", {}).get("username", "알 수 없음")
            action = log.get("actionType", "작업")
            date = log.get("created", "알 수 없음")
            response_text += f'{i + 1}. **일시**: {date}\n   - **실행자**: **{actor}**\n   - **작업**: {action}\n\n'

        await status_msg.edit(content=response_text)

    except Exception as e:
        print(e)
        await status_msg.edit(content='⚠️ 감사 로그를 처리하는 중 오류가 발생했습니다.')

# Flask를 백그라운드로 실행하고 디스코드 봇 구동
if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    bot.run(os.environ.get("DISCORD_TOKEN"))
