from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TOPIC_STYLES = {
    "맛집": "감성적이고 친근한 말투로, 음식 맛과 분위기를 생생하게 묘사해줘. 방문 후기 형식으로 작성해.",
    "부동산": "신뢰감 있고 정보성 강한 톤으로, 실질적인 정보를 제공해줘. 전문가 느낌으로 작성해.",
    "뷰티": "트렌디하고 공감 가는 말투로, 제품 후기나 뷰티 팁 형식으로 작성해.",
    "건강": "전문성 있지만 친근한 톤으로, 건강 정보나 생활 습관 팁을 제공해줘.",
    "여행": "설레고 감성적인 말투로, 여행지의 매력을 생생하게 전달해줘.",
    "IT": "명확하고 실용적인 톤으로, 기술 정보나 사용 후기를 쉽게 설명해줘.",
    "쇼핑": "솔직하고 공감 가는 후기 형식으로, 제품의 장단점을 자연스럽게 얘기해줘.",
    "기타": "자연스럽고 친근한 말투로, 독자가 공감할 수 있게 작성해줘."
}

def generate_post(keyword, topic_type="기타", custom_prompt=""):
    style = TOPIC_STYLES.get(topic_type, TOPIC_STYLES["기타"])
    
    system_prompt = f"""너는 네이버 블로그 전문 작가야.
{style}

규칙:
- AI가 쓴 것처럼 보이지 않게, 사람이 직접 쓴 것처럼 자연스럽게
- 네이버 블로그 특유의 줄바꿈 많이 사용
- 이모지 적절히 활용
- 소제목은 📌 이모지로 구분
- 글 분량은 600~1000자
- 마지막에 자연스러운 마무리 멘트 추가
- 절대 "안녕하세요! 오늘은~" 같은 AI스러운 시작 금지
"""

    user_prompt = f"키워드: {keyword}\n{f'추가 요청: {custom_prompt}' if custom_prompt else ''}\n\n위 키워드로 네이버 블로그 포스팅을 작성해줘. 제목도 같이 만들어줘. 형식: 제목:[제목]\n\n[본문]"

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.85
    )
    
    content = response.choices[0].message.content
    
    # 제목/본문 분리
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
    
    return {"title": title, "body": body}
