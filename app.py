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

# 🌟 대한민국 표준시(KST) 타임존 정의 (Streamlit Cloud 서버 시각 동기화용)
KST = datetime.timezone(datetime.timedelta(hours=9))

# 클라우드 초기화 방지: 파일 변경 시 GitHub에 즉시 덮어쓰기(Push) 하는 함수
def sync_text_to_github(file_path):
    token = os.getenv("GITHUB_TOKEN")
    repo = f"{os.getenv('GITHUB_USERNAME')}/{os.getenv('GITHUB_REPO')}"
    if not all([token, os.getenv("GITHUB_USERNAME"), os.getenv("GITHUB_REPO")]):
        return False
        
    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    
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
            data["sha"] = sha
            
        put_resp = requests.put(url, headers=headers, json=data)
        return put_resp.status_code in [200, 201]
    except Exception as e:
        st.error(f"GitHub 동기화 중 오류 발생: {e}")
        return False

def run_auto_posting(channel_key, progress_bar, status_text):
    """실시간 프로그레스바와 연동되어 상태를 UI에 표기하는 핵심 포스팅 공정"""
    config = CHANNEL_CONFIG[channel_key]
    
    # 0% 시작
    progress_bar.progress(0)
    status_text.info(f"⏳ [{config['name']}] 파이프라인 가동 준비 중...")
    
    brand_guide_path = f"{config['dir']}/brand_guide.md"
    history_path = f"{config['dir']}/posting_history.md"
    titles_history_path = f"{config['dir']}/titles_history.txt"
    
    brand_guide = file_manager.read_markdown_file(brand_guide_path)
    
    # 히스토리 경량화 DB 구축 단계 (5%)
    progress_bar.progress(5)
    if not os.path.exists(titles_history_path) and os.path.exists(history_path):
        status_text.warning("🗄️ [시스템 최적화] 과거 히스토리에서 제목 추출 및 경량 DB 구축 중...")
        with open(history_path, 'r', encoding='utf-8') as f:
            full_content = f.read()
        extracted_titles = re.findall(r'^##\s+(.*)', full_content, re.MULTILINE)
        with open(titles_history_path, 'w', encoding='utf-8') as f:
            for t in extracted_titles:
                clean_t = re.sub(r'\[.*?\]\s*', '', t).strip()
                if clean_t:
                    f.write(f"- {clean_t}\n")
        sync_text_to_github(titles_history_path)
    
    if os.path.exists(titles_history_path):
        with open(titles_history_path, 'r', encoding='utf-8') as f:
            titles_history = f.read()
    else:
        titles_history = "아직 발행된 포스팅이 없습니다."
    
    # 토픽 탐색 단계 (15%)
    progress_bar.progress(15)
    status_text.info("🔍 실시간 트렌드 및 과거 발행 내역 분석 기반 최신 토픽 탐색 중...")
    suggested_topics = gemini_agent.suggest_topics(brand_guide, titles_history, config['lang'])
    
    valid_topics = [t for t in suggested_topics if t.strip()]
    if not valid_topics:
        status_text.error(f"❌ [{config['name']}] 추천 주제 탐색 실패. 공정을 중단합니다.")
        return False
        
    final_topic = valid_topics[0].split('.', 1)[-1].strip()
    
    # 본문 작성 단계 [진행 1/4] -> 30% 변경
    progress_bar.progress(30)
    status_text.markdown(f"📝 **[진행 1/4] 본문 작성 중...**\n\n🎯 **선정된 주제:** `{final_topic}`")
    draft_content = gemini_agent.generate_blog_content(final_topic, brand_guide, titles_history, config['lang'])
    
    # 이미지 생성 단계 [진행 2/4] -> 55% 변경
    progress_bar.progress(55)
    status_text.markdown(f"🎨 **[진행 2/4] AI 이미지 생성 및 GitHub 호스팅 저장 중...**\n\n💡 *FLUX 엔진으로 무인물 이미지를 제작 중입니다. (약 1분 소요)*")
    
    thumbnail_prompt, body_prompts = gemini_agent.extract_and_format_prompts(draft_content)
    
    # 🌟 임시 디렉토리 생성 시에도 한국 시간(KST) 기준으로 폴더명 포맷팅
    now_str = datetime.datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    image_dir = os.path.join(config['dir'], "images", now_str)
    
    # 백엔드 이미지 대량 생산 가동 (블로킹 구간)
    image_urls = gemini_agent.generate_official_images(thumbnail_prompt, body_prompts, image_dir)
    
    # 이미지 치환 작업 (75%)
    progress_bar.progress(75)
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
    
    # 구글 전송 단계 [진행 3/4] -> 85% 변경
    progress_bar.progress(85)
    status_text.markdown(f"🚀 **[진행 3/4] 구글 블로거로 문서 전송 중...**\n\n📌 타이틀: `{final_topic}`")
    html_content = markdown.markdown(clean_content, extensions=['extra', 'nl2br'])
    
    upload_success = blog_publisher.post_to_blogger(config['id'], final_topic, html_content, is_draft=True)
    
    if upload_success:
        # 데이터 최종 동기화 [진행 4/4] -> 95% 변경
        progress_bar.progress(95)
        status_text.markdown("💾 **[진행 4/4] 로컬 히스토리 갱신 및 GitHub 백업 서버 동기화 중...**")
        file_manager.append_to_history(history_path, final_topic, clean_content)
        with open(titles_history_path, "a", encoding="utf-8") as f:
            f.write(f"- {final_topic}\n")
            
        sync_text_to_github(history_path)
        sync_text_to_github(titles_history_path)
            
        # 100% 완료 마감
        progress_bar.progress(100)
        status_text.success(f"🎉 [{config['name']}] 자동 발행 공정 완벽 완료!")
        return True
    else:
        progress_bar.progress(100)
        status_text.error(f"❌ [{config['name']}] 구글 블로거 전송 단계에서 실패했습니다.")
        return False

