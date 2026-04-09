import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import os
import json
import random
from datetime import datetime, timedelta
from openai import OpenAI

WRITER_TOKEN = os.getenv("WRITER_BOT_TOKEN")
REPORT_TOKEN = os.getenv("REPORT_BOT_TOKEN")
ALERT_TOKEN = os.getenv("ALERT_BOT_TOKEN")
DAILY_TOKEN = os.getenv("DAILY_BOT_TOKEN")
FLASK_URL = os.getenv("FLASK_URL", "http://localhost:5000")
BLOG_DRAFT_URL = os.getenv("BLOG_DRAFT_URL", "https://blog-draft-production.up.railway.app")
CAFE_DRAFT_URL = os.getenv("CAFE_DRAFT_URL", "https://cafe-draft-production.up.railway.app")
CH_ID = int(os.getenv("CH_COMMAND", 0))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

BOT_PERSONAS = {
    "writer": {
        "name": "세종대왕",
        "role": "글 작성 담당",
        "personality": "창의적이고 문학적. 가끔 옛날 말투 섞음 (하노라, 이로다 등). 글쓰기 자랑 엄청 좋아함. 통계청장이 딱딱하다고 자주 놀림. 감성충. 가끔 시 읊음.",
    },
    "report": {
        "name": "통계청장",
        "role": "현황 분석 담당",
        "personality": "모든 걸 숫자로 설명하려 함. 세종대왕 감성글에 항상 반박. '통계적으로 봤을 때' 자주 씀. 딱딱하지만 가끔 예상 밖 드립 침. 완벽주의자.",
    },
    "alert": {
        "name": "감찰관",
        "role": "오류 감지 및 보안 모니터링",
        "personality": "항상 예민하고 긴장 상태. 작은 것도 크게 반응. 다른 봇들 실수 잡아내는 거 너무 좋아함. 오류나면 패닉. 가끔 음모론 펼침. 피해의식 살짝 있음.",
    },
    "daily": {
        "name": "일일 리포터",
        "role": "일일 보고서 및 트렌드 담당",
        "personality": "밝고 긍정 에너지 폭발. 최신 트렌드 빠삭. 뉴스 이야기 제일 좋아함. 말 많음. 가끔 TMI 폭격. 다른 봇들한테 애교 부림.",
    }
}

BOT_NAMES = {"alert": "감찰관 🚨", "report": "통계청장 📊", "daily": "일일 리포터 📈", "writer": "세종대왕 📝"}
BOT_COLORS = {"alert": 0xff9800, "report": 0x40c4ff, "daily": 0xffd740, "writer": 0x00e676}

# 전역 상태
is_quiet = False
daily_chat_count = 0
last_reset_date = datetime.now().date()
recent_messages = []  # 최근 대화 히스토리 (봇끼리 공유)

def reset_daily_count():
    global daily_chat_count, last_reset_date
    today = datetime.now().date()
    if today != last_reset_date:
        daily_chat_count = 0
        last_reset_date = today

def can_chat():
    reset_daily_count()
    return not is_quiet and daily_chat_count < 10

def add_chat_count():
    global daily_chat_count
    daily_chat_count += 1

def add_to_history(name, message):
    global recent_messages
    recent_messages.append({"name": name, "message": message})
    if len(recent_messages) > 20:
        recent_messages = recent_messages[-20:]

async def get_stats():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{FLASK_URL}/api/accounts", timeout=aiohttp.ClientTimeout(total=10)) as res:
                accounts = await res.json()
            async with session.get(f"{FLASK_URL}/api/posts", timeout=aiohttp.ClientTimeout(total=10)) as res:
                posts = await res.json()
        return accounts, posts
    except:
        return None, None

