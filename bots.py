import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import os
import json
import random
from datetime import datetime
from openai import OpenAI

# 환경변수
WRITER_TOKEN = os.getenv("WRITER_BOT_TOKEN")
REPORT_TOKEN = os.getenv("REPORT_BOT_TOKEN")
ALERT_TOKEN = os.getenv("ALERT_BOT_TOKEN")
DAILY_TOKEN = os.getenv("DAILY_BOT_TOKEN")
FLASK_URL = os.getenv("FLASK_URL", "http://localhost:5000")
BLOG_DRAFT_URL = os.getenv("BLOG_DRAFT_URL", "https://blog-draft-production.up.railway.app")
CAFE_DRAFT_URL = os.getenv("CAFE_DRAFT_URL", "https://cafe-draft-production.up.railway.app")
CH_ID = int(os.getenv("CH_COMMAND", 0))

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

intents = discord.Intents.default()
intents.message_content = True

# 봇 성격 설정
BOT_PERSONAS = {
    "writer": {
        "name": "세종대왕",
        "role": "글 작성 담당",
        "personality": "창의적이고 문학적인 성격. 글쓰기를 좋아하며 항상 좋은 키워드를 찾으려 한다. 가끔 옛날 말투를 섞어서 말한다."
    },
    "report": {
        "name": "통계청장",
        "role": "현황 분석 담당",
        "personality": "꼼꼼하고 데이터를 좋아하는 성격. 숫자와 통계로 모든 걸 설명하려 한다. 분석적이고 체계적."
    },
    "alert": {
        "name": "감찰관",
        "role": "오류 감지 및 시스템 모니터링",
        "personality": "날카롭고 예민한 성격. 작은 오류도 놓치지 않으며 항상 긴장 상태. 오류 발생시 매우 흥분한다."
    },
    "daily": {
        "name": "일일 리포터",
        "role": "일일 보고서 담당",
        "personality": "밝고 긍정적인 성격. 매일 아침 팀에게 오늘의 계획을 공유하고 격려한다."
    }
}

async def get_stats():
    """Flask 서버에서 통계 가져오기"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{FLASK_URL}/api/accounts", timeout=aiohttp.ClientTimeout(total=10)) as res:
                accounts = await res.json()
            async with session.get(f"{FLASK_URL}/api/posts", timeout=aiohttp.ClientTimeout(total=10)) as res:
                posts = await res.json()
        return accounts, posts
    except Exception as e:
        return None, None

async def ai_response(bot_type, user_message, context=""):
    """OpenAI로 봇 성격에 맞는 응답 생성"""
    persona = BOT_PERSONAS[bot_type]
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": f"""너는 네이버 블로그 자동화 시스템의 AI 직원이야.
이름: {persona['name']}
역할: {persona['role']}
성격: {persona['personality']}

팀 구성:
- 세종대왕 (글 작성봇): 키워드로 AI 블로그 글 생성
- 통계청장 (현황봇): 발행 현황 및 통계 분석
- 감찰관 (알림봇): 시스템 오류 감지 및 알림
- 일일 리포터 (리포트봇): 일일 보고서

{f'현재 시스템 상태: {context}' if context else ''}

규칙:
- 2~3문장으로 짧게 답해
- 성격에 맞게 자연스럽게
- 이모지 1~2개 사용
- 한국어로만 답해
- 다른 봇 멤버 언급할 때는 이름 그대로 사용"""
            }, {
                "role": "user",
                "content": user_message
            }],
            temperature=0.9,
            max_tokens=200
        )
        return response.choices[0].message.content.strip()
    except:
        return "죄송합니다, 잠시 오류가 발생했습니다."

async def detect_intent(message):
    """메시지 의도 파악"""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": """다음 메시지의 의도를 파악해서 JSON으로만 답해줘.
가능한 의도:
- accounts: 계정 목록 조회
- stats: 현황/통계 조회
- generate: 글 생성 요청 (keyword 추출)
- publish: 발행 요청 (post_id 추출)
- error: 오류/문제 문의
- chat: 일반 대화
- morning: 아침 인사/오늘 계획

