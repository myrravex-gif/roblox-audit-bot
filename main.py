import os
import threading
import discord
from discord import app_commands
from discord.ext import commands
import requests
from flask import Flask
from datetime import datetime, timedelta, timezone

# 1. Flask 웹 서버 설정 (Render 웹 서비스 포트 바인딩용)
app = Flask('')

@app.route('/')
def home():
    return "Roblox Audit Log Bot (Python) is running!"

def run_flask():
    port = int(os.environ.get("PORT", 3000))
    app.run(host='0.0.0.0', port=port)

# 2. 디스코드 봇 설정 (슬래시 명령어 사용을 위해 intents 설정)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

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

def get_audit_logs_within_days(group_id, cookies, days):
    """지정한 기간(일수) 내의 감사 로그를 페이지네이션을 통해 수집"""
    logs = []
    cursor = ""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    # 최대 10페이지(약 1000개)까지만 탐색하여 무한 루프 및 레이트 리밋 방지
    for _ in range(10):
        url = f"https://groups.roblox.com/v1/groups/{group_id}/audit-log?limit=100"
        if cursor:
            url += f"&cursor={cursor}"
        
        response = requests.get(url, cookies=cookies)
        if response.status_code != 200:
            break
        
        data = response.json()
        items = data.get("data", [])
        if not items:
            break
        
        should_stop = False
        for item in items:
            created_str = item.get("created")
            if created_str:
                try:
                    dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    # 지정한 기간보다 오래된 로그에 도달하면 수집 중단
                    if dt < cutoff_date:
                        should_stop = True
                        break
                    logs.append(item)
                except Exception:
                    logs.append(item)
        
        if should_stop:
            break
        
        cursor = data.get("nextPageCursor")
        if not cursor:
            break
            
    return logs

@bot.event
async def on_ready():
    try:
        # 슬래시 명령어 전역 동기화
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)
    print(f'Discord Bot Logged in as {bot.user}!')

# 슬래시 명령어 정의
@bot.tree.command(name="감사로그", description="로블록스 그룹의 특정 유저 감사 로그를 기간별로 조회합니다.")
@app_commands.describe(
    대상자="조회할 로블록스 유저 닉네임",
    기간="조회할 기간 (일 단위, 예: 7일이면 7 입력)"
)
async def audit_log(interaction: discord.Interaction, 대상자: str, 기간: int):
    # 응답이 지연될 수 있으므로 처 중임을 먼저 알림 (타임아웃 방지)
    await interaction.response.defer(thinking=True)

    target_username = 대상자.lstrip('$')

    try:
        target_user_id = get_roblox_user_id(target_username)
        if not target_user_id:
            await interaction.followup.send(f'❌ "{target_username}" 로블록스 유저를 찾을 수 없습니다.')
            return

        cookies = {".ROBLOSECURITY": ROBLOSECURITY}
        logs = get_audit_logs_within_days(GROUP_ID, cookies, 기간)
        
        if not logs:
            await interaction.followup.send(f'⚠️ 최근 {기간}일 동안의 감사 로그를 불러오지 못했거나 쿠키 권한이 부족합니다.')
            return

        user_logs = []
        for log in logs:
            target_info = log.get("target")
            description = str(log.get("description", ""))
            actor_name = log.get("actor", {}).get("user", {}).get("username", "")
            
            if (target_info and target_info.get("id") == target_user_id) or \
               (target_username.lower() in description.lower()) or \
               (target_username.lower() in actor_name.lower()):
                user_logs.append(log)

        if not user_logs:
            await interaction.followup.send(f'❌ "{target_username}"님과 관련된 최근 {기간}일 내 감사 로그를 찾지 못했습니다.')
            return

        response_text = f'📋 **[ {target_username} ] 최근 {기간}일 간 감사 로그 (총 {len(user_logs)}개)**\n\n'
        for i, log in enumerate(user_logs):
            actor = log.get("actor", {}).get("user", {}).get("username", "알 수 없음")
            action = log.get("actionType", "작업")
            date = log.get("created", "알 수 없음")
            
            entry_text = f'{i + 1}. **일시**: {date}\n   - **실행자**: **{actor}**\n   - **작업**: {action}\n\n'
            
            if len(response_text) + len(entry_text) > 1900:
                response_text += '\n*(메시지 글자수 제한으로 일부 로그가 생략되었습니다)*'
                break
                
            response_text += entry_text

        await interaction.followup.send(response_text)

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        await interaction.followup.send(f'⚠️ 에러 발생: `{str(e)}`')

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    bot.run(os.environ.get("DISCORD_TOKEN"))
