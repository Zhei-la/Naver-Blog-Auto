from openai import OpenAI
import requests
import os
import random

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PEXELS_KEY = os.getenv("PEXELS_API_KEY")

POST_STYLES = {
    "info": "정보성 글 - 전문적이고 신뢰감 있는 톤으로 유용한 정보를 제공해줘",
    "review": "후기/리뷰 - 실제 사용자처럼 솔직하고 공감 가는 톤으로 써줘",
    "listicle": "리스트형 - 번호나 항목으로 정리된 읽기 쉬운 형식으로 써줘",
    "story": "스토리텔링 - 경험담처럼 자연스럽고 감성적인 톤으로 써줘",
    "compare": "비교형 - 여러 옵션을 비교 분석하는 형식으로 써줘"
}

TOPIC_TONES = {
    "맛집": "감성적이고 친근한 말투, 음식 맛과 분위기를 생생하게",
    "부동산": "신뢰감 있고 정보성 강한 톤, 실질적 정보 제공",
    "뷰티": "트렌디하고 공감 가는 말투, 제품 후기나 팁 형식",
    "건강": "전문성 있지만 친근한 톤, 건강 정보나 생활 팁",
    "여행": "설레고 감성적인 말투, 여행지 매력을 생생하게",
    "IT": "명확하고 실용적인 톤, 기술 정보를 쉽게 설명",
    "쇼핑": "솔직하고 공감 가는 후기 형식, 제품 장단점",
    "기타": "자연스럽고 친근한 말투, 독자가 공감할 수 있게"
}

def suggest_keywords(topic, topic_type="기타", count=5):
    """AI가 키워드 추천"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": f"""네이버 블로그 SEO에 최적화된 키워드 {count}개를 추천해줘.
주제: {topic}
카테고리: {topic_type}

조건:
- 검색량이 많고 경쟁이 적당한 키워드
- 한국어 키워드
- 각 키워드는 2~5단어 조합
- JSON 형식으로만 답해줘: {{"keywords": ["키워드1", "키워드2", ...]}}"""
        }],
        temperature=0.8
    )
    import json
    content = response.choices[0].message.content
    content = content.replace("```json", "").replace("```", "").strip()
    return json.loads(content)["keywords"]

def get_pexels_images(keyword, count=3):
    """Pexels에서 이미지 가져오기"""
    if not PEXELS_KEY:
        return []
    
    headers = {"Authorization": PEXELS_KEY}
    params = {"query": keyword, "per_page": count, "locale": "ko-KR"}
    
    try:
        res = requests.get("https://api.pexels.com/v1/search", headers=headers, params=params)
        data = res.json()
        return [photo["src"]["large"] for photo in data.get("photos", [])]
    except:
        return []

def generate_post(keyword, topic_type="기타", post_style="info", custom_prompt="", 
                  cta_link="", cta_text="", cpa_link="", cps_link=""):
    """AI 블로그 글 생성"""
    
    tone = TOPIC_TONES.get(topic_type, TOPIC_TONES["기타"])
    style = POST_STYLES.get(post_style, POST_STYLES["info"])
    
    # CTA/CPA/CPS 링크 설정
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
톤: {tone}
형식: {style}

규칙:
- AI가 쓴 것처럼 보이지 않게, 사람이 직접 쓴 것처럼 자연스럽게
- 네이버 블로그 특유의 줄바꿈 많이 사용 (문단마다 빈 줄)
- 이모지 적절히 활용 (과하지 않게)
- 소제목은 📌 이모지로 구분
- 글 분량은 800~1200자
- "안녕하세요! 오늘은~" 같은 AI스러운 시작 절대 금지
- 자연스러운 구어체 사용
- 키워드를 제목과 본문에 자연스럽게 2~3번 포함{links_prompt}"""

    user_prompt = f"""키워드: {keyword}
{f'추가 요청: {custom_prompt}' if custom_prompt else ''}

위 키워드로 네이버 블로그 포스팅을 작성해줘.
형식: 
제목:[제목]

[본문]"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.85
    )
    
    content = response.choices[0].message.content
    lines = content.strip().split('\n')
    title = ""
    body = ""
    
    for i, line in enumerate(lines):
        if line.startswith("제목:"):
            title = line.replace("제목:", "").strip()
            body = '\n'.join(lines[i+1:]).strip()
            break
    
    if not title:
        title = keyword + " 완벽 정리"
        body = content

    # Pexels 이미지 가져오기
    images = get_pexels_images(keyword, count=3)
    
    return {
        "title": title,
        "body": body,
        "images": images,
        "keyword": keyword
    }