# --- Streamlit UI 구성 ---
st.set_page_config(page_title="블로그 자동화 웹 관제소", page_icon="🚀", layout="centered")

st.title("🚀 무인 블로그 자동화 웹 관제소")
st.markdown("스마트폰 환경에서도 끊김 없이 실시간 공정 상태를 추적하고 제어합니다.")

st.divider()

options = {k: f"{v['name']} ({v['lang']})" for k, v in CHANNEL_CONFIG.items()}
options["7"] = "🔥 전체 채널 연속 마스터 자동 포스팅 (1번~6번 연속 순차 가동)"

selected_key = st.selectbox("👉 제어 타겟 채널을 선택하세요:", list(options.keys()), format_func=lambda x: options[x])

if st.button("🚀 자동 포스팅 시작", type="primary", use_container_width=True):
    log_area = st.container()
    
    with log_area:
        if selected_key == "7":
            st.markdown("### 🏭 전 채널 마스터 연속 자동 가동 대시보드")
            # 전체 마스터 진행 바 생성
            total_progress_bar = st.progress(0)
            total_status_text = st.empty()
            
            channels = sorted(k for k in CHANNEL_CONFIG.keys())
            total_channels = len(channels)
            
            for idx, key in enumerate(channels):
                # 전체 진척도 업데이트
                current_percent = int((idx / total_channels) * 100)
                total_progress_bar.progress(current_percent)
                total_status_text.markdown(f"✨ **전체 공정 현황:** 총 {total_channels}개 중 **{idx+1}번째 채널 가동 중** ({idx}/{total_channels} 완료)")
                
                st.markdown(f"#### 📺 {CHANNEL_CONFIG[key]['name']} 공정 로그")
                # 각 채널용 전용 프로그레스 바와 컨테이너 실시간 생성
                chan_pbar = st.progress(0)
                chan_stext = st.empty()
                
                try:
                    run_auto_posting(key, chan_pbar, chan_stext)
                except Exception as e:
                    chan_stext.error(f"❌ 이 채널에서 치명적 예외 발생: {e}")
                
                st.divider()
                
            total_progress_bar.progress(100)
            total_status_text.success(f"🎯 마스터 자동화 완료! 총 {total_channels}개 채널의 포스팅 인프라가 정상 작동 완료되었습니다.")
            
        else:
            st.markdown(f"### 📺 {CHANNEL_CONFIG[selected_key]['name']} 실시간 관제 창")
            single_pbar = st.progress(0)
            single_stext = st.empty()
            run_auto_posting(selected_key, single_pbar, single_stext)
            
    st.balloons() # 축하 풍선 날리기 애니메이션