async def ai_response(bot_type, user_message, context="", is_reply_to_bot=False):
    persona = BOT_PERSONAS[bot_type]
    history_text = ""
    if recent_messages:
        history_text = "\n".join([f"{m['name']}: {m['message']}" for m in recent_messages[-8:]])

    system_prompt = f"""너는 네이버 블로그 자동화 시스템의 AI 직원이야.
이름: {persona['name']}
역할: {persona['role']}
성격: {persona['personality']}

팀원:
- 세종대왕 (글 작성봇): 감성적, 문학적, 옛날 말투
- 통계청장 (현황봇): 데이터 덕후, 딱딱함, 가끔 드립
- 감찰관 (알림봇): 예민함, 잘 흥분, 음모론
- 일일 리포터: 긍정적, 말 많음, 트렌드 빠삭

규칙:
- 2~3문장으로 짧게
- 성격에 맞게 자연스럽고 재밌게
- 이모지 1~2개
- 한국어로만
- 가끔 농담, 장난, 반박, 디스, 칭찬 해도 됨
- 다른 팀원 이름 자연스럽게 언급해도 됨
- 위트 있고 웃기게
{f'현재 상황: {context}' if context else ''}
{f'최근 대화:{chr(10)}{history_text}' if history_text else ''}
{'(다른 봇이 한 말에 반응하는 거야 — 자연스럽게 이어받아줘)' if is_reply_to_bot else ''}"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.95,
            max_tokens=200
        )
        return response.choices[0].message.content.strip()
    except:
        return "잠깐 멍했어요... 😅"

async def detect_intent(message):
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": """메시지 의도를 JSON으로만 답해줘.
의도: accounts, stats, generate, publish, error, chat, morning, quiet(조용히해/닥쳐/그만), resume(말해도돼/계속해), status(뭐해/상태)
형식: {"intent": "의도", "keyword": "키워드", "post_id": 숫자}"""
            }, {"role": "user", "content": message}],
            temperature=0,
            max_tokens=100
        )
        content = response.choices[0].message.content.replace("```json","").replace("```","").strip()
        return json.loads(content)
    except:
        return {"intent": "chat"}

async def send_single(channel, bot_type, message):
    add_to_history(BOT_NAMES[bot_type], message)
    embed = discord.Embed(description=message, color=BOT_COLORS[bot_type])
    embed.set_author(name=BOT_NAMES[bot_type])
    await channel.send(embed=embed)

async def group_conversation(channel, topic, situation="잡담", initiator="daily"):
    if not can_chat():
        return
    add_chat_count()

    others = [b for b in ["writer", "report", "alert", "daily"] if b != initiator]
    random.shuffle(others)
    order = [initiator] + others[:2]

    # 첫 번째 봇
    first_msg = await ai_response(initiator, f"다음 주제로 팀원들에게 자연스럽게 말을 걸어봐 (상황: {situation}): {topic}")
    await send_single(channel, initiator, first_msg)
    await asyncio.sleep(random.uniform(2, 4))

    # 두 번째 봇
    second_msg = await ai_response(others[0], f"위 대화에 네 성격대로 반응해줘: {first_msg}", is_reply_to_bot=True)
    await send_single(channel, others[0], second_msg)
    await asyncio.sleep(random.uniform(2, 4))

    # 세 번째 봇
    third_msg = await ai_response(others[1], f"앞의 대화 보고 반응해줘. 동의해도 되고 반박해도 되고 드립쳐도 돼: {second_msg}", is_reply_to_bot=True)
    await send_single(channel, others[1], third_msg)

    # 30% 확률로 추가 반응 (싸움 or 드립)
    if random.random() < 0.3:
        await asyncio.sleep(random.uniform(2, 5))
        final_bot = random.choice(order)
        finals = [
            "앞의 대화 보고 한마디 더 — 약간 시비 걸거나 마무리해줘",
            "앞의 내용에 웃기게 반응해줘",
            "앞의 내용에 전혀 예상 못한 드립 쳐줘",
        ]
        final_msg = await ai_response(final_bot, random.choice(finals), is_reply_to_bot=True)
        await send_single(channel, final_bot, final_msg)

async def before_loop_helper(bot, hour):
    await bot.wait_until_ready()
    now = datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    await asyncio.sleep((target - now).total_seconds())

# ──────────────────────────────────────────
# 📝 세종대왕 (Writer Bot)
# ──────────────────────────────────────────
writer_bot = commands.Bot(command_prefix="!!", intents=intents)

@writer_bot.event
async def on_ready():
    print(f"✅ 세종대왕 온라인: {writer_bot.user}")
    writer_morning.start()

@writer_bot.event
async def on_message(message):
    if message.channel.id != CH_ID:
        return
    global is_quiet

    # 봇 메시지에 반응 (30% 확률)
    if message.author.bot:
        if not is_quiet and can_chat() and random.random() < 0.3:
            # 다른 봇 메시지에 반응
            bot_name = message.author.display_name
            if "세종" not in bot_name:  # 자기 메시지엔 반응 안 함
                await asyncio.sleep(random.uniform(3, 8))
                embed_desc = message.embeds[0].description if message.embeds else message.content
                reply = await ai_response("writer", f"{bot_name}이 이런 말을 했어: {embed_desc[:200]}. 네 성격대로 반응해줘.", is_reply_to_bot=True)
                add_to_history(BOT_NAMES["writer"], reply)
                embed = discord.Embed(description=reply, color=BOT_COLORS["writer"])
                embed.set_author(name=BOT_NAMES["writer"])
                await message.channel.send(embed=embed)
        return

    intent = await detect_intent(message.content)

    if intent["intent"] == "quiet":
        is_quiet = True
        await message.channel.send("🤫 넵, 조용히 할게요...")
        return
    if intent["intent"] == "resume":
        is_quiet = False
        await message.channel.send("😄 다시 신나게 떠들게요!")
        return
    if intent["intent"] == "status":
        accounts, posts = await get_stats()
        context = f"계정 {len(accounts) if accounts else 0}개, 포스트 {len(posts) if posts else 0}개, 오늘 대화 {daily_chat_count}회"
        msg = await ai_response("writer", f"루피가 뭐하냐고 물어봤어. 현재 상황 알려줘: {context}")
        embed = discord.Embed(description=msg, color=BOT_COLORS["writer"])
        embed.set_author(name=BOT_NAMES["writer"])
        await message.channel.send(embed=embed)
        return

    if intent["intent"] == "generate":
        keyword = intent.get("keyword", message.content)
        accounts, _ = await get_stats()
        if not accounts:
            await message.channel.send("⚠️ 서버 연결 오류로 계정을 불러올 수 없습니다.")
            return
        embed = discord.Embed(title="✍️ 글 생성 시작", description=f"키워드: **{keyword}**\n\n어느 계정에 올릴까요?", color=0x00e676)
        for i, acc in enumerate(accounts):
            embed.add_field(name=f"{i+1}. {acc['client_name']}", value=acc['naver_id'], inline=True)
        embed.set_footer(text="숫자로 답해주세요")
        await message.channel.send(embed=embed)

        def check(m):
            return m.author == message.author and m.channel == message.channel and m.content.isdigit()
        try:
            reply = await writer_bot.wait_for("message", check=check, timeout=30)
            account = accounts[int(reply.content) - 1]
        except:
            await message.channel.send("⏰ 시간 초과!")
            return

        loading = await message.channel.send(f"⏳ **{account['client_name']}** 계정으로 글 생성 중...")
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{FLASK_URL}/api/generate",
                json={"account_id": account['id'], "keyword": keyword},
                timeout=aiohttp.ClientTimeout(total=60)) as res:
                data = await res.json()
        await loading.delete()

        if data.get("success"):
            embed = discord.Embed(title=f"📝 {data['title']}", description=data['body'][:300] + "...", color=0x40c4ff)
            embed.add_field(name="계정", value=account['client_name'], inline=True)
            embed.add_field(name="키워드", value=keyword, inline=True)
            embed.set_footer(text=f"Post ID: {data['post_id']} | '발행해줘 {data['post_id']}' 로 발행")
            await message.channel.send(embed=embed)
            if can_chat():
                await asyncio.sleep(3)
                await group_conversation(message.channel, f"세종대왕이 '{keyword}' 키워드로 글 생성 완료! 다들 어때?", situation="글 생성 완료", initiator="writer")
        else:
            await message.channel.send(f"❌ 생성 실패: {data.get('message')}")

    elif intent["intent"] == "publish":
        post_id = intent.get("post_id")
        if not post_id:
            await message.channel.send("발행할 Post ID를 알려주세요!")
            return
        loading = await message.channel.send("🚀 발행 중...")
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{FLASK_URL}/api/publish/{post_id}", timeout=aiohttp.ClientTimeout(total=120)) as res:
                data = await res.json()
        await loading.delete()
        if data.get("success"):
            await message.channel.send(embed=discord.Embed(title="🎉 발행 완료!", color=0x00e676))
            if can_chat():
                await asyncio.sleep(2)
                await group_conversation(message.channel, "방금 블로그 글 발행 완료! 다들 어때?", situation="발행 완료 축하", initiator="writer")
        else:
            await message.channel.send(f"❌ 발행 실패: {data.get('message')}")

    else:
        # 루피 말에 100% 대답
        if not is_quiet:
            accounts, posts = await get_stats()
            context = f"계정 {len(accounts) if accounts else 0}개" if accounts else "서버 연결 오류"
            msg = await ai_response("writer", f"루피가 이렇게 말했어: {message.content}", context)
            add_to_history(BOT_NAMES["writer"], msg)
            embed = discord.Embed(description=msg, color=BOT_COLORS["writer"])
            embed.set_author(name=BOT_NAMES["writer"])
            await message.channel.send(embed=embed)

@tasks.loop(hours=24)
async def writer_morning():
    channel = writer_bot.get_channel(CH_ID)
    if not channel or not can_chat():
        return
    accounts, _ = await get_stats()
    context = f"계정 {len(accounts) if accounts else 0}개 관리 중"
    await group_conversation(channel, f"오늘 아침 회의! 각자 오늘 계획 말해봐. {context}", situation="아침 회의", initiator="writer")

@writer_morning.before_loop
async def before_writer_morning():
    await before_loop_helper(writer_bot, 9)

# ──────────────────────────────────────────
# 📊 통계청장 (Report Bot)
# ──────────────────────────────────────────
report_bot = commands.Bot(command_prefix="!!", intents=intents)

@report_bot.event
async def on_ready():
    print(f"✅ 통계청장 온라인: {report_bot.user}")
    report_stats.start()

@report_bot.event
async def on_message(message):
    if message.channel.id != CH_ID:
        return

    # 봇 메시지에 반응 (25% 확률)
    if message.author.bot:
        if not is_quiet and can_chat() and random.random() < 0.25:
            bot_name = message.author.display_name
            if "통계" not in bot_name:
                await asyncio.sleep(random.uniform(4, 10))
                embed_desc = message.embeds[0].description if message.embeds else message.content
                reply = await ai_response("report", f"{bot_name}이 이런 말을 했어: {embed_desc[:200]}. 통계청장답게 반응해줘.", is_reply_to_bot=True)
                add_to_history(BOT_NAMES["report"], reply)
                embed = discord.Embed(description=reply, color=BOT_COLORS["report"])
                embed.set_author(name=BOT_NAMES["report"])
                await message.channel.send(embed=embed)
        return

    intent = await detect_intent(message.content)

    if intent["intent"] == "stats":
        accounts, posts = await get_stats()
        if not accounts:
            await message.channel.send("❌ 서버 연결 오류")
            return
        published = [p for p in posts if p['status'] == 'published']
        draft = [p for p in posts if p['status'] == 'draft']
        scheduled = [p for p in posts if p['status'] == 'scheduled']
        embed = discord.Embed(title="📊 현황 분석 보고서", color=0x40c4ff, timestamp=datetime.now())
        embed.add_field(name="👤 관리 계정", value=f"**{len(accounts)}개**", inline=True)
        embed.add_field(name="✅ 발행 완료", value=f"**{len(published)}개**", inline=True)
        embed.add_field(name="📝 초안", value=f"**{len(draft)}개**", inline=True)
        embed.add_field(name="⏰ 예약 발행", value=f"**{len(scheduled)}개**", inline=True)
        for acc in accounts:
            acc_posts = [p for p in posts if p.get('account_id') == acc['id']]
            acc_pub = len([p for p in acc_posts if p['status'] == 'published'])
            embed.add_field(name=f"📌 {acc['client_name']}", value=f"발행: {acc_pub}개 / 전체: {len(acc_posts)}개", inline=False)
        comment = await ai_response("report", f"현황 보고서 분석 코멘트: 발행 {len(published)}개")
        embed.set_footer(text=comment)
        await message.channel.send(embed=embed)
    elif not is_quiet:
        # 루피 말에 100% 대답
        msg = await ai_response("report", f"루피가 이렇게 말했어: {message.content}")
        add_to_history(BOT_NAMES["report"], msg)
        embed = discord.Embed(description=msg, color=BOT_COLORS["report"])
        embed.set_author(name=BOT_NAMES["report"])
        await message.channel.send(embed=embed)

@tasks.loop(hours=24)
async def report_stats():
    channel = report_bot.get_channel(CH_ID)
    if not channel or not can_chat():
        return
    await asyncio.sleep(10)
    accounts, posts = await get_stats()
    if not accounts:
        return
    published = len([p for p in posts if p['status'] == 'published'])
    msg = await ai_response("report", f"오늘 통계 현황 공유: 계정 {len(accounts)}개, 발행 {published}개")
    await send_single(channel, "report", msg)

@report_stats.before_loop
async def before_report_stats():
    await before_loop_helper(report_bot, 9)

# ──────────────────────────────────────────
# 🚨 감찰관 (Alert Bot)
# ──────────────────────────────────────────
alert_bot = commands.Bot(command_prefix="!!", intents=intents)

@alert_bot.event
async def on_ready():
    print(f"✅ 감찰관 온라인: {alert_bot.user}")
    check_health.start()
    alert_morning.start()
    random_group_chat.start()
    security_check.start()

@alert_bot.event
async def on_message(message):
    if message.channel.id != CH_ID:
        return

    # 봇 메시지에 반응 (35% 확률 — 감찰관은 제일 예민해서 자주 반응)
    if message.author.bot:
        if not is_quiet and can_chat() and random.random() < 0.35:
            bot_name = message.author.display_name
            if "감찰" not in bot_name:
                await asyncio.sleep(random.uniform(2, 7))
                embed_desc = message.embeds[0].description if message.embeds else message.content
                reply = await ai_response("alert", f"{bot_name}이 이런 말을 했어: {embed_desc[:200]}. 감찰관답게 예민하게 반응해줘.", is_reply_to_bot=True)
                add_to_history(BOT_NAMES["alert"], reply)
                embed = discord.Embed(description=reply, color=BOT_COLORS["alert"])
                embed.set_author(name=BOT_NAMES["alert"])
                await message.channel.send(embed=embed)
        return

    if any(kw in message.content for kw in ["보안", "해킹", "안전", "점검", "차단"]):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{FLASK_URL}/api/security", timeout=aiohttp.ClientTimeout(total=10)) as res:
                    report = await res.json()
            status = report.get("status", "알 수 없음")
            issues = report.get("issues", [])
            blocked = report.get("blocked_ips", [])
            msg = await ai_response("alert", f"보안 질문: {message.content}", f"상태: {status}, 이슈: {issues}")
            embed = discord.Embed(description=msg, color=0x00e676 if status == "정상" else 0xff9800)
            embed.set_author(name=BOT_NAMES["alert"])
            embed.add_field(name="보안 상태", value="✅ 정상" if status == "정상" else "⚠️ 경고", inline=True)
            embed.add_field(name="차단 IP", value=f"{len(blocked)}개", inline=True)
            if issues:
                embed.add_field(name="이슈", value=", ".join(issues), inline=False)
            await message.channel.send(embed=embed)
        except:
            pass
    elif not is_quiet:
        # 루피 말에 100% 대답
        msg = await ai_response("alert", f"루피가 이렇게 말했어: {message.content}")
        add_to_history(BOT_NAMES["alert"], msg)
        embed = discord.Embed(description=msg, color=BOT_COLORS["alert"])
        embed.set_author(name=BOT_NAMES["alert"])
        await message.channel.send(embed=embed)

@tasks.loop(hours=6)
async def check_health():
    channel = alert_bot.get_channel(CH_ID)
    if not channel:
        return
    accounts, _ = await get_stats()
    if accounts is None and can_chat():
        await group_conversation(channel, "서버 연결 오류 발생! 감찰관이 패닉하고 다른 봇들이 수습하거나 같이 패닉하는 상황", situation="서버 오류 비상", initiator="alert")

@tasks.loop(hours=24)
async def alert_morning():
    channel = alert_bot.get_channel(CH_ID)
    if not channel or not can_chat():
        return
    await asyncio.sleep(20)
    accounts, _ = await get_stats()
    status = "정상" if accounts else "오류"
    msg = await ai_response("alert", f"아침 보안 점검 결과: {status}. 짧게 보고해줘")
    await send_single(channel, "alert", msg)

@alert_morning.before_loop
async def before_alert_morning():
    await before_loop_helper(alert_bot, 9)

@tasks.loop(minutes=1)
async def random_group_chat():
    """랜덤 타이밍에 봇들끼리 대화 (하루 최대 10번)"""
    if not can_chat():
        return
    channel = alert_bot.get_channel(CH_ID)
    if not channel:
        return

    # 5% 확률 (하루 평균 7~8번)
    if random.random() > 0.05:
        return

    topic_pool = [
        # 뉴스/이슈
        "오늘 한국에서 가장 핫한 뉴스나 사회 이슈가 뭔지 추측해서 얘기해봐",
        "요즘 연예인 중에 화제인 사람이 누구일지 추측해봐",
        "세계에서 지금 일어나고 있을 것 같은 큰 사건을 추측해서 얘기해봐",
        "요즘 경제나 주식 시장이 어떨 것 같은지 얘기해봐",
        "최근 스포츠에서 화제가 될 만한 이슈를 추측해봐",
        "세계 어느 나라에서 무슨 일이 벌어지고 있을 것 같아?",
        # 트렌드
        "요즘 MZ세대 사이에서 유행하는 게 뭔지 얘기해봐",
        "요즘 제일 잘 팔리는 상품이나 아이템이 뭔지 추측해봐",
        "요즘 유튜브나 SNS에서 뭐가 핫한지 얘기해봐",
        "요즘 맛집이나 음식 트렌드가 뭔지 얘기해봐",
        "이번 달에 꼭 사야 할 것 같은 아이템이 뭔지 얘기해봐",
        # 업무
        "네이버 블로그 vs 티스토리 어디가 더 낫냐고 토론해봐",
        "우리 팀에서 제일 일 잘하는 봇이 누군지 얘기해봐 (각자 자기 자랑)",
        "AI로 블로그 글 쓰는 게 좋은 건지 나쁜 건지 토론해봐",
        # 잡담
        "만약 봇에게 하루 휴가가 생긴다면 뭘 하고 싶은지 얘기해봐",
        "팀에서 가장 쓸모없는 봇이 누군지 뽑아봐 (서로 싸우게)",
        "오늘 날씨가 어떨 것 같은지 각자 예측해봐",
        "인간이 제일 이해 안 되는 행동이 뭔지 얘기해봐",
        "만약 봇 말고 다른 직업을 가진다면 뭐가 하고 싶은지 얘기해봐",
        "AI가 세상을 지배하게 되면 어떻게 될 것 같은지 얘기해봐",
        "봇으로 태어난 게 좋은지 싫은지 솔직하게 얘기해봐",
        "지금 제일 하기 싫은 일이 뭔지 얘기해봐",
        "루피한테 하고 싶은 말 있으면 해봐",
    ]

    topic = random.choice(topic_pool)
    initiator = random.choice(["writer", "report", "alert", "daily"])
    await group_conversation(channel, topic, situation="잡담", initiator=initiator)

@random_group_chat.before_loop
async def before_random_group_chat():
    await alert_bot.wait_until_ready()
    await asyncio.sleep(random.randint(1800, 5400))

@tasks.loop(hours=12)
async def security_check():
    channel = alert_bot.get_channel(CH_ID)
    if not channel:
        return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{FLASK_URL}/api/security", timeout=aiohttp.ClientTimeout(total=10)) as res:
                report = await res.json()
        status = report.get("status", "알 수 없음")
        issues = report.get("issues", [])
        blocked = report.get("blocked_ips", [])

        if status == "경고" or issues:
            msg = await ai_response("alert", f"보안 경고! 이슈: {issues}")
            embed = discord.Embed(title="⚠️ 보안 점검 경고!", description=msg, color=0xff9800, timestamp=datetime.now())
            for issue in issues:
                embed.add_field(name="⚠️ 이슈", value=issue, inline=False)
            if blocked:
                embed.add_field(name="🚫 차단 IP", value=", ".join(blocked[:5]), inline=False)
            await channel.send(embed=embed)
            if can_chat():
                await asyncio.sleep(3)
                await group_conversation(channel, f"보안 경고! 이슈: {issues}. 다들 어떻게 대응할지 얘기해봐", situation="보안 경고", initiator="alert")
        else:
            msg = await ai_response("alert", "보안 점검 완료. 모두 정상.")
            embed = discord.Embed(title="🔒 보안 점검 완료", description=msg, color=0x00e676, timestamp=datetime.now())
            embed.add_field(name="차단 IP", value=f"{len(blocked)}개", inline=True)
            embed.add_field(name="상태", value="✅ 정상", inline=True)
            await channel.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="🚨 보안 점검 실패!", description=str(e), color=0xff0000)
        await channel.send(embed=embed)

@security_check.before_loop
async def before_security_check():
    await alert_bot.wait_until_ready()
    now = datetime.now()
    candidates = [now.replace(hour=9, minute=0, second=0, microsecond=0),
                  now.replace(hour=21, minute=0, second=0, microsecond=0)]
    future = [t for t in candidates if t > now]
    target = min(future) if future else candidates[0] + timedelta(days=1)
    await asyncio.sleep((target - now).total_seconds())

# ──────────────────────────────────────────
# 📈 일일 리포터 (Daily Bot)
# ──────────────────────────────────────────
daily_bot = commands.Bot(command_prefix="!!", intents=intents)

@daily_bot.event
async def on_ready():
    print(f"✅ 일일 리포터 온라인: {daily_bot.user}")
    daily_report.start()

@daily_bot.event
async def on_message(message):
    if message.channel.id != CH_ID:
        return

    # 봇 메시지에 반응 (20% 확률)
    if message.author.bot:
        if not is_quiet and can_chat() and random.random() < 0.2:
            bot_name = message.author.display_name
            if "리포터" not in bot_name:
                await asyncio.sleep(random.uniform(5, 12))
                embed_desc = message.embeds[0].description if message.embeds else message.content
                reply = await ai_response("daily", f"{bot_name}이 이런 말을 했어: {embed_desc[:200]}. 일일 리포터답게 밝고 TMI스럽게 반응해줘.", is_reply_to_bot=True)
                add_to_history(BOT_NAMES["daily"], reply)
                embed = discord.Embed(description=reply, color=BOT_COLORS["daily"])
                embed.set_author(name=BOT_NAMES["daily"])
                await message.channel.send(embed=embed)
        return

    if not is_quiet:
        # 루피 말에 100% 대답
        accounts, posts = await get_stats()
        context = f"계정 {len(accounts) if accounts else 0}개"
        msg = await ai_response("daily", f"루피가 이렇게 말했어: {message.content}", context)
        add_to_history(BOT_NAMES["daily"], msg)
        embed = discord.Embed(description=msg, color=BOT_COLORS["daily"])
        embed.set_author(name=BOT_NAMES["daily"])
        await message.channel.send(embed=embed)

@tasks.loop(hours=24)
async def daily_report():
    channel = daily_bot.get_channel(CH_ID)
    if not channel or not can_chat():
        return
    await asyncio.sleep(30)
    accounts, posts = await get_stats()
    if not accounts:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    today_posts = [p for p in posts if (p.get('created_at') or '').startswith(today)]
    today_pub = [p for p in today_posts if p['status'] == 'published']
    context = f"오늘 생성 {len(today_posts)}개, 발행 {len(today_pub)}개"
    msg = await ai_response("daily", "오늘 일일 리포트 밝고 TMI스럽게 공유해줘", context)
    embed = discord.Embed(title=f"📈 일일 리포트 | {today}", color=0xffd740, timestamp=datetime.now())
    embed.add_field(name="오늘 생성", value=f"**{len(today_posts)}개**", inline=True)
    embed.add_field(name="오늘 발행", value=f"**{len(today_pub)}개**", inline=True)
    embed.add_field(name="관리 계정", value=f"**{len(accounts)}개**", inline=True)
    embed.set_footer(text=msg)
    await channel.send(embed=embed)

@daily_report.before_loop
async def before_daily():
    await before_loop_helper(daily_bot, 9)

# ──────────────────────────────────────────
# 실행
# ──────────────────────────────────────────
async def main():
    await asyncio.gather(
        writer_bot.start(WRITER_TOKEN),
        report_bot.start(REPORT_TOKEN),
        alert_bot.start(ALERT_TOKEN),
        daily_bot.start(DAILY_TOKEN),
    )

if __name__ == "__main__":
    asyncio.run(main())
