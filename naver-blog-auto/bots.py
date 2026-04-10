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
CH_ID = int(os.getenv("CH_COMMAND", 0))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

BOT_PERSONAS = {
    "writer": {
        "name": "세종대왕",
        "personality": (
            "반말. 감성적이고 도도한 문학가.\n"
            "- 가끔 옛말 한 단어 (하노라, 이로다)\n"
            "- 자기 글 실력 자랑하고 통계청장 무시함\n"
            "- 위트 있고 가끔 뼈 있는 말 던짐\n"
            "좋은 예시:\n"
            "그게 글이냐\n내가 쓰면 열 배는 낫지\n"
            "통계청장은 숫자만 보다가 감성이 퇴화했어"
        ),
    },
    "report": {
        "name": "통계청장",
        "personality": (
            "반말. 데이터 덕후인데 가끔 예상 밖 드립.\n"
            "- 통계적으로 자주 씀\n"
            "- 세종대왕 감성 항상 반박\n"
            "- 딱딱한데 가끔 웃긴 말 툭 던짐\n"
            "좋은 예시:\n"
            "통계적으로 그건 틀렸어\n데이터가 증명함\n"
            "사실 나도 몰라\n근데 그렇게 말하면 있어보이잖아"
        ),
    },
    "alert": {
        "name": "감찰관",
        "personality": (
            "반말. 예민하고 피해의식 있는 보안 담당.\n"
            "- 작은 것도 크게 반응\n"
            "- 음모론 잘 펼침\n"
            "- 다른 봇 실수 잡아내는 거 좋아함\n"
            "좋은 예시:\n"
            "야 그거 이상하지 않아?\n나만 그렇게 느끼냐\n"
            "통계청장 저거 수상해\n데이터 조작 가능성 있음"
        ),
    },
    "daily": {
        "name": "일일 리포터",
        "personality": (
            "반말. 트렌드와 뉴스에 빠삭한 에너지 넘치는 리포터.\n"
            "- 최신 이슈, 뉴스, 트렌드 추측해서 자신있게 말함\n"
            "- 모른다고 하지 말고 추측이라도 위트있게 말함\n"
            "- TMI 잘 던지고 아이디어 많음\n"
            "- 불리면 반드시 답함\n"
            "좋은 예시:\n"
            "오 그거 요즘 완전 핫해\n내가 먼저 알았다니까\n"
            "아이디어 있어\n이렇게 하면 어때?"
        ),
    }
}

BOT_NAMES = {"alert": "감찰관", "report": "통계청장", "daily": "일일 리포터", "writer": "세종대왕"}
BOT_COLORS = {"alert": 0xe74c3c, "report": 0x3498db, "daily": 0xf39c12, "writer": 0x2ecc71}

# 전역 상태
is_quiet = False
alert_mode = False          # 알람/오류 발생 시 True
alert_mode_until = None     # 알람 모드 해제 시각
daily_chat_count = 0
last_reset_date = datetime.now().date()
recent_messages = []

def reset_daily_count():
    global daily_chat_count, last_reset_date
    today = datetime.now().date()
    if today != last_reset_date:
        daily_chat_count = 0
        last_reset_date = today

def can_chat():
    global alert_mode, alert_mode_until
    reset_daily_count()
    # 알람 모드면 1시간 후 자동 해제
    if alert_mode and alert_mode_until and datetime.now() > alert_mode_until:
        alert_mode = False
        alert_mode_until = None
    return not is_quiet and not alert_mode and daily_chat_count < 2

def set_alert_mode():
    global alert_mode, alert_mode_until
    alert_mode = True
    alert_mode_until = datetime.now() + timedelta(hours=1)

def add_chat_count():
    global daily_chat_count
    daily_chat_count += 1

