from openai import OpenAI
import requests
import os
import json

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PEXELS_KEY = os.getenv("PEXELS_API_KEY")

# 블로그 타입별 설정
BLOG_TYPES = {
    "monetize": {
        "name": "💰 수익화 블로그",
        "tone": "검색 유입을 노리는 SEO 최적화 글, 자연스럽게 제품/서비스를 추천하며 구매 욕구를 자극하는 톤",
        "style": "정보성 + 추천 형식",
        "link_hint": "본문에 자연스럽게 제품 추천 링크 삽입",
        "auto_cta": True
    },
    "ads": {
        "name": "📢 광고형 블로그",
        "tone": "특정 제품/서비스를 홍보하는 리뷰 형식, 신뢰감 있게 장점을 부각",
        "style": "리뷰/후기 형식",
        "link_hint": "글 마지막에 강력한 CTA 링크 삽입",
        "auto_cta": True
    },
    "daily": {
        "name": "📖 일상 블로그",
        "tone": "친근하고 자연스러운 일상 이야기 형식, 공감대 형성 중심",
        "style": "스토리텔링 형식",
        "link_hint": "",
        "auto_cta": False
    },
    "business": {
        "name": "🏪 사업체 블로그",
        "tone": "지역 키워드를 포함한 업체 홍보 글, 신뢰감 있고 전문적인 톤",
        "style": "업체 소개/홍보 형식",
        "link_hint": "업체 방문 유도 CTA 삽입",
        "auto_cta": True
    },
    "info": {
        "name": "📚 정보성 블로그",
        "tone": "검색 유입을 위한 전문적이고 신뢰감 있는 정보 제공 형식",
        "style": "정보성 글 형식",
        "link_hint": "",
        "auto_cta": False
    }
}

POST_STYLES = {
    "info": "정보성 글 - 전문적이고 신뢰감 있는 톤",
    "review": "후기/리뷰 - 실제 사용자처럼 솔직하고 공감 가는 톤",
    "listicle": "리스트형 - 번호나 항목으로 정리된 읽기 쉬운 형식",
    "story": "스토리텔링 - 경험담처럼 자연스럽고 감성적인 톤",
    "compare": "비교형 - 여러 옵션을 비교 분석하는 형식"
}

def suggest_keywords(topic, blog_type="info", count=6):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": f"""네이버 블로그 SEO에 최적화된 키워드 {count}개를 추천해줘.
주제: {topic}
블로그 타입: {BLOG_TYPES.get(blog_type, {}).get('name', '일반')}
조건:
- 검색량이 많고 경쟁이 적당한 키워드
- 한국어 키워드
- 각 키워드는 2~5단어 조합
- JSON 형식으로만 답해줘: {{"keywords": ["키워드1", "키워드2", ...]}}"""}],
        temperature=0.8
    )
    content = response.choices[0].message.content.replace("```json","").replace("```","").strip()
    return json.loads(content)["keywords"]

def get_pexels_images(keyword, count=3):
    if not PEXELS_KEY:
        return []
    headers = {"Authorization": PEXELS_KEY}
    params = {"query": keyword, "per_page": count}
    try:
        res = requests.get("https://api.pexels.com/v1/search", headers=headers, params=params)
        data = res.json()
        return [photo["src"]["large"] for photo in data.get("photos", [])]
    except:
        return []

def generate_post(keyword, blog_type="info", post_style="info", custom_prompt="",
                  cta_link="", cta_text="", cpa_link="", cps_link=""):
    btype = BLOG_TYPES.get(blog_type, BLOG_TYPES["info"])
    style = POST_STYLES.get(post_style, POST_STYLES["info"])

    links_prompt = ""
    if cta_link:
        links_prompt += f"\n- 글 마지막에 자연스럽게 이 링크를 넣어줘 (CTA): {cta_link}"
        if cta_text:
            links_prompt += f" (링크 텍스트: {cta_text})"
    if cpa_link:
        links_prompt += f"\n- 본문 중간에 자연스럽게 이 제휴 링크를 넣어줘 (CPA): {cpa_link}"
    if cps_link:
        links_prompt += f"\n- 상품 언급 시 이 쇼핑 링크를 넣어줘 (CPS): {cps_link}"

    system_prompt = f"""너는 네이버 블로그 전문 작가야.
블로그 타입: {btype['name']}
톤: {btype['tone']}
형식: {style}
규칙:
- AI가 쓴 것처럼 보이지 않게, 사람이 직접 쓴 것처럼 자연스럽게
- 네이버 블로그 특유의 줄바꿈 많이 사용
- 이모지 적절히 활용
- 소제목은 📌 이모지로 구분
- 글 분량은 800~1200자
- "안녕하세요! 오늘은~" 같은 AI스러운 시작 절대 금지
- 키워드를 제목과 본문에 자연스럽게 2~3번 포함
{f'- {btype["link_hint"]}' if btype["link_hint"] else ""}
{links_prompt}"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"키워드: {keyword}\n{f'추가 요청: {custom_prompt}' if custom_prompt else ''}\n\n위 키워드로 네이버 블로그 포스팅을 작성해줘.\n형식:\n제목:[제목]\n\n[본문]"}
        ],
        temperature=0.85
    )

    content = response.choices[0].message.content
    lines = content.strip().split('\n')
    title, body = "", ""
    for i, line in enumerate(lines):
        if line.startswith("제목:"):
            title = line.replace("제목:", "").strip()
            body = '\n'.join(lines[i+1:]).strip()
            break
    if not title:
        title = keyword + " 완벽 정리"
        body = content

    images = get_pexels_images(keyword, count=3)
    return {"title": title, "body": body, "images": images, "keyword": keyword}
