from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import os

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
    
    # JS로 입력 (봇 감지 우회)
    driver.execute_script(f"document.getElementById('id').value = '{naver_id}'")
    driver.execute_script(f"document.getElementById('pw').value = '{naver_pw}'")
    time.sleep(1)
    
    driver.find_element(By.ID, "log.login").click()
    time.sleep(3)
    
    # 로그인 성공 확인
    if "nid.naver.com" in driver.current_url:
        return False, "로그인 실패 (캡차 또는 비밀번호 오류)"
    
    return True, "로그인 성공"

def publish_post(naver_id, naver_pw, title, body):
    driver = get_driver()
    result = {"success": False, "message": "", "url": ""}
    
    try:
        # 로그인
        success, msg = naver_login(driver, naver_id, naver_pw)
        if not success:
            result["message"] = msg
            return result
        
        # 블로그 글쓰기 페이지
        driver.get(f"https://blog.naver.com/{naver_id}")
        time.sleep(2)
        
        # 글쓰기 버튼
        driver.get("https://blog.naver.com/PostWriteForm.naver")
        time.sleep(3)
        
        # iframe 전환 (에디터)
        wait = WebDriverWait(driver, 10)
        
        # 제목 입력
        try:
            title_frame = wait.until(EC.presence_of_element_located((By.ID, "titleTypeText")))
            title_frame.click()
            title_frame.send_keys(title)
        except:
            # 새 에디터 방식
            title_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".se-title-input")))
            title_input.click()
            title_input.send_keys(title)
        
        time.sleep(1)
        
        # 본문 iframe 진입
        try:
            driver.switch_to.frame("mainFrame")
        except:
            pass
        
        try:
            editor = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".se-content")))
            editor.click()
            # 본문 입력 (줄바꿈 처리)
            for line in body.split('\n'):
                editor.send_keys(line)
                from selenium.webdriver.common.keys import Keys
                editor.send_keys(Keys.RETURN)
        except Exception as e:
            result["message"] = f"본문 입력 실패: {str(e)}"
            return result
        
        time.sleep(1)
        
        # 발행 버튼
        try:
            driver.switch_to.default_content()
            publish_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".publish_btn, .btn_publish, #publishBtn")))
            publish_btn.click()
            time.sleep(2)
            
            # 발행 확인 팝업
            confirm_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn_ok, .confirm_btn")))
            confirm_btn.click()
            time.sleep(3)
        except Exception as e:
            result["message"] = f"발행 버튼 오류: {str(e)}"
            return result
        
        result["success"] = True
        result["message"] = "발행 완료"
        result["url"] = driver.current_url
        
    except Exception as e:
        result["message"] = f"오류: {str(e)}"
    finally:
        driver.quit()
    
    return result
