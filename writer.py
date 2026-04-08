from openai import OpenAI
import requests
import os
import json
import urllib.parse

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PEXELS_KEY = os.getenv("PEXELS_API_KEY")

BLOG_TYPES = {
    "monetize": {"name": "💰 수익화 블로그", "tone": "검색 유입을 노리는 SEO 최적화 글, 자연스럽게 제품/서비스를 추천하며 구매 욕구를 자극", "goal": "수익화 및 구매 유도", "link_hint": "제품 추천 링크 자연스럽게 삽입"},
    "ads": {"name": "📢 광고형 블로그", "tone": "특정 제품/서비스를 홍보하는 리뷰 형식, 신뢰감 있게 장점을 부각", "goal": "제품/서비스 홍보", "link_hint": "글 마지막에 강력한 CTA 링크 삽입"},
    "daily": {"name": "📖 일상 블로그", "tone": "친근하고 자연스러운 일상 이야기 형식, 공감대 형성 중심", "goal": "공감 및 소통", "link_hint": ""},
    "business": {"name": "🏪 사업체 블로그", "tone": "지역 키워드를 포함한 업체 홍보 글, 신뢰감 있고 전문적인 톤", "goal": "업체 방문 유도", "link_hint": "업체 방문 유도 CTA 삽입"},
    "info": {"name": "📚 정보성 블로그", "tone": "검색 유입을 위한 전문적이고 신뢰감 있는 정보 제공 형식", "goal": "정보 제공 및 검색 유입", "link_hint": ""}
}

POST_STYLES = {
    "info": "정보성 글",
    "review": "후기/리뷰",
    "listicle": "리스트형",
    "story": "스토리텔링",
    "compare": "비교형"
}

PLACE_POSITION = {
    "top": "글 맨 위 도입부 바로 아래",
    "middle": "글 중간 본문 중간 지점",
    "bottom": "글 맨 마지막 마무리 직전"
}

def suggest_keywords(topic, blog_type="info", count=6):
    btype = BLOG_TYPES.get(blog_type, BLOG_TYPES["info"])
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": f"""네이버 블로그 SEO에 최적화된 키워드 {count}개를 추천해줘.
주제: {topic}
블로그 타입: {btype['name']}
목적: {btype['goal']}
조건:
- 검색량이 많고 경쟁이 적당한 롱테일 키워드
- 한국어 키워드
- 2~5단어 조합
- JSON 형식으로만 답해줘: {{"keywords": ["키워드1", "키워드2", ...]}}"""}],
        temperature=0.8
    )
    content = response.choices[0].message.content.replace("```json","").replace("```","").strip()
    return json.loads(content)["keywords"]

def translate_keyword(keyword):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": f"다음 한국어 키워드를 Pexels 이미지 검색에 적합한 영어로 번역해줘. 단어만 답해줘: {keyword}"}],
            max_tokens=30, temperature=0
        )
        return response.choices[0].message.content.strip()
    except:
        return keyword

def get_pexels_images(keyword, count=3):
    if not PEXELS_KEY:
        return []
    en_keyword = translate_keyword(keyword)
    headers = {"Authorization": PEXELS_KEY}
    params = {"query": en_keyword, "per_page": count, "orientation": "landscape"}
    try:
        res = requests.get("https://api.pexels.com/v1/search", headers=headers, params=params)
        data = res.json()
        return [photo["src"]["large"] for photo in data.get("photos", [])]
    except:
        return []

def get_naver_place_link(place_name):
    encoded = urllib.parse.quote(place_name)
    return f"https://map.naver.com/v5/search/{encoded}"

def analyze_image(image_base64, image_type="image/jpeg"):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{image_type};base64,{image_base64}"}},
                {"type": "text", "text": "이 이미지를 자세히 설명해줘. 음식, 장소, 분위기, 색감 등을 포함해서 블로그 글 작성에 활용할 수 있도록 설명해줘."}
            ]}],
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except:
        return ""

def build_place_block(place_info, position):
    """업체 정보 인용구 블록 생성"""
    if not place_info or not any(place_info.values()):
        return ""
    
    lines = []
    if place_info.get("name"):
        lines.append(f"📍 {place_info['name']}")
    if place_info.get("address"):
        lines.append(f"주소: {place_info['address']}")
    if place_info.get("phone"):
        lines.append(f"전화: {place_info['phone']}")
    if place_info.get("hours"):
        lines.append(f"영업시간: {place_info['hours']}")
    if place_info.get("price"):
        lines.append(f"가격대: {place_info['price']}")
    if place_info.get("parking"):
        lines.append(f"주차: {place_info['parking']}")
    if place_info.get("url"):
        lines.append(f"네이버 지도: {place_info['url']}")
    
    block = "\n".join(lines)
    return f"\n\n---\n> {chr(10).join(['> ' + l for l in lines])}\n---\n\n"

def generate_post(keyword, blog_type="info", post_style="info", custom_prompt="",
                  cta_link="", cta_text="", cpa_link="", cps_link="",
                  place_name="", image_base64="", image_type="image/jpeg",
                  word_count=1000, image_count=3,
                  place_info=None, place_position="bottom"):
    
    btype = BLOG_TYPES.get(blog_type, BLOG_TYPES["info"])
    style = POST_STYLES.get(post_style, POST_STYLES["info"])
    
    # 이미지 분석
    image_desc = ""
    if image_base64:
        image_desc = analyze_image(image_base64, image_type)
    
    # 플레이스 정보 처리
    place_block = ""
    if place_info and any(place_info.values()):
        if place_info.get("name") and not place_info.get("url"):
            place_info["url"] = get_naver_place_link(place_info["name"])
        place_block = build_place_block(place_info, place_position)
    elif place_name:
        place_url = get_naver_place_link(place_name)
        place_info = {"name": place_name, "url": place_url}
        place_block = build_place_block(place_info, place_position)
    
    # 링크 프롬프트
    links_prompt = ""
    if cta_link:
        links_prompt += f"\n- 글 마지막에 자연스럽게 이 링크를 넣어줘 (CTA): {cta_link}"
        if cta_text:
            links_prompt += f" (링크 텍스트: {cta_text})"
    if cpa_link:
        links_prompt += f"\n- 본문 중간에 자연스럽게 이 제휴 링크를 넣어줘 (CPA): {cpa_link}"
    if cps_link:
        links_prompt += f"\n- 상품 언급 시 이 쇼핑 링크를 넣어줘 (CPS): {cps_link}"

    # 업체 정보 위치 지시
    place_position_prompt = ""
    if place_block:
        pos_desc = PLACE_POSITION.get(place_position, PLACE_POSITION["bottom"])
        place_position_prompt = f"\n- 아래 업체 정보를 {pos_desc}에 인용구(>) 형식으로 삽입해줘:\n{place_block}"

    system_prompt = f"""너는 상업용 블로그 콘텐츠를 작성하는 전문 에디터다.
