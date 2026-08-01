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

# 2. 디스코드 봇 설정
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
    logs = []
    cursor = ""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    
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

def format_kst_time(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        kst_dt = dt.astimezone(timezone(timedelta(hours=9)))
        return kst_dt.strftime("%Y년 %m월 %d일 %p %I:%M").replace("AM", "오전").replace("PM", "오후")
    except Exception:
        return iso_str

def format_log_sentence(log, default_target):
    actor = log.get("actor", {}).get("user", {}).get("username", "알 수 없음")
    action_type = log.get("actionType", "")
    desc = log.get("description", {})
    
    target = default_target
    role_name = "역할"
    
    if isinstance(desc, dict):
        if "TargetName" in desc:
            target = desc["TargetName"]
        elif "UserName" in desc:
            target = desc["UserName"]
            
        # 역할 이름이 담길 수 있는 다양한 키값 확인
        role_name = (
            desc.get("RoleName") or 
            desc.get("roleName") or 
            desc.get("OldRoleName") or 
            desc.get("NewRoleName") or 
            desc.get("Name") or 
            "역할"
        )
    
    if "Unassign Role" in action_type:
        return f"**{actor}** 님이 **{target}** 님에게 지정된 역할군 **{role_name}**을(를) 취소했어요."
    elif "Assign Role" in action_type:
        return f"**{actor}** 님이 **{target}** 님에게 역할군 **{role_name}**을(를) 부여했어요."
    elif "Change Rank" in action_type or "Update Rank" in action_type:
        return f"**{actor}** 님이 **{target}** 님의 랭크를 변경했어요."
    elif "Kick" in action_type:
        return f"**{actor}** 님이 **{target}** 님을 그룹에서 추방했어요."
    elif "Accept" in action_type:
        return f"**{actor}** 님이 **{target}** 님의 그룹 가입을 수락했어요."
    else:
        return f"**{actor}** 님이 **{target}** 님과 관련하여 **{action_type}** 작업을 수행했어요."

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)
    print(f'Discord Bot Logged in as {bot.user}!')

@bot.tree.command(name="감사로그", description="로블록스 그룹의 특정 유저 감사 로그를 자연스러운 문장으로 조회합니다.")
@app_commands.describe(
    대상자="조회할 로블록스 유저 닉네임",
    기간="조회할 기간 (일 단위, 예: 7일이면 7 입력)"
)
async def audit_log(interaction: discord.Interaction, 대상자: str, 기간: int):
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

        response_text = f'**[ {target_username} ] 최근 {기간}일 간 감사 로그 (총 {len(user_logs)}개)**\n\n'
        for log in user_logs:
            date_str = format_kst_time(log.get("created", ""))
            sentence = format_log_sentence(log, target_username)
            
            entry_text = f'**{date_str}**\n{sentence}\n\n'
            
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
