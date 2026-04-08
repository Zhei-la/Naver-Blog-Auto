import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import os
import json
from datetime import datetime

# 환경변수
WRITER_TOKEN = os.getenv("WRITER_BOT_TOKEN")
REPORT_TOKEN = os.getenv("REPORT_BOT_TOKEN")
ALERT_TOKEN = os.getenv("ALERT_BOT_TOKEN")
DAILY_TOKEN = os.getenv("DAILY_BOT_TOKEN")

FLASK_URL = os.getenv("FLASK_URL", "http://localhost:5000")

# 채널 ID (환경변수로 관리)
CH_COMMAND = int(os.getenv("CH_COMMAND", 0))   # #naver-command
CH_STATUS  = int(os.getenv("CH_STATUS", 0))    # #naver-status
CH_ALERT   = int(os.getenv("CH_ALERT", 0))     # #naver-alert
CH_DAILY   = int(os.getenv("CH_DAILY", 0))     # #naver-daily

intents = discord.Intents.default()
intents.message_content = True

# ──────────────────────────────────────────
# 📝 NaverWriter - 글 생성 봇
# ──────────────────────────────────────────
writer_bot = commands.Bot(command_prefix="!", intents=intents)

@writer_bot.event
async def on_ready():
    print(f"✅ NaverWriter 온라인: {writer_bot.user}")

@writer_bot.command(name="글써줘")
async def write_post(ctx, *, keyword: str = None):
    if ctx.channel.id != CH_COMMAND:
        return
    if not keyword:
        await ctx.send("❌ 키워드를 입력해줘!\n예시: `!글써줘 강남 맛집 추천`")
        return

    # 계정 목록 가져오기
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{FLASK_URL}/api/accounts") as res:
            accounts = await res.json()

    if not accounts:
        await ctx.send("❌ 등록된 계정이 없어! 대시보드에서 계정 먼저 추가해줘.")
        return

    # 계정 선택 임베드
    embed = discord.Embed(
        title="✍️ 글 생성 시작",
        description=f"키워드: **{keyword}**\n\n어느 계정에 올릴까?",
        color=0x00e676
    )
    for i, acc in enumerate(accounts):
        embed.add_field(name=f"{i+1}. {acc['client_name']}", value=acc['naver_id'], inline=True)

    embed.set_footer(text="숫자로 답해줘 (예: 1)")
    msg = await ctx.send(embed=embed)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

    try:
        reply = await writer_bot.wait_for("message", check=check, timeout=30)
        idx = int(reply.content) - 1
        if idx < 0 or idx >= len(accounts):
            await ctx.send("❌ 잘못된 번호야!")
            return
        account = accounts[idx]
    except asyncio.TimeoutError:
        await ctx.send("⏰ 시간 초과! 다시 시도해줘.")
        return

    # 글 생성 중
    loading = await ctx.send(f"⏳ **{account['client_name']}** 계정으로 글 생성 중...")

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{FLASK_URL}/api/generate", json={
            "account_id": account['id'],
            "keyword": keyword
        }) as res:
            data = await res.json()

    await loading.delete()

    if not data.get("success"):
        await ctx.send(f"❌ 생성 실패: {data.get('message')}")
        return

    # 미리보기 임베드
    body_preview = data['body'][:300] + "..." if len(data['body']) > 300 else data['body']
    embed = discord.Embed(
        title=f"📝 {data['title']}",
        description=body_preview,
        color=0x40c4ff
    )
    embed.add_field(name="계정", value=f"{account['client_name']} ({account['naver_id']})", inline=True)
    embed.add_field(name="키워드", value=keyword, inline=True)
    embed.set_footer(text=f"Post ID: {data['post_id']} | !발행 {data['post_id']} 로 발행")

    await ctx.send(embed=embed)

