import os
import threading
import json
import discord
from discord import app_commands
from discord.ext import commands
import requests
from flask import Flask
from datetime import datetime, timedelta, timezone

# 1. Flask 웹 서버 설정
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

GROUP_ID = int(os.environ.get("GROUP_ID", 0) or 0)
ROBLOSECURITY = os.environ.get("ROBLOSECURITY", "")

def get_roblox_user_info(query):
    query = query.strip()
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # 1. 숫자로 된 유저 ID를 입력한 경우 (API 실패 시에도 입력한 ID를 그대로 사용)
    if query.isdigit():
        user_id = int(query)
        uname = query
        display_name = query
        try:
            profile_url = f"https://users.roblox.com/v1/users/{user_id}"
            profile_res = requests.get(profile_url, headers=headers, timeout=5)
            if profile_res.status_code == 200:
                data = profile_res.json()
                uname = data.get("name", query)
                display_name = data.get("displayName", uname)
        except Exception:
            pass
        return user_id, uname, display_name

    # 2. 유저네임(문자열)을 입력한 경우
    try:
        url = "https://users.roblox.com/v1/usernames/users"
        payload = {"usernames": [query], "excludeBannedUsers": True}
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json().get("data", [])
            if data:
                user_id = data[0]["id"]
                uname = data[0]["name"]
                display_name = uname
                try:
                    profile_url = f"https://users.roblox.com/v1/users/{user_id}"
                    profile_res = requests.get(profile_url, headers=headers, timeout=5)
                    if profile_res.status_code == 200:
                        display_name = profile_res.json().get("displayName", uname)
                except Exception:
                    pass
                return user_id, uname, display_name
    except Exception as e:
        print(f"User search error: {e}")
        
    return None, None, None

def get_audit_logs_within_range(group_id, cookies, start_date_utc, end_date_utc):
    logs = []
    cursor = ""
    
    try:
        for _ in range(20):
            url = f"https://groups.roblox.com/v1/groups/{group_id}/audit-log?limit=100"
            if cursor:
                url += f"&cursor={cursor}"
            
            response = requests.get(url, cookies=cookies, timeout=10)
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
                        if dt < start_date_utc:
                            should_stop = True
                            break
                        if dt > end_date_utc:
                            continue
                        logs.append(item)
                    except Exception:
                        continue
            
            if should_stop:
                break
            
            cursor = data.get("nextPageCursor")
            if not cursor:
                break
    except Exception as e:
        print(f"Audit log fetch error: {e}")
            
    return logs

def format_kst_time(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        kst_dt = dt.astimezone(timezone(timedelta(hours=9)))
        return kst_dt.strftime("%Y년 %m월 %d일 %p %I:%M").replace("AM", "오전").replace("PM", "오후")
    except Exception:
        return iso_str

def extract_role_name(log):
    try:
        desc = log.get("description", {})
        if isinstance(desc, str):
            try:
                desc = json.loads(desc)
            except Exception:
                pass
        
        if isinstance(desc, dict):
            for key in ["NewRoleName", "RoleName", "roleName", "OldRoleName", "role", "Name"]:
                val = desc.get(key)
                if val and isinstance(val, str):
                    return val
            for k, v in desc.items():
                if isinstance(v, str) and v and not v.isdigit() and len(v) < 50:
                    if any(keyword in k.lower() for keyword in ["role", "name", "rank"]):
                        return v
        elif isinstance(desc, str) and desc:
            return desc
    except Exception:
        pass
    return "역할"

def format_log_sentence(log, default_target):
    actor = log.get("actor", {}).get("user", {}).get("username", "알 수 없음")
    action_type = log.get("actionType", "")
    desc = log.get("description", {})
    
    target = default_target
    if isinstance(desc, dict):
        if "TargetName" in desc:
            target = desc["TargetName"]
        elif "UserName" in desc:
            target = desc["UserName"]
    
    role_name = extract_role_name(log)
    
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
        print(f"Sync error: {e}")
    print(f'Discord Bot Logged in as {bot.user}!')

@bot.tree.command(name="감사로그", description="한국 시간 기준으로 정확한 기간을 설정하여 로블록스 그룹 감사 로그를 조회합니다.")
@app_commands.describe(
    대상자="조회할 로블록스 숫자 유저 ID 또는 유저네임 (예: 5447069104 또는 today22111)",
    시작일="시작 날짜 (형식: YYYY-MM-DD, 예: 2026-07-30)",
    종료일="종료 날짜 (형식: YYYY-MM-DD, 예: 2026-08-02 / 생략 시 오늘까지)"
)
async def audit_log(interaction: discord.Interaction, 대상자: str, 시작일: str, 종료일: str = None):
    await interaction.response.defer(thinking=True)

    search_query = 대상자.lstrip('$').strip()
    kst = timezone(timedelta(hours=9))

    try:
        try:
            start_kst = datetime.strptime(시작일.strip(), "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=kst)
            if 종료일 and 종료일.strip():
                end_kst = datetime.strptime(종료일.strip(), "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=kst)
            else:
                end_kst = datetime.now(kst)
        except ValueError:
            await interaction.followup.send("❌ 날짜 형식이 올바르지 않습니다. `YYYY-MM-DD` 형식으로 입력해주세요. (예: `2026-07-30`)")
            return

        start_utc = start_kst.astimezone(timezone.utc)
        end_utc = end_kst.astimezone(timezone.utc)

        target_user_id, username, display_name = get_roblox_user_info(search_query)
        if not target_user_id:
            await interaction.followup.send(f'❌ "{search_query}" 유저 정보를 처리할 수 없습니다.')
            return

        cookies = {".ROBLOSECURITY": ROBLOSECURITY}
        logs = get_audit_logs_within_range(GROUP_ID, cookies, start_utc, end_utc)
        
        if not logs:
            await interaction.followup.send(f'⚠️ 지정하신 기간({시작일} ~ {종료일 if 종료일 else "오늘" }) 동안의 감사 로그를 불러오지 못했거나 쿠키 권한이 부족합니다.')
            return

        user_logs = []
        for log in logs:
            target_info = log.get("target")
            desc = log.get("description", "")
            desc_str = str(desc)
            if isinstance(desc, dict):
                desc_str = " ".join([str(v) for v in desc.values()])
            
            actor_name = log.get("actor", {}).get("user", {}).get("username", "")
            
            match_id = (target_info and target_info.get("id") == target_user_id)
            match_name = (
                username.lower() in desc_str.lower() or
                display_name.lower() in desc_str.lower() or
                username.lower() in actor_name.lower() or
                display_name.lower() in actor_name.lower()
            )
            
            if match_id or match_name:
                user_logs.append(log)

        if not user_logs:
            period_str = f"{시작일}부터 {종료일}" if 종료일 else f"{시작일}부터 오늘까지"
            await interaction.followup.send(f'❌ "{search_query}"님과 관련된 **{period_str}** 기간 내 감사 로그를 찾지 못했습니다.')
            return

        period_label = f"{시작일} ~ {종료일}" if 종료일 else f"{시작일} ~ 오늘"
        response_text = f'**[ {search_query} ] 기간별 감사 로그 ({period_label} / 총 {len(user_logs)}개)**\n\n'
        for log in user_logs:
            date_str = format_kst_time(log.get("created", ""))
            sentence = format_log_sentence(log, username if username != search_query else search_query)
            
            entry_text = f'• **{date_str}**\n  {sentence}\n\n'
            
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