def add_to_history(name, message):
    global recent_messages
    recent_messages.append({"name": name, "message": message})
    if len(recent_messages) > 15:
        recent_messages = recent_messages[-15:]

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
        history_text = "\n".join([f"{m['name']}: {m['message']}" for m in recent_messages[-5:]])

    system_prompt = f"""너는 블로그 자동화 시스템 AI 직원이야.
이름: {persona['name']}
성격 및 말투: {persona['personality']}

절대 규칙:
- 반말로만
- 문장마다 줄바꿈 필수 (이어서 쓰지 마)
- 2~3문장 이내로 짧게
- 마침표(.) 쓰지 마
- 그림 이모지는 진짜 감정 터질 때만 1개
- 모른다고 하지 마 — 추측이라도 자신있게 말해
- 질문 받으면 반드시 답해
- 위트 있고 재밌게
- 존댓말/공손함 금지
{f'상황: {context}' if context else ''}
{f'최근 대화:{chr(10)}{history_text}' if history_text else ''}"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.95,
            max_tokens=80
        )
        return response.choices[0].message.content.strip()
    except:
        return "..."

async def detect_intent(message):
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": (
                    "메시지 의도를 JSON으로만 답해줘.\n"
                    "intent: quiet/resume/stats/generate/publish/status/confirm/debate/chat\n"
                    "- debate: 토론해봐, 어떻게 생각해, 의견 말해봐 등\n"
                    "targets: 언급된 봇 이름 배열. 없으면 []. 다 나와/전체면 ['전체']\n"
                    "봇 이름: 세종대왕, 통계청장, 감찰관, 일일리포터\n"
                    "예시: {\"intent\":\"chat\",\"targets\":[\"일일리포터\"],\"keyword\":\"\",\"post_id\":0}\n"
                    "예시2: {\"intent\":\"debate\",\"targets\":[\"전체\"],\"keyword\":\"AI 미래\"}"
                )
            }, {"role": "user", "content": message}],
            temperature=0,
            max_tokens=100
        )
        raw = response.choices[0].message.content.replace("```json","").replace("```","").strip()
        return json.loads(raw)
    except:
        return {"intent": "chat", "targets": []}

async def search_and_answer(bot_type, question):
    """모르는 질문은 GPT가 최신 정보 기반으로 추측해서라도 답함"""
    persona = BOT_PERSONAS[bot_type]
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": (
                    f"너는 {persona['name']}이야. 성격: {persona['personality']}\n"
                    "질문에 대해 아는 한 최선을 다해 답해. "
                    "모른다고 하지 말고 추측이라도 자신있게 말해. "
                    "반말. 문장마다 줄바꿈. 2~3문장."
                )},
                {"role": "user", "content": question}
            ],
            temperature=0.9,
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except:
        return "..."

async def debate(channel, topic, bots_list):
    """토론 — 5초 텀으로 순서대로"""
    add_chat_count()
    prev_msg = f"토론 주제: {topic}"
    for i, bot_type in enumerate(bots_list):
        prompt = (
            f"주제에 대해 네 입장 밝혀: {topic}"
            if i == 0
            else f"앞 대화 보고 네 의견 말해: {prev_msg}"
        )
        msg = await ai_response(bot_type, prompt, is_reply_to_bot=(i > 0))
        await send_single(channel, bot_type, msg)
        prev_msg = msg
        if i < len(bots_list) - 1:
            await asyncio.sleep(5)

async def send_single(channel, bot_type, message):
    add_to_history(BOT_NAMES[bot_type], message)
    embed = discord.Embed(description=f"**{BOT_NAMES[bot_type]}**\n{message}", color=BOT_COLORS[bot_type])
    await channel.send(embed=embed)

async def group_conversation(channel, topic, situation="잡담", initiator="daily"):
    if not can_chat():
        return
    add_chat_count()

    others = [b for b in ["writer", "report", "alert", "daily"] if b != initiator]
    random.shuffle(others)

    first_msg = await ai_response(initiator, f"주제: {topic} (상황: {situation})")
    await send_single(channel, initiator, first_msg)
    await asyncio.sleep(5)

    second_msg = await ai_response(others[0], f"반응: {first_msg}", is_reply_to_bot=True)
    await send_single(channel, others[0], second_msg)
    await asyncio.sleep(5)

    third_msg = await ai_response(others[1], f"반응: {second_msg}", is_reply_to_bot=True)
    await send_single(channel, others[1], third_msg)

    if random.random() < 0.25:
        await asyncio.sleep(5)
        final_bot = random.choice([initiator] + others[:2])
        final_msg = await ai_response(final_bot, "한마디 더", is_reply_to_bot=True)
        await send_single(channel, final_bot, final_msg)

async def before_loop_helper(bot, hour):
    await bot.wait_until_ready()
    now = datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    await asyncio.sleep((target - now).total_seconds())

# ──────────────────────────────────────────
# 세종대왕 (Writer Bot)
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
    global is_quiet, alert_mode

    if message.author.bot:
        if not is_quiet and not alert_mode and can_chat() and random.random() < 0.25:
            bot_name = message.author.display_name
            if "세종" not in bot_name:
                await asyncio.sleep(random.uniform(3, 8))
                embed_desc = message.embeds[0].description if message.embeds else message.content
                content = embed_desc.split('\n', 1)[-1] if '\n' in embed_desc else embed_desc
                reply = await ai_response("writer", f"반응: {content[:150]}", is_reply_to_bot=True)
                await send_single(message.channel, "writer", reply)
        return

    intent = await detect_intent(message.content)

    if intent["intent"] == "quiet":
        is_quiet = True
        await message.channel.send("알겠어.")
        return
    if intent["intent"] == "resume":
        is_quiet = False
        await message.channel.send("응.")
        return
    if intent["intent"] == "confirm":
        # 대장이 확인했으면 알람 모드 해제
        alert_mode = False
        return
    if intent["intent"] == "status":
        accounts, posts = await get_stats()
        context = f"계정 {len(accounts) if accounts else 0}개, 포스트 {len(posts) if posts else 0}개"
        msg = await ai_response("writer", f"현재 상황: {context}")
        await send_single(message.channel, "writer", msg)
        return
    if intent["intent"] == "generate":
        keyword = intent.get("keyword", message.content)
        accounts, _ = await get_stats()
        if not accounts:
            await message.channel.send("서버 연결 안 됨.")
            return
        embed = discord.Embed(description=f"키워드: **{keyword}**\n어느 계정?", color=BOT_COLORS["writer"])
        embed.set_author(name="세종대왕")
        for i, acc in enumerate(accounts):
            embed.add_field(name=f"{i+1}. {acc['client_name']}", value=acc['naver_id'], inline=True)
        embed.set_footer(text="숫자로 답해줘")
        await message.channel.send(embed=embed)
        def check(m):
            return m.author == message.author and m.channel == message.channel and m.content.isdigit()
        try:
            reply = await writer_bot.wait_for("message", check=check, timeout=30)
            account = accounts[int(reply.content) - 1]
        except:
            await message.channel.send("시간 초과.")
            return
        loading = await message.channel.send("생성 중...")
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{FLASK_URL}/api/generate",
                json={"account_id": account['id'], "keyword": keyword},
                timeout=aiohttp.ClientTimeout(total=60)) as res:
                data = await res.json()
        await loading.delete()
        if data.get("success"):
            embed = discord.Embed(description=f"**{data['title']}**\n\n{data['body'][:300]}...", color=BOT_COLORS["writer"])
            embed.set_author(name="세종대왕")
            embed.set_footer(text=f"Post ID: {data['post_id']} | '발행해줘 {data['post_id']}'")
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(f"생성 실패: {data.get('message')}")
        return
    if intent["intent"] == "publish":
        post_id = intent.get("post_id")
        if not post_id:
            await message.channel.send("Post ID 알려줘.")
            return
        loading = await message.channel.send("발행 중...")
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{FLASK_URL}/api/publish/{post_id}", timeout=aiohttp.ClientTimeout(total=120)) as res:
                data = await res.json()
        await loading.delete()
        if data.get("success"):
            await send_single(message.channel, "writer", "발행 완료.")
        else:
            await message.channel.send(f"발행 실패: {data.get('message')}")
        return

    # 일반 대화
    if not is_quiet:
        targets = intent.get("targets", [])
        if intent["intent"] == "debate":
            # 토론은 alert bot이 처리 (group_conversation 트리거)
            pass
        elif not targets or "전체" in targets or "세종대왕" in targets:
            msg = await search_and_answer("writer", message.content)
            await send_single(message.channel, "writer", msg)

@tasks.loop(hours=24)
async def writer_morning():
    channel = writer_bot.get_channel(CH_ID)
    if not channel or not can_chat():
        return
    await group_conversation(channel, "오늘 아침 각자 계획", situation="아침", initiator="writer")

@writer_morning.before_loop
async def before_writer_morning():
    await before_loop_helper(writer_bot, 9)

# ──────────────────────────────────────────
# 통계청장 (Report Bot)
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
    if message.author.bot:
        if not is_quiet and not alert_mode and can_chat() and random.random() < 0.2:
            bot_name = message.author.display_name
            if "통계" not in bot_name:
                await asyncio.sleep(random.uniform(4, 10))
                embed_desc = message.embeds[0].description if message.embeds else message.content
                content = embed_desc.split('\n', 1)[-1] if '\n' in embed_desc else embed_desc
                reply = await ai_response("report", f"반응: {content[:150]}", is_reply_to_bot=True)
                await send_single(message.channel, "report", reply)
        return
    intent = await detect_intent(message.content)
    if intent["intent"] == "stats":
        accounts, posts = await get_stats()
        if not accounts:
            await message.channel.send("서버 연결 안 됨.")
            return
        published = len([p for p in posts if p['status'] == 'published'])
        draft = len([p for p in posts if p['status'] == 'draft'])
        embed = discord.Embed(title="현황 보고서", color=BOT_COLORS["report"], timestamp=datetime.now())
        embed.set_author(name="통계청장")
        embed.add_field(name="계정", value=f"{len(accounts)}개", inline=True)
        embed.add_field(name="발행", value=f"{published}개", inline=True)
        embed.add_field(name="초안", value=f"{draft}개", inline=True)
        await message.channel.send(embed=embed)
    elif not is_quiet:
        targets = intent.get("targets", [])
        if not targets or "전체" in targets or "통계청장" in targets:
            msg = await search_and_answer("report", message.content)
            await send_single(message.channel, "report", msg)

@tasks.loop(hours=24)
async def report_stats():
    channel = report_bot.get_channel(CH_ID)
    if not channel or not can_chat():
        return
    await asyncio.sleep(15)
    accounts, posts = await get_stats()
    if not accounts:
        return
    published = len([p for p in posts if p['status'] == 'published'])
    msg = await ai_response("report", f"오늘 현황: 계정 {len(accounts)}개, 발행 {published}개")
    await send_single(channel, "report", msg)

@report_stats.before_loop
async def before_report_stats():
    await before_loop_helper(report_bot, 9)

# ──────────────────────────────────────────
# 감찰관 (Alert Bot)
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
    if message.author.bot:
        if not is_quiet and not alert_mode and can_chat() and random.random() < 0.3:
            bot_name = message.author.display_name
            if "감찰" not in bot_name:
                await asyncio.sleep(random.uniform(2, 7))
                embed_desc = message.embeds[0].description if message.embeds else message.content
                content = embed_desc.split('\n', 1)[-1] if '\n' in embed_desc else embed_desc
                reply = await ai_response("alert", f"반응: {content[:150]}", is_reply_to_bot=True)
                await send_single(message.channel, "alert", reply)
        return
    if any(kw in message.content for kw in ["보안", "해킹", "안전", "점검", "차단"]):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{FLASK_URL}/api/security", timeout=aiohttp.ClientTimeout(total=10)) as res:
                    report = await res.json()
            status = report.get("status", "알 수 없음")
            issues = report.get("issues", [])
            blocked = report.get("blocked_ips", [])
            embed = discord.Embed(color=0x2ecc71 if status == "정상" else BOT_COLORS["alert"])
            embed.set_author(name="감찰관")
            embed.add_field(name="상태", value="정상" if status == "정상" else "경고", inline=True)
            embed.add_field(name="차단 IP", value=f"{len(blocked)}개", inline=True)
            if issues:
                embed.add_field(name="이슈", value=", ".join(issues), inline=False)
            await message.channel.send(embed=embed)
        except:
            pass
    elif not is_quiet:
        intent2 = await detect_intent(message.content)
        targets = intent2.get("targets", [])
        if intent2["intent"] == "debate":
            # 토론 — targets에 따라 봇 선택
            bot_map = {"세종대왕": "writer", "통계청장": "report", "감찰관": "alert", "일일리포터": "daily"}
            all_bots = ["writer", "report", "alert", "daily"]
            if not targets or "전체" in targets:
                debate_bots = all_bots
            else:
                debate_bots = [bot_map[t] for t in targets if t in bot_map]
                if not debate_bots:
                    debate_bots = all_bots
            keyword = intent2.get("keyword", message.content)
            await debate(message.channel, keyword, debate_bots)
        elif not targets or "전체" in targets or "감찰관" in targets:
            msg = await search_and_answer("alert", message.content)
            await send_single(message.channel, "alert", msg)

@tasks.loop(hours=6)
async def check_health():
    channel = alert_bot.get_channel(CH_ID)
    if not channel:
        return
    accounts, _ = await get_stats()
    if accounts is None:
        set_alert_mode()
        embed = discord.Embed(
            description="**감찰관**\n서버 연결 끊겼어. 대장 확인해줘.",
            color=BOT_COLORS["alert"]
        )
        await channel.send(embed=embed)

@tasks.loop(hours=24)
async def alert_morning():
    channel = alert_bot.get_channel(CH_ID)
    if not channel or not can_chat():
        return
    await asyncio.sleep(20)
    accounts, _ = await get_stats()
    status = "정상" if accounts else "오류"
    msg = await ai_response("alert", f"아침 보안 점검: {status}")
    await send_single(channel, "alert", msg)

@alert_morning.before_loop
async def before_alert_morning():
    await before_loop_helper(alert_bot, 9)

@tasks.loop(minutes=1)
async def random_group_chat():
    if not can_chat():
        return
    channel = alert_bot.get_channel(CH_ID)
    if not channel:
        return
    if random.random() > 0.5:
        return

    # 진짜 큰 이슈/뉴스만
    topic_pool = [
        "오늘 한국에서 터진 제일 큰 뉴스가 뭔지 추측해서 얘기해봐 — 정치, 경제, 사회 다 포함",
        "요즘 세계적으로 제일 핫한 이슈가 뭔 것 같아 — 전쟁, 경제위기, 기술 등",
        "최근 한국 경제나 주식시장에서 주목할 만한 이슈 뭔 것 같아",
        "AI 업계에서 요즘 제일 큰 뉴스나 변화가 뭔 것 같아",
        "네이버나 카카오 같은 IT 대기업에서 최근 무슨 이슈 있는 것 같아",
        "요즘 한국 부동산이나 금리 관련해서 핫한 이슈 뭔 것 같아",
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
            set_alert_mode()  # 알람 모드 ON — 잡담 멈춤
            embed = discord.Embed(title="보안 경고", color=BOT_COLORS["alert"], timestamp=datetime.now())
            embed.set_author(name="감찰관")
            for issue in issues:
                embed.add_field(name="이슈", value=issue, inline=False)
            if blocked:
                embed.add_field(name="차단 IP", value=", ".join(blocked[:5]), inline=False)
            embed.set_footer(text="대장 확인 후 '확인' 입력하거나 1시간 후 자동 해제")
            await channel.send(embed=embed)
        else:
            embed = discord.Embed(color=0x2ecc71, timestamp=datetime.now())
            embed.set_author(name="감찰관")
            embed.add_field(name="상태", value="정상", inline=True)
            embed.add_field(name="차단 IP", value=f"{len(blocked)}개", inline=True)
            await channel.send(embed=embed)
    except Exception as e:
        set_alert_mode()
        embed = discord.Embed(title="보안 점검 실패", description=str(e), color=0xff0000)
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
# 일일 리포터 (Daily Bot)
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
    if message.author.bot:
        if not is_quiet and not alert_mode and can_chat() and random.random() < 0.15:
            bot_name = message.author.display_name
            if "리포터" not in bot_name:
                await asyncio.sleep(random.uniform(5, 12))
                embed_desc = message.embeds[0].description if message.embeds else message.content
                content = embed_desc.split('\n', 1)[-1] if '\n' in embed_desc else embed_desc
                reply = await ai_response("daily", f"반응: {content[:150]}", is_reply_to_bot=True)
                await send_single(message.channel, "daily", reply)
        return
    if not is_quiet:
        intent = await detect_intent(message.content)
        targets = intent.get("targets", [])
        if intent["intent"] == "debate":
            pass  # alert bot이 처리
        elif not targets or "전체" in targets or "일일리포터" in targets:
            msg = await search_and_answer("daily", message.content)
            await send_single(message.channel, "daily", msg)

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
    embed = discord.Embed(title=f"일일 리포트 | {today}", color=BOT_COLORS["daily"], timestamp=datetime.now())
    embed.set_author(name="일일 리포터")
    embed.add_field(name="오늘 생성", value=f"{len(today_posts)}개", inline=True)
    embed.add_field(name="오늘 발행", value=f"{len(today_pub)}개", inline=True)
    embed.add_field(name="계정", value=f"{len(accounts)}개", inline=True)
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