@writer_bot.command(name="발행")
async def publish_post(ctx, post_id: int = None):
    if ctx.channel.id != CH_COMMAND:
        return
    if not post_id:
        await ctx.send("❌ Post ID를 입력해줘!\n예시: `!발행 3`")
        return

    loading = await ctx.send(f"🚀 발행 중... (시간이 걸릴 수 있어)")

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{FLASK_URL}/api/publish/{post_id}") as res:
            data = await res.json()

    await loading.delete()

    if data.get("success"):
        embed = discord.Embed(
            title="🎉 발행 완료!",
            description=f"네이버 블로그에 성공적으로 올라갔어!",
            color=0x00e676
        )
        if data.get("url"):
            embed.add_field(name="URL", value=data['url'])
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ 발행 실패: {data.get('message')}")

@writer_bot.command(name="계정목록")
async def list_accounts(ctx):
    if ctx.channel.id != CH_COMMAND:
        return
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{FLASK_URL}/api/accounts") as res:
            accounts = await res.json()

    if not accounts:
        await ctx.send("등록된 계정 없음")
        return

    embed = discord.Embed(title="👤 계정 목록", color=0x00e676)
    for acc in accounts:
        embed.add_field(
            name=f"{acc['client_name']}",
            value=f"ID: `{acc['naver_id']}` | 주제: {acc['topic_type']}",
            inline=False
        )
    await ctx.send(embed=embed)

@writer_bot.command(name="도움말")
async def help_writer(ctx):
    if ctx.channel.id != CH_COMMAND:
        return
    embed = discord.Embed(title="📝 NaverWriter 도움말", color=0x00e676)
    embed.add_field(name="!글써줘 [키워드]", value="키워드로 AI 글 생성", inline=False)
    embed.add_field(name="!발행 [Post ID]", value="생성된 글 네이버에 발행", inline=False)
    embed.add_field(name="!계정목록", value="등록된 계정 보기", inline=False)
    await ctx.send(embed=embed)


# ──────────────────────────────────────────
# 📊 NaverReport - 현황 조회 봇
# ──────────────────────────────────────────
report_bot = commands.Bot(command_prefix="!", intents=intents)

@report_bot.event
async def on_ready():
    print(f"✅ NaverReport 온라인: {report_bot.user}")

@report_bot.command(name="현황")
async def report_status(ctx):
    if ctx.channel.id != CH_STATUS:
        return

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{FLASK_URL}/api/accounts") as res:
            accounts = await res.json()
        async with session.get(f"{FLASK_URL}/api/posts") as res:
            posts = await res.json()

    published = [p for p in posts if p['status'] == 'published']
    draft = [p for p in posts if p['status'] == 'draft']

    embed = discord.Embed(
        title="📊 네이버 블로그 현황",
        color=0x40c4ff,
        timestamp=datetime.now()
    )
    embed.add_field(name="👤 관리 계정", value=f"**{len(accounts)}개**", inline=True)
    embed.add_field(name="✅ 발행 완료", value=f"**{len(published)}개**", inline=True)
    embed.add_field(name="📝 초안", value=f"**{len(draft)}개**", inline=True)

    # 계정별 현황
    for acc in accounts:
        acc_posts = [p for p in posts if p['account_id'] == acc['id']]
        acc_published = len([p for p in acc_posts if p['status'] == 'published'])
        embed.add_field(
            name=f"📌 {acc['client_name']}",
            value=f"발행: {acc_published}개 | 전체: {len(acc_posts)}개",
            inline=False
        )

    await ctx.send(embed=embed)

@report_bot.command(name="최근글")
async def recent_posts(ctx):
    if ctx.channel.id != CH_STATUS:
        return

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{FLASK_URL}/api/posts") as res:
            posts = await res.json()

    recent = posts[:5]
    embed = discord.Embed(title="📋 최근 포스트 5개", color=0x40c4ff)
    for p in recent:
        status = "✅ 발행" if p['status'] == 'published' else "📝 초안"
        embed.add_field(
            name=f"{status} | {p['client_name']}",
            value=f"**{p['title'][:30]}...**\n키워드: {p['keyword']}",
            inline=False
        )
    await ctx.send(embed=embed)


# ──────────────────────────────────────────
# 🚨 NaverAlert - 오류 알림 봇
# ──────────────────────────────────────────
alert_bot = commands.Bot(command_prefix="!", intents=intents)

