from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import json
import re
from datetime import datetime

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

def safe_text(driver, selector, default="0"):
    try:
        el = driver.find_element(By.CSS_SELECTOR, selector)
        text = el.text.strip().replace(",", "")
        return text if text else default
    except:
        return default

def get_blog_insight(naver_id, naver_pw, date=None):
    """네이버 블로그 통계 가져오기"""
    driver = get_driver()
    result = {
        "success": False,
        "error": "",
        "date": date or datetime.now().strftime("%Y.%m.%d"),
        "daily": {
            "views": "0",
            "visitors": "0",
            "visits": "0",
            "likes": "0",
            "comments": "0",
            "neighbor_change": "0"
        },
        "keywords": [],
        "top_posts": [],
        "hourly": [],
        "fetched_at": datetime.now().isoformat()
    }

    try:
        if not naver_login(driver, naver_id, naver_pw):
            result["error"] = "로그인 실패"
            return result

        # 블로그 통계 페이지
        driver.get(f"https://blog.naver.com/{naver_id}/admin/statistics")
        time.sleep(3)

        # iframe 진입 시도
        try:
            wait = WebDriverWait(driver, 10)
            iframe = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "iframe#mainFrame, iframe")))
            driver.switch_to.frame(iframe)
            time.sleep(2)
        except:
            pass

        # 일간 현황 데이터
        try:
            stats = driver.find_elements(By.CSS_SELECTOR, ".graph_area .num, .statistics_daily .num, .count_area .num")
            if len(stats) >= 5:
                result["daily"]["views"] = stats[0].text.replace(",", "") or "0"
                result["daily"]["visitors"] = stats[1].text.replace(",", "") or "0"
                result["daily"]["likes"] = stats[2].text.replace(",", "") or "0"
                result["daily"]["comments"] = stats[3].text.replace(",", "") or "0"
                result["daily"]["neighbor_change"] = stats[4].text.replace(",", "") or "0"
        except Exception as e:
            result["error"] += f" 일간통계오류:{str(e)[:30]}"

        # 유입 키워드
        try:
            driver.switch_to.default_content()
            driver.get(f"https://blog.naver.com/{naver_id}/admin/statistics/inflow")
            time.sleep(2)
            try:
                iframe = driver.find_element(By.CSS_SELECTOR, "iframe#mainFrame, iframe")
                driver.switch_to.frame(iframe)
                time.sleep(2)
            except:
                pass
            
            kw_els = driver.find_elements(By.CSS_SELECTOR, ".keyword_list li, .inflow_keyword li, .list_keyword li")
            keywords = []
            for el in kw_els[:10]:
                try:
                    kw = el.find_element(By.CSS_SELECTOR, ".keyword, .word, span").text.strip()
                    cnt = el.find_element(By.CSS_SELECTOR, ".count, .num, em").text.strip().replace(",", "")
                    if kw and cnt:
                        keywords.append({"keyword": kw, "count": cnt})
                except:
                    pass
            result["keywords"] = keywords
        except Exception as e:
            result["error"] += f" 키워드오류:{str(e)[:30]}"

        result["success"] = True

    except Exception as e:
        result["error"] = str(e)[:100]
        result["success"] = False
    finally:
        driver.quit()

    return result
