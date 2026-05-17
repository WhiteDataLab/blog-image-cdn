import os
import re
import datetime
import base64
import requests
from dotenv import load_dotenv
import markdown
import streamlit as st

import file_manager
import gemini_agent
import blog_publisher

load_dotenv()

CHANNEL_CONFIG = {
    "1": {"name": "DataInsight Lab", "id": "3581078424288898006", "dir": "data/1_data_insight_lab", "lang": "English"},
    "2": {"name": "K-Trend Radar", "id": "7188862452316740616", "dir": "data/2_k_trend_radar", "lang": "English"},
    "3": {"name": "Global Wisdom Hub", "id": "2529089626247182141", "dir": "data/3_global_wisdom_hub", "lang": "English"},
    "4": {"name": "디지털 워크플로우 랩", "id": "5556360003706387143", "dir": "data/4_digital_workflow_lab", "lang": "Korean"},
    "5": {"name": "머니 인사이트 클립", "id": "7957728657232937282", "dir": "data/5_money_insight_clip", "lang": "Korean"},
    "6": {"name": "웰니스 라이프 레시피", "id": "6001598686226598495", "dir": "data/6_wellness_life_recipe", "lang": "Korean"}
}

# 🌟 클라우드 초기화 방지: 파일 변경 시 GitHub에 즉시 덮어쓰기(Push) 하는 함수
def sync_text_to_github(file_path):
    token = os.getenv("GITHUB_TOKEN")
    repo = f"{os.getenv('GITHUB_USERNAME')}/{os.getenv('GITHUB_REPO')}"
    if not all([token, os.getenv("GITHUB_USERNAME"), os.getenv("GITHUB_REPO")]):
        return False
        
    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    
    # 기존 파일의 SHA 키를 먼저 가져와야 덮어쓰기가 가능함
    sha = None
    get_resp = requests.get(url, headers=headers)
    if get_resp.status_code == 200:
        sha = get_resp.json().get("sha")
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        b64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        data = {"message": f"Auto-sync {file_path} from Streamlit Cloud", "content": b64_content}
        if sha:
            data["sha"] = sha # 기존 파일 덮어쓰기
            
        put_resp = requests.put(url, headers=headers, json=data)
        return put_resp.status_code in [200, 201]
    except Exception as e:
        st.error(f"GitHub 동기화 중 오류 발생: {e}")
        return False