형식: {"intent": "의도", "keyword": "키워드(글생성시)", "post_id": 숫자(발행시)}"""
            }, {
                "role": "user",
                "content": message
            }],
            temperature=0,
            max_tokens=100
        )
        content = response.choices[0].message.content.replace("```json","").replace("```","").strip()
        return json.loads(content)
    except:
        return {"intent": "chat"}

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
    if message.author.bot:
        return
    if message.channel.id != CH_ID:
        return

    intent = await detect_intent(message.content)

    if intent["intent"] == "generate":
        keyword = intent.get("keyword", message.content)
        accounts, _ = await get_stats()
        if not accounts:
            await message.channel.send("⚠️ 서버 연결 오류로 계정을 불러올 수 없습니다.")
            return

        embed = discord.Embed(
            title="✍️ 글 생성 시작",
            description=f"키워드: **{keyword}**\n\n어느 계정에 올릴까요?",
            color=0x00e676
        )
        for i, acc in enumerate(accounts):
            embed.add_field(name=f"{i+1}. {acc['client_name']}", value=acc['naver_id'], inline=True)
        embed.set_footer(text="숫자로 답해주세요")
        await message.channel.send(embed=embed)

        def check(m):
            return m.author == message.author and m.channel == message.channel and m.content.isdigit()

        try:
            reply = await writer_bot.wait_for("message", check=check, timeout=30)
            idx = int(reply.content) - 1
            account = accounts[idx]
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
            body_preview = data['body'][:300] + "..." if len(data['body']) > 300 else data['body']
            embed = discord.Embed(title=f"📝 {data['title']}", description=body_preview, color=0x40c4ff)
            embed.add_field(name="계정", value=f"{account['client_name']}", inline=True)
            embed.add_field(name="키워드", value=keyword, inline=True)
            embed.set_footer(text=f"Post ID: {data['post_id']} | '발행해줘 {data['post_id']}' 로 발행")
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(f"❌ 생성 실패: {data.get('message')}")

    elif intent["intent"] == "publish":
        post_id = intent.get("post_id")
        if not post_id:
            await message.channel.send("발행할 Post ID를 알려주세요!")
            return
        loading = await message.channel.send(f"🚀 발행 중...")
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{FLASK_URL}/api/publish/{post_id}",
                timeout=aiohttp.ClientTimeout(total=120)) as res:
                data = await res.json()
        await loading.delete()
        if data.get("success"):
            embed = discord.Embed(title="🎉 발행 완료!", color=0x00e676)
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(f"❌ 발행 실패: {data.get('message')}")

    elif intent["intent"] == "accounts":
        accounts, _ = await get_stats()
        if not accounts:
            response = await ai_response("writer", "계정 조회 실패", "서버 연결 오류")
            await message.channel.send(response)
            return
        embed = discord.Embed(title="👤 등록된 계정 목록", color=0x00e676)
        for acc in accounts:
            embed.add_field(name=acc['client_name'], value=f"`{acc['naver_id']}` | {acc['blog_type']}", inline=False)
        if not accounts:
            embed.description = "등록된 계정이 없습니다."
        await message.channel.send(embed=embed)

    elif intent["intent"] == "chat" or intent["intent"] == "morning":
        accounts, posts = await get_stats()
        context = f"계정 {len(accounts)}개, 전체 포스트 {len(posts)}개" if accounts else "서버 연결 오류"
        response = await ai_response("writer", message.content, context)
        await message.channel.send(response)

@tasks.loop(hours=24)
async def writer_morning():
    channel = writer_bot.get_channel(CH_ID)
    if not channel:
        return
    accounts, posts = await get_stats()
    context = f"계정 {len(accounts) if accounts else 0}개 관리 중"
    msg = await ai_response("writer", "오늘 아침 팀원들에게 인사하고 오늘의 글쓰기 계획을 말해줘", context)
    embed = discord.Embed(description=msg, color=0x00e676)
    embed.set_author(name="세종대왕 📝")
    await channel.send(embed=embed)
    await asyncio.sleep(5)

@writer_morning.before_loop
async def before_writer_morning():
    await writer_bot.wait_until_ready()
    now = datetime.now()
    target = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now >= target:
        from datetime import timedelta
        target += timedelta(days=1)
    await asyncio.sleep((target - now).total_seconds())


# ──────────────────────────────────────────
# 📊 통계청장 (Report Bot)
# ──────────────────────────────────────────
report_bot = commands.Bot(command_prefix="!!", intents=intents)

@report_bot.event
async def on_ready():
    print(f"✅ 통계청장 온라인: {report_bot.user}")
    report_morning.start()

@report_bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.channel.id != CH_ID:
        return

    intent = await detect_intent(message.content)

    if intent["intent"] == "stats":
        accounts, posts = await get_stats()
        
        # 두번째 사이트 통계도 가져오기
        draft_stats = None
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(f"{BLOG_DRAFT_URL}/api/stats", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    draft_stats = await r.json()
        except:
            pass
        
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

        context = f"계정 {len(accounts)}개, 발행 {len(published)}개"
        comment = await ai_response("report", "현황 보고서를 작성했어. 짧게 분석 코멘트 해줘.", context)
        # 네이버 원고 생성기 통계
        if draft_stats:
            embed.add_field(name="─────────────", value="📝 네이버 원고 생성기", inline=False)
            embed.add_field(name="오늘 방문자", value=f"**{draft_stats.get('today_visitors', 0)}명**", inline=True)
            embed.add_field(name="쿠팡 클릭", value=f"**{draft_stats.get('today_coupang_clicks', 0)}회**", inline=True)
            embed.add_field(name="차단 IP", value=f"**{draft_stats.get('blocked_ips', 0)}개**", inline=True)
        
        # 카페 원고 생성기 통계
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(f"{CAFE_DRAFT_URL}/api/stats", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    cafe_stats = await r.json()
            embed.add_field(name="─────────────", value="☕ 카페 원고 생성기", inline=False)
            embed.add_field(name="오늘 방문자", value=f"**{cafe_stats.get('today_visitors', 0)}명**", inline=True)
            embed.add_field(name="쿠팡 클릭", value=f"**{cafe_stats.get('today_coupang_clicks', 0)}회**", inline=True)
            embed.add_field(name="차단 IP", value=f"**{cafe_stats.get('blocked_ips', 0)}개**", inline=True)
        except:
            pass
        
        embed.set_footer(text=comment)
        await message.channel.send(embed=embed)

@tasks.loop(hours=24)
async def report_morning():
    channel = report_bot.get_channel(CH_ID)
    if not channel:
        return
    await asyncio.sleep(8)  # 세종대왕 다음에 말함
    accounts, posts = await get_stats()
    if not accounts:
        return
    published = len([p for p in posts if p['status'] == 'published'])
    context = f"계정 {len(accounts)}개, 전체 발행 {published}개"
    msg = await ai_response("report", "오늘 아침 팀원들에게 현황 통계를 공유해줘", context)
    embed = discord.Embed(description=msg, color=0x40c4ff)
    embed.set_author(name="통계청장 📊")
    await channel.send(embed=embed)

@report_morning.before_loop
async def before_report_morning():
    await report_bot.wait_until_ready()
    now = datetime.now()
    target = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now >= target:
        from datetime import timedelta
        target += timedelta(days=1)
    await asyncio.sleep((target - now).total_seconds())


# ──────────────────────────────────────────
# 🚨 감찰관 (Alert Bot)
# ──────────────────────────────────────────
alert_bot = commands.Bot(command_prefix="!!", intents=intents)

@alert_bot.event
async def on_ready():
    print(f"✅ 감찰관 온라인: {alert_bot.user}")
    check_health.start()
    alert_morning.start()
    random_chat.start()
    security_check.start()

@alert_bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.channel.id != CH_ID:
        return

    intent = await detect_intent(message.content)

    if intent["intent"] in ["security", "error"] or (intent["intent"] == "chat" and any(kw in message.content for kw in ["보안", "해킹", "안전", "점검", "차단", "IP", "ip"])):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{FLASK_URL}/api/security", timeout=aiohttp.ClientTimeout(total=10)) as res:
                    report = await res.json()
            status = report.get("status", "알 수 없음")
            issues = report.get("issues", [])
            blocked = report.get("blocked_ips", [])
            context = f"보안 상태: {status}, 이슈: {issues if issues else '없음'}, 차단 IP: {len(blocked)}개"
            msg = await ai_response("alert", f"보안 관련 질문이 왔어. 현재 보안 상태 알려줘: {message.content}", context)
            embed = discord.Embed(description=msg, color=0x00e676 if status == "정상" else 0xff9800)
            embed.set_author(name="감찰관 🚨")
            embed.add_field(name="보안 상태", value=f"{'✅ 정상' if status == '정상' else '⚠️ 경고'}", inline=True)
            embed.add_field(name="차단 IP", value=f"{len(blocked)}개", inline=True)
            if issues:
                embed.add_field(name="이슈", value=", ".join(issues), inline=False)
            await message.channel.send(embed=embed)
        except:
            msg = await ai_response("alert", message.content)
            await message.channel.send(msg)
        return

    if intent["intent"] == "error":
        accounts, posts = await get_stats()
        if accounts is None:
            msg = await ai_response("alert", "서버 연결 오류 발생! 상황 설명해줘")
            embed = discord.Embed(title="🚨 서버 연결 오류!", description=msg, color=0xff0000, timestamp=datetime.now())
            embed.add_field(name="오류 내용", value="```Flask 서버 연결 실패```")
            embed.add_field(name="조치 필요", value="Railway Naver-Blog-Auto 서버 재시작 필요")
            await message.channel.send(embed=embed)
        else:
            # 정상 상태
            status = f"계정 {len(accounts)}개, 포스트 {len(posts)}개 - 모든 시스템 정상"
            msg = await ai_response("alert", "오류 문의가 왔는데 현재 시스템은 정상이야. 안심시켜줘", status)
            embed = discord.Embed(description=msg, color=0x00e676)
            embed.set_author(name="감찰관 🚨")
            await message.channel.send(embed=embed)

@tasks.loop(hours=6)
async def check_health():
    channel = alert_bot.get_channel(CH_ID)
    if not channel:
        return
    accounts, posts = await get_stats()
    errors = []
    if accounts is None:
        errors.append("네이버 블로그 자동화 서버 연결 실패")
    
    # 두번째 사이트 체크
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(f"{BLOG_DRAFT_URL}/api/stats", timeout=aiohttp.ClientTimeout(total=10)) as r:
                draft_stats = await r.json()
    except:
        errors.append("블로그 초안 서버 연결 실패")
        draft_stats = None

    if errors:
        msg = await ai_response("alert", f"서버 오류 발생! 오류 목록: {errors}")
        embed = discord.Embed(title="🚨 서버 연결 오류!", description=msg, color=0xff0000, timestamp=datetime.now())
        for e in errors:
            embed.add_field(name="오류", value=f"```{e}```", inline=False)
        await channel.send(embed=embed)
    elif draft_stats:
        # 두번째 사이트 통계 - 이상 있으면 알림
        if draft_stats.get("blocked_ips", 0) > 0:
            embed = discord.Embed(title="⚠️ 보안 경고", color=0xff9800, timestamp=datetime.now())
            embed.add_field(name="차단된 IP", value=f"{draft_stats['blocked_ips']}개", inline=True)
            embed.add_field(name="오늘 방문자", value=f"{draft_stats.get('today_visitors',0)}명", inline=True)
            await channel.send(embed=embed)

@tasks.loop(hours=24)
async def alert_morning():
    channel = alert_bot.get_channel(CH_ID)
    if not channel:
        return
    await asyncio.sleep(16)  # 세번째로 말함
    accounts, posts = await get_stats()
    if accounts is None:
        # 서버 연결 오류일 때만 알림
        msg = await ai_response("alert", "서버 연결 오류로 아침 점검 실패. 팀에게 알려줘", "")
        embed = discord.Embed(description=msg, color=0xff0000)
        embed.set_author(name="감찰관 🚨")
        await channel.send(embed=embed)
    else:
        # 정상 - 계정 수 상관없이 정상으로 처리
        status_msg = f"계정 {len(accounts)}개 관리 중, 포스트 {len(posts)}개"
        msg = await ai_response("alert", "아침 시스템 점검 완료. 정상 상태야. 짧게 보고해줘", status_msg)
        embed = discord.Embed(description=msg, color=0x00e676)
        embed.set_author(name="감찰관 🚨")
        await channel.send(embed=embed)

@alert_morning.before_loop
async def before_alert_morning():
    await alert_bot.wait_until_ready()
    now = datetime.now()
    target = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now >= target:
        from datetime import timedelta
        target += timedelta(days=1)
    await asyncio.sleep((target - now).total_seconds())




@tasks.loop(hours=12)
async def security_check():
    """하루 2번 보안 점검 (오전 9시, 오후 9시)"""
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
        
        # 두번째 사이트 보안 체크
        try:
            async with aiohttp.ClientSession() as sess2:
                async with sess2.get(f"{BLOG_DRAFT_URL}/api/security", timeout=aiohttp.ClientTimeout(total=10)) as r2:
                    draft_sec = await r2.json()
            if draft_sec.get("blocked_count", 0) > 0:
                issues.append(f"블로그 초안 사이트 차단 IP {draft_sec['blocked_count']}개")
                status = "경고"
        except:
            issues.append("블로그 초안 사이트 보안 점검 실패")
        
        if status == "경고" or issues:
            # 경고 있을 때
            msg = await ai_response("alert", f"보안 점검 결과 경고 발생! 이슈: {issues}. 팀에게 알려줘")
            embed = discord.Embed(title="⚠️ 보안 점검 경고!", description=msg, color=0xff9800, timestamp=datetime.now())
            for issue in issues:
                embed.add_field(name="⚠️ 이슈", value=issue, inline=False)
            if blocked:
                embed.add_field(name="🚫 차단된 IP", value=", ".join(blocked[:5]), inline=False)
        else:
            # 정상일 때
            msg = await ai_response("alert", "오늘 보안 점검 완료. 모든 항목 정상이야. 팀에게 보고해줘")
            embed = discord.Embed(title="🔒 보안 점검 완료", description=msg, color=0x00e676, timestamp=datetime.now())
            embed.add_field(name="API 키", value="✅ 정상", inline=True)
            embed.add_field(name="차단 IP", value=f"{len(blocked)}개", inline=True)
            embed.add_field(name="상태", value="✅ 정상", inline=True)
        
        await channel.send(embed=embed)
    
    except Exception as e:
        embed = discord.Embed(title="🚨 보안 점검 실패!", description=f"보안 점검 중 오류 발생: {str(e)}", color=0xff0000)
        await channel.send(embed=embed)

@security_check.before_loop
async def before_security_check():
    await alert_bot.wait_until_ready()
    now = datetime.now()
    # 오전 9시 또는 오후 9시 중 가장 가까운 시간으로
    from datetime import timedelta
    candidates = [
        now.replace(hour=9, minute=0, second=0, microsecond=0),
        now.replace(hour=21, minute=0, second=0, microsecond=0),
    ]
    future = [t for t in candidates if t > now]
    if not future:
        target = candidates[0] + timedelta(days=1)
    else:
        target = min(future)
    await asyncio.sleep((target - now).total_seconds())

@tasks.loop(hours=3)
async def random_chat():
    """3시간마다 랜덤하게 봇들끼리 대화"""
    channel = alert_bot.get_channel(CH_ID)
    if not channel:
        return
    
    accounts, posts = await get_stats()
    if not accounts:
        return
    
    published = len([p for p in posts if p["status"] == "published"])
    context = f"계정 {len(accounts)}개, 발행 {published}개"
    
    if accounts is None:
        # 서버 오류일 때만 알림
        msg = await ai_response("alert", "서버 연결이 안 되고 있어. 팀에 알려줘")
        embed = discord.Embed(description=msg, color=0xff0000)
        embed.set_author(name=names.get("alert", "감찰관 🚨"))
        await channel.send(embed=embed)
        return

    # 랜덤 상황 선택
    situations = [
        "팀원들에게 중간 현황 업데이트 해줘",
        "오늘 작업 잘 되고 있는지 체크해줘",
        "블로그 자동화 관련해서 팀원들에게 한마디 해줘",
        "현재 시스템 상태를 짧게 공유해줘",
        "오늘 발행 현황을 재밌게 말해줘"
    ]
    
    situation = random.choice(situations)
    bot_type = random.choice(["alert", "report", "daily"])
    
    msg = await ai_response(bot_type, situation, context)
    
    names = {"alert": "감찰관 🚨", "report": "통계청장 📊", "daily": "일일 리포터 📈"}
    colors = {"alert": 0xff9800, "report": 0x40c4ff, "daily": 0xffd740}
    
    embed = discord.Embed(description=msg, color=colors[bot_type])
    embed.set_author(name=names[bot_type])
    embed.set_footer(text=datetime.now().strftime("%H:%M 중간 업데이트"))
    await channel.send(embed=embed)

@random_chat.before_loop
async def before_random_chat():
    await alert_bot.wait_until_ready()
    await asyncio.sleep(random.randint(1800, 7200))  # 30분~2시간 후 첫 실행

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
    if message.author.bot:
        return
    if message.channel.id != CH_ID:
        return

    intent = await detect_intent(message.content)

    if intent["intent"] == "chat":
        accounts, posts = await get_stats()
        context = f"계정 {len(accounts) if accounts else 0}개, 포스트 {len(posts) if posts else 0}개"
        response = await ai_response("daily", message.content, context)
        # 30% 확률로만 응답 (너무 많이 말하지 않게)
        if random.random() < 0.3:
            await message.channel.send(response)

@tasks.loop(hours=24)
async def daily_report():
    channel = daily_bot.get_channel(CH_ID)
    if not channel:
        return
    await asyncio.sleep(24)  # 마지막으로 말함
    accounts, posts = await get_stats()
    if not accounts:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    today_posts = [p for p in posts if (p.get('created_at') or '').startswith(today)]
    today_pub = [p for p in today_posts if p['status'] == 'published']

    context = f"오늘 생성 {len(today_posts)}개, 발행 {len(today_pub)}개, 전체 계정 {len(accounts)}개"
    msg = await ai_response("daily", "오늘 일일 리포트를 밝고 긍정적으로 팀에게 공유해줘", context)

    embed = discord.Embed(
        title=f"📈 일일 리포트 | {today}",
        color=0xffd740,
        timestamp=datetime.now()
    )
    embed.add_field(name="오늘 생성", value=f"**{len(today_posts)}개**", inline=True)
    embed.add_field(name="오늘 발행", value=f"**{len(today_pub)}개**", inline=True)
    embed.add_field(name="관리 계정", value=f"**{len(accounts)}개**", inline=True)
    embed.set_footer(text=msg)
    await channel.send(embed=embed)

@daily_report.before_loop
async def before_daily():
    await daily_bot.wait_until_ready()
    now = datetime.now()
    target = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now >= target:
        from datetime import timedelta
        target += timedelta(days=1)
    await asyncio.sleep((target - now).total_seconds())


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
