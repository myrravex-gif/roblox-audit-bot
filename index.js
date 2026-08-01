const express = require('express');
const { Client, GatewayIntentBits } = require('discord.js');
const noblox = require('noblox.js');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;

app.get('/', (req, res) => {
    res.send('Roblox Audit Log Bot is running!');
});

app.listen(PORT, () => {
    console.log(`Web server is running on port ${PORT}`);
});

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent
    ]
});

const PREFIX = '!감사로그';
const GROUP_ID = Number(process.env.GROUP_ID);

client.once('ready', async () => {
    console.log(`Discord Bot Logged in as ${client.user.tag}!`);
    
    try {
        await noblox.setCookie(process.env.ROBLOSECURITY);
        console.log('Roblox logged in successfully via Cookie!');
    } catch (err) {
        console.error('Roblox login failed:', err);
    }
});

client.on('messageCreate', async message => {
    if (message.author.bot) return;
    if (!message.content.startsWith(PREFIX)) return;

    const args = message.content.slice(PREFIX.length).trim().split(' ');
    const targetUsername = args[0];

    if (!targetUsername) {
        return message.reply('사용법: `!감사로그 [대상자 로블록스 닉네임]`');
    }

    const statusMessage = await message.reply(`🔍 "${targetUsername}"님의 그룹 감사 로그를 검색 중입니다...`);

    try {
        const targetUserId = await noblox.getIdFromUsername(targetUsername);

        const auditLogs = await noblox.getAuditLog({
            group: GROUP_ID,
            limit: 100
        });

        const userLogs = auditLogs.filter(log => {
            if (log.target && log.target.id === targetUserId) return true;
            if (log.description && log.description.includes(targetUsername)) return true;
            return false;
        });

        if (userLogs.length === 0) {
            return statusMessage.edit(`❌ "${targetUsername}"님과 관련된 최근 감사 로그를 찾지 못했습니다.`);
        }

        let responseText = `📋 **[ ${targetUsername} ] 관련 감사 로그 (최근 기록)**\n\n`;

        userLogs.slice(0, 5).forEach((log, index) => {
            const actorName = log.actor && log.actor.user ? log.actor.user.username : '알 수 없음';
            const action = log.actionType || '작업';
            const date = new Date(log.created).toLocaleString('ko-KR');
            responseText += `${index + 1}. **일시**: ${date}\n   - **실행자**: **${actorName}**\n   - **작업**: ${action}\n\n`;
        });

        await statusMessage.edit(responseText);

    } catch (error) {
        console.error(error);
        await statusMessage.edit('⚠️ 감사 로그를 불러오는 중 오류가 발생했습니다. 닉네임이 올바른지 확인해주세요.');
    }
});

client.login(process.env.DISCORD_TOKEN);