@alert_bot.event
async def on_ready():
    print(f"✅ NaverAlert 온라인: {alert_bot.user}")
    check_health.start()

@tasks.loop(hours=6)
async def check_health():
    """6시간마다 발행 시스템 상태 체크"""
    channel = alert_bot.get_channel(CH_ALERT)
    if not channel:
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{FLASK_URL}/api/accounts", timeout=aiohttp.ClientTimeout(total=10)) as res:
                if res.status != 200:
                    raise Exception(f"서버 응답 오류: {res.status}")
                accounts = await res.json()

        if not accounts:
            return

        # 발행 테스트 (실제 발행 없이 서버 연결만 확인)
        embed = discord.Embed(
            title="✅ 시스템 정상",
            description=f"관리 계정 {len(accounts)}개 | 서버 연결 정상",
            color=0x00e676,
            timestamp=datetime.now()
        )
        embed.set_footer(text="6시간마다 자동 체크")
        await channel.send(embed=embed)

    except Exception as e:
        embed = discord.Embed(
            title="🚨 시스템 오류 감지!",
            description=f"**오류 내용:**\n```{str(e)}```",
            color=0xff5252,
            timestamp=datetime.now()
        )
        embed.add_field(name="조치 필요", value="Railway 서버 상태 확인 또는 blogger.py 셀렉터 점검")
        await channel.send(embed=embed)

async def send_alert(message: str, is_error: bool = True):
    """외부에서 호출하는 알림 함수"""
    channel = alert_bot.get_channel(CH_ALERT)
    if not channel:
        return

    color = 0xff5252 if is_error else 0x00e676
    title = "🚨 오류 발생!" if is_error else "✅ 정상 처리"

    embed = discord.Embed(title=title, description=message, color=color, timestamp=datetime.now())
    await channel.send(embed=embed)


# ──────────────────────────────────────────
# 📈 NaverDaily - 일일 리포트 봇
# ──────────────────────────────────────────
daily_bot = commands.Bot(command_prefix="!", intents=intents)

@daily_bot.event
async def on_ready():
    print(f"✅ NaverDaily 온라인: {daily_bot.user}")
    daily_report.start()

@tasks.loop(hours=24)
async def daily_report():
    """매일 오전 9시 일일 리포트"""
    channel = daily_bot.get_channel(CH_DAILY)
    if not channel:
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{FLASK_URL}/api/accounts") as res:
                accounts = await res.json()
            async with session.get(f"{FLASK_URL}/api/posts") as res:
                posts = await res.json()

        today = datetime.now().strftime("%Y-%m-%d")
        today_posts = [p for p in posts if p.get('created_at', '').startswith(today)]
        today_published = [p for p in today_posts if p['status'] == 'published']

        embed = discord.Embed(
            title=f"📈 일일 리포트 | {today}",
            color=0xffd740,
            timestamp=datetime.now()
        )
        embed.add_field(name="오늘 생성", value=f"**{len(today_posts)}개**", inline=True)
        embed.add_field(name="오늘 발행", value=f"**{len(today_published)}개**", inline=True)
        embed.add_field(name="관리 계정", value=f"**{len(accounts)}개**", inline=True)

        total_published = len([p for p in posts if p['status'] == 'published'])
        embed.add_field(name="누적 발행", value=f"**{total_published}개**", inline=False)

        if today_published:
            recent = "\n".join([f"• {p['client_name']}: {p['title'][:20]}..." for p in today_published[:3]])
            embed.add_field(name="오늘 발행된 글", value=recent, inline=False)

        await channel.send(embed=embed)

    except Exception as e:
        await channel.send(f"⚠️ 일일 리포트 생성 실패: {str(e)}")

@daily_report.before_loop
async def before_daily():
    """오전 9시에 맞춰 시작"""
    await daily_bot.wait_until_ready()
    now = datetime.now()
    target = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now >= target:
        from datetime import timedelta
        target += timedelta(days=1)
    await asyncio.sleep((target - now).total_seconds())

@daily_bot.command(name="리포트")
async def manual_report(ctx):
    """수동으로 리포트 받기"""
    if ctx.channel.id != CH_DAILY:
        return
    await daily_report()


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