def run_auto_posting(channel_key, log_container):
    config = CHANNEL_CONFIG[channel_key]
    log_container.info(f"🔄 [{config['name']}] 무인 자동 포스팅 가동 중...")
    
    brand_guide_path = f"{config['dir']}/brand_guide.md"
    history_path = f"{config['dir']}/posting_history.md"
    titles_history_path = f"{config['dir']}/titles_history.txt"
    
    brand_guide = file_manager.read_markdown_file(brand_guide_path)
    
    if not os.path.exists(titles_history_path) and os.path.exists(history_path):
        log_container.warning("🗄️ [시스템 최적화] 기존 포스팅 히스토리에서 제목 데이터를 추출하여 경량 DB를 구축합니다...")
        with open(history_path, 'r', encoding='utf-8') as f:
            full_content = f.read()
        extracted_titles = re.findall(r'^##\s+(.*)', full_content, re.MULTILINE)
        with open(titles_history_path, 'w', encoding='utf-8') as f:
            for t in extracted_titles:
                clean_t = re.sub(r'\[.*?\]\s*', '', t).strip()
                if clean_t:
                    f.write(f"- {clean_t}\n")
        sync_text_to_github(titles_history_path) # 생성 직후 GitHub 동기화
    
    if os.path.exists(titles_history_path):
        with open(titles_history_path, 'r', encoding='utf-8') as f:
            titles_history = f.read()
    else:
        titles_history = "아직 발행된 포스팅이 없습니다."
    
    log_container.write("🔍 실시간 검색 및 과거 제목 DB 기반 최신 트렌드 토픽 탐색 중...")
    suggested_topics = gemini_agent.suggest_topics(brand_guide, titles_history, config['lang'])
    
    valid_topics = [t for t in suggested_topics if t.strip()]
    if not valid_topics:
        log_container.error("❌ 추천 주제를 가져오지 못했습니다. 다음 채널로 넘어갑니다.")
        return
        
    final_topic = valid_topics[0].split('.', 1)[-1].strip()
    log_container.success(f"🔥 [자동 선정 주제]: {final_topic}")
    
    log_container.write(f"📝 [진행 1/4] 실시간 검색 및 가이드 참조 기반 본문 작성 중...")
    draft_content = gemini_agent.generate_blog_content(final_topic, brand_guide, titles_history, config['lang'])
    
    log_container.write("🎨 [진행 2/4] 이미지 생성 및 GitHub 업로드 중...")
    thumbnail_prompt, body_prompts = gemini_agent.extract_and_format_prompts(draft_content)
    
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    image_dir = os.path.join(config['dir'], "images", now_str)
    
    image_urls = gemini_agent.generate_official_images(thumbnail_prompt, body_prompts, image_dir)
    
    clean_content = draft_content
    if image_urls.get("thumbnail"):
        thumb_img_tag = f'<p style="text-align: center;"><img src="{image_urls["thumbnail"]}" alt="Thumbnail" style="max-width: 100%; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);"></p>'
        clean_content = re.sub(r'\[THUMBNAIL_PROMPT\].*?\[/?THUMBNAIL_PROMPT\]', thumb_img_tag, clean_content, count=1, flags=re.DOTALL | re.IGNORECASE)
    
    for img_url in image_urls.get("body", []):
        if img_url:
            body_img_tag = f'<p style="text-align: center;"><img src="{img_url}" alt="Body Image" style="max-width: 100%; border-radius: 8px; margin: 20px 0;"></p>'
            clean_content = re.sub(r'\[BODY_IMAGE_PROMPT\].*?\[/?BODY_IMAGE_PROMPT\]', body_img_tag, clean_content, count=1, flags=re.DOTALL | re.IGNORECASE)
            
    clean_content = re.sub(r'\[THUMBNAIL_PROMPT\].*?\[/?THUMBNAIL_PROMPT\]', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
    clean_content = re.sub(r'\[BODY_IMAGE_PROMPT\].*?\[/?BODY_IMAGE_PROMPT\]', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
    
    log_container.write("🚀 [진행 3/4] 마크다운 변환 및 구글 블로거 초안 전송 중...")
    html_content = markdown.markdown(clean_content, extensions=['extra', 'nl2br'])
    
    upload_success = blog_publisher.post_to_blogger(config['id'], final_topic, html_content, is_draft=True)
    
    if upload_success:
        log_container.write("💾 [진행 4/4] 데이터 업데이트 및 히스토리 깃헙 동기화 중...")
        file_manager.append_to_history(history_path, final_topic, clean_content)
        with open(titles_history_path, "a", encoding="utf-8") as f:
            f.write(f"- {final_topic}\n")
            
        # 🌟 클라우드 메모리 증발 방지: 작성된 최신 히스토리를 내 깃헙 저장소에 영구 저장
        sync_text_to_github(history_path)
        sync_text_to_github(titles_history_path)
            
        log_container.success(f"✅ [{config['name']}] 포스팅 작업 완료!")
    else:
        log_container.error(f"❌ [{config['name']}] 업로드 실패.")

# --- Streamlit UI 구성 ---
st.set_page_config(page_title="블로그 자동화 시스템", page_icon="🚀", layout="centered")

st.title("🚀 무인 블로그 자동화 웹 관제소")
st.markdown("스마트폰에서도 터치 한 번으로 최신 트렌드 포스팅을 생성하고 발행합니다.")

st.divider()

# 채널 선택기 UI
options = {k: f"{v['name']} ({v['lang']})" for k, v in CHANNEL_CONFIG.items()}
options["7"] = "🔥 전체 채널 연속 자동 포스팅 (1번~6번 순차 실행)"

selected_key = st.selectbox("👉 채널을 선택하세요:", list(options.keys()), format_func=lambda x: options[x])

if st.button("🚀 자동 포스팅 시작", type="primary", use_container_width=True):
    # 로그를 실시간으로 띄워줄 빈 공간 생성
    log_container = st.container()
    
    with st.spinner("로봇 에디터가 작업을 진행 중입니다. 페이지를 끄지 마세요..."):
        if selected_key == "7":
            log_container.info("📢 전 채널 연속 자동화를 시작합니다.")
            for key in sorted(k for k in CHANNEL_CONFIG.keys()):
                try:
                    run_auto_posting(key, log_container)
                except Exception as e:
                    log_container.error(f"❌ {CHANNEL_CONFIG[key]['name']} 진행 중 오류: {e}")
            log_container.success("🎉 모든 채널의 자동 포스팅 공정 완료!")
        else:
            run_auto_posting(selected_key, log_container)
            
    st.balloons() # 완료 시 폰 화면에 풍선 애니메이션 띄우기!