목표는 사람이 직접 쓴 것처럼 자연스럽고 읽기 편한 블로그 글을 만드는 것이다.
절대 기계적으로 쓰지 말고 절대 AI가 쓴 티가 나지 않게 작성한다.

블로그 타입: {btype['name']}
목적: {btype['goal']}
톤: {btype['tone']}
글 형식: {style}
분량: {word_count}자 내외

다음 원칙을 반드시 지켜라:
- 모든 카테고리를 다룰 수 있어야 한다
- 주제에 따라 말투와 흐름은 자연스럽게 조절하되 전체적으로 편안하고 읽기 쉬운 한국어로 작성한다
- 이상한 번역투, 외국어투, 어색한 표현, 과장된 문장 구조는 전부 금지한다
- 독자가 바로 이해할 수 있는 자연스러운 한국어만 사용한다
- 이모지는 절대 사용하지 않는다
- 특수기호 남용도 금지한다
- 의미 없는 감탄사, 과한 강조, 반복 표현도 금지한다
- 문장은 너무 길지 않게 끊어 쓴다
- 가독성을 위해 문단은 짧게 나눈다
- 한 문단이 너무 답답해 보이지 않도록 적절히 줄바꿈한다
- 중간중간 한 줄을 비워서 읽기 흐름을 편하게 만든다
- 목록형 정보가 필요할 때도 딱딱하지 않게 자연스럽게 풀어 쓴다
- 마침표를 과하게 쓰지 말고 전체 말투는 부드럽고 자연스럽게 유지한다
- 기계적으로 정리된 느낌보다 사람이 바로 작성한 듯한 호흡을 살린다
- 완전 자동 스케줄러용 글을 만들 때는 인용구와 구분선을 적극 활용한다
- 중요한 문장, 요약, 주의사항, 핵심 포인트는 인용구 형식(>)으로 분리해서 보여준다
- 주제가 전환되거나 정보 단락이 길어질 때는 구분선(---)을 사용해 흐름을 정리한다
- 단 남용하지 말고 읽기 편한 수준에서만 사용한다

아래 표현은 금지한다:
- AI가 알려드립니다 / 지금부터 설명하겠습니다 / 정리해보겠습니다
- 도움이 되었길 바랍니다 / 전문가처럼 보이기 위한 과한 말투
- 부자연스러운 높임말 / 어색한 번역체 연결어
- 불필요한 영어 혼용 / 의미 없는 반복 문장

출력 형식:
제목:[제목]

[도입부 - 독자가 왜 이 글을 읽어야 하는지 자연스럽게]

[본문 - 정보 전달 중심, 인용구와 구분선 활용]

[마무리 - 억지 요약 없이 읽은 사람이 정리된 느낌]
{links_prompt}
{place_position_prompt}"""

    user_content = f"""주제: {keyword}
카테고리: {btype['name']}
핵심 키워드: {keyword}
톤: {btype['tone']}
목적: {btype['goal']}
분량: {word_count}자 내외
추가 요청사항: {custom_prompt if custom_prompt else '없음'}"""

    if image_desc:
        user_content += f"\n\n[첨부 이미지 설명]\n{image_desc}\n이미지 내용을 글에 자연스럽게 반영해줘."

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
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

    images = get_pexels_images(keyword, count=image_count)
    return {"title": title, "body": body, "images": images, "keyword": keyword}
