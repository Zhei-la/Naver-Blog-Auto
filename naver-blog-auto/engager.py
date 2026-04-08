from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from openai import OpenAI
import time
import os
import random

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=options)
    return driver

def naver_login(driver, naver_id, naver_pw):
    driver.get("https://nid.naver.com/nidlogin.login")
    time.sleep(2)
    driver.execute_script(f"document.getElementById('id').value = '{naver_id}'")
    driver.execute_script(f"document.getElementById('pw').value = '{naver_pw}'")
    time.sleep(1)
    driver.find_element(By.ID, "log.login").click()
    time.sleep(3)
    if "nid.naver.com" in driver.current_url:
        return False
    return True

def generate_comment(post_title, post_content="", tone="friendly"):
    tones = {
        "friendly": "친근하고 따뜻한 톤으로",
        "professional": "전문적이고 정중한 톤으로",
        "casual": "가볍고 캐주얼한 톤으로"
    }
    tone_desc = tones.get(tone, tones["friendly"])
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": f"""네이버 블로그 댓글을 {tone_desc} 작성해줘.
블로그 제목: {post_title}
{f'내용 요약: {post_content[:200]}' if post_content else ''}

조건:
- 1~2문장으로 짧게
- 자연스럽고 진심 어린 댓글
- 스팸처럼 보이지 않게
- 이모지 1개 정도만 사용
- 댓글 내용만 답해줘 (설명 없이)"""}],
        temperature=0.9
    )
    return response.choices[0].message.content.strip()

def auto_like(naver_id, naver_pw, target="neighbor", keyword="", count=10):
    """공감 자동화 - target: neighbor(이웃) or keyword(키워드 검색)"""
    driver = get_driver()
    result = {"success": False, "liked": 0, "message": ""}
    
    try:
        if not naver_login(driver, naver_id, naver_pw):
            result["message"] = "로그인 실패"
            return result

        liked = 0
        posts_to_like = []

        if target == "neighbor":
            # 이웃 새글 가져오기
            driver.get("https://blog.naver.com/FollowingList.naver")
            time.sleep(2)
            posts = driver.find_elements(By.CSS_SELECTOR, ".post_link, .blog_link")
            posts_to_like = [p.get_attribute("href") for p in posts[:count] if p.get_attribute("href")]
        
        elif target == "keyword":
            # 키워드 검색으로 최신글 가져오기
            driver.get(f"https://search.naver.com/search.naver?where=blog&query={keyword}&sm=tab_opt&nso=so:dd,p:1d")
            time.sleep(2)
            posts = driver.find_elements(By.CSS_SELECTOR, ".api_txt_lines.total_tit a, .title_link")
            posts_to_like = [p.get_attribute("href") for p in posts[:count] if p.get_attribute("href")]

        for url in posts_to_like:
            if liked >= count:
                break
            try:
                driver.get(url)
                time.sleep(random.uniform(2, 4))
                
                # 공감 버튼 찾기
                try:
                    like_btn = driver.find_element(By.CSS_SELECTOR, ".u_likeit_btn, .btn_like, .like_btn")
                    if "on" not in like_btn.get_attribute("class"):
                        like_btn.click()
                        liked += 1
                        time.sleep(random.uniform(1, 2))
                except:
                    pass
            except:
                continue

        result["success"] = True
        result["liked"] = liked
        result["message"] = f"공감 {liked}개 완료"

    except Exception as e:
        result["message"] = f"오류: {str(e)}"
    finally:
        driver.quit()
    
    return result

def auto_comment(naver_id, naver_pw, target="neighbor", keyword="", count=5, tone="friendly", custom_comment=""):
    """댓글 자동화"""
    driver = get_driver()
    result = {"success": False, "commented": 0, "message": ""}
    
    try:
        if not naver_login(driver, naver_id, naver_pw):
            result["message"] = "로그인 실패"
            return result

        commented = 0
        posts_to_comment = []

        if target == "neighbor":
            driver.get("https://blog.naver.com/FollowingList.naver")
            time.sleep(2)
            posts = driver.find_elements(By.CSS_SELECTOR, ".post_link, .blog_link")
            posts_to_comment = [p.get_attribute("href") for p in posts[:count*2] if p.get_attribute("href")]
        
        elif target == "keyword":
            driver.get(f"https://search.naver.com/search.naver?where=blog&query={keyword}&sm=tab_opt&nso=so:dd,p:1d")
            time.sleep(2)
            posts = driver.find_elements(By.CSS_SELECTOR, ".api_txt_lines.total_tit a, .title_link")
            posts_to_comment = [p.get_attribute("href") for p in posts[:count*2] if p.get_attribute("href")]

        for url in posts_to_comment:
            if commented >= count:
                break
            try:
                driver.get(url)
                time.sleep(random.uniform(3, 5))
                
                # 제목 가져오기
                try:
                    title = driver.find_element(By.CSS_SELECTOR, ".se-title-text, .pcol1").text
                except:
                    title = keyword or "블로그 글"
                
                # 댓글 생성
                comment_text = custom_comment if custom_comment else generate_comment(title, tone=tone)
                
                # 댓글창 찾기
                try:
                    comment_area = driver.find_element(By.CSS_SELECTOR, ".u_cbox_input, .comment_textarea")
                    comment_area.click()
                    time.sleep(1)
                    comment_area.send_keys(comment_text)
                    time.sleep(1)
                    
                    submit_btn = driver.find_element(By.CSS_SELECTOR, ".u_cbox_btn_upload, .comment_submit")
                    submit_btn.click()
                    commented += 1
                    time.sleep(random.uniform(3, 5))
                except:
                    pass
            except:
                continue

        result["success"] = True
        result["commented"] = commented
        result["message"] = f"댓글 {commented}개 완료"

    except Exception as e:
        result["message"] = f"오류: {str(e)}"
    finally:
        driver.quit()
    
    return result

def auto_neighbor(naver_id, naver_pw, keyword="", count=10, message="안녕하세요! 좋은 글 잘 보고 갑니다. 서로이웃 신청드려요 :)"):
    """서로이웃 자동 신청"""
    driver = get_driver()
    result = {"success": False, "requested": 0, "message": ""}
    
    try:
        if not naver_login(driver, naver_id, naver_pw):
            result["message"] = "로그인 실패"
            return result

        requested = 0
        
        # 키워드로 블로거 찾기
        driver.get(f"https://search.naver.com/search.naver?where=blog&query={keyword}&sm=tab_opt&nso=so:dd,p:1d")
        time.sleep(2)
        
        blog_links = []
        posts = driver.find_elements(By.CSS_SELECTOR, ".api_txt_lines.total_tit a, .title_link")
        for post in posts[:count*2]:
            href = post.get_attribute("href")
            if href and "blog.naver.com" in href:
                # 블로그 ID 추출
                parts = href.split("/")
                for i, p in enumerate(parts):
                    if p == "blog.naver.com" and i+1 < len(parts):
                        blog_id = parts[i+1].split("?")[0]
                        if blog_id and blog_id not in blog_links:
                            blog_links.append(blog_id)
                        break

        for blog_id in blog_links[:count]:
            if requested >= count:
                break
            try:
                driver.get(f"https://blog.naver.com/{blog_id}")
                time.sleep(random.uniform(2, 3))
                
                # 서로이웃 버튼 찾기
                try:
                    neighbor_btn = driver.find_element(By.CSS_SELECTOR, ".btn_buddy, .buddyAddfriend")
                    neighbor_btn.click()
                    time.sleep(2)
                    
                    # 신청 메시지 입력
                    try:
                        msg_area = driver.find_element(By.CSS_SELECTOR, ".buddy_request_message, textarea")
                        msg_area.clear()
                        msg_area.send_keys(message)
                        
                        confirm_btn = driver.find_element(By.CSS_SELECTOR, ".btn_confirm, .buddy_request_ok")
                        confirm_btn.click()
                        requested += 1
                        time.sleep(random.uniform(2, 4))
                    except:
                        pass
                except:
                    pass
            except:
                continue

        result["success"] = True
        result["requested"] = requested
        result["message"] = f"서로이웃 신청 {requested}개 완료"

    except Exception as e:
        result["message"] = f"오류: {str(e)}"
    finally:
        driver.quit()
    
    return result

def auto_engage(naver_id, naver_pw, target="neighbor", keyword="", like_count=10, comment_count=5, tone="friendly"):
    """공감 + 댓글 동시"""
    like_result = auto_like(naver_id, naver_pw, target, keyword, like_count)
    comment_result = auto_comment(naver_id, naver_pw, target, keyword, comment_count, tone)
    return {
        "success": True,
        "liked": like_result["liked"],
        "commented": comment_result["commented"],
        "message": f"공감 {like_result['liked']}개, 댓글 {comment_result['commented']}개 완료"
    }
