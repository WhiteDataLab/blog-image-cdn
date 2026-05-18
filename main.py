import os
import re
import datetime
import base64
import requests
from dotenv import load_dotenv
import markdown

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

# 🌟 대한민국 표준시(KST) 타임존 정의 (GitHub Actions 해외 러너 서버 시각 동기화용)
KST = datetime.timezone(datetime.timedelta(hours=9))

def sync_text_to_github(file_path):
    """배치에서 수정된 텍스트 파일(히스토리/DB)을 GitHub 저장소에 즉시 반영하여 완전 동기화를 유지합니다."""
    token = os.getenv("GITHUB_TOKEN")
    repo = f"{os.getenv('GITHUB_USERNAME')}/{os.getenv('GITHUB_REPO')}"
    if not all([token, os.getenv("GITHUB_USERNAME"), os.getenv("GITHUB_REPO")]):
        print("⚠️ GitHub 설정 누락으로 인해 클라우드 동기화를 건너뜁니다 (.env 또는 Actions Secret 확인 요망).")
        return False
            
    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
        
    # 기존 파일의 SHA 키를 먼저 조회 (덮어쓰기 필수 규격)
    sha = None
    get_resp = requests.get(url, headers=headers)
    if get_resp.status_code == 200:
        sha = get_resp.json().get("sha")
            
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
                    
        b64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        data = {"message": f"Auto-sync {file_path} from GitHub Actions Batch", "content": b64_content}
        if sha:
            data["sha"] = sha
                    
        put_resp = requests.put(url, headers=headers, json=data)
        return put_resp.status_code in [200, 201]
    except Exception as e:
        print(f"❌ GitHub 동기화 중 오류 발생: {e}")
        return False

def run_auto_posting(channel_key):
    config = CHANNEL_CONFIG[channel_key]
    print(f"\n========================================")
    print(f"🏭 [{config['name']}] 무인 자동 포스팅 공정 가동...")
    print(f"========================================")
    
    brand_guide_path = f"{config['dir']}/brand_guide.md"
    history_path = f"{config['dir']}/posting_history.md"
    titles_history_path = f"{config['dir']}/titles_history.txt"
    
    brand_guide = file_manager.read_markdown_file(brand_guide_path)
    
    # [DB 자동 마이그레이션]: 최초 가동 시 기존 히스토리에서 제목 DB 구축 및 깃허브 동기화
    if not os.path.exists(titles_history_path) and os.path.exists(history_path):
        print("🗄️ [시스템 최적화] 기존 포스팅 히스토리에서 제목 데이터를 추출하여 경량 DB를 구축합니다...")
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
    
    print("🔍 실시간 검색 및 과거 제목 DB 기반 최신 트렌드 토픽 탐색 중...")
    suggested_topics = gemini_agent.suggest_topics(brand_guide, titles_history, config['lang'])
    
    valid_topics = [t for t in suggested_topics if t.strip()]
    if not valid_topics:
        print("❌ 추천 주제를 가져오지 못했습니다. 다음 채널로 넘어갑니다.")
        return
        
    final_topic = valid_topics[0].split('.', 1)[-1].strip()
    print(f"🔥 [자동 선정 주제]: {final_topic}")
    
    print(f"📝 [진행 1/4] 실시간 검색 및 가이드 참조 기반 본문 작성 중...")
    draft_content = gemini_agent.generate_blog_content(final_topic, brand_guide, titles_history, config['lang'])
    
    print("🎨 [진행 2/4] 이미지 생성 및 GitHub 업로드 중...")
    thumbnail_prompt, body_prompts = gemini_agent.extract_and_format_prompts(draft_content)
    
    # KST 시간 기준으로 폴더 스트링 조립
    now_str = datetime.datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    image_dir = os.path.join(config['dir'], "images", now_str)
    
    # 이미지 생성 전 프롬프트 로그 백업 진행
    prompts_log_path = f"{config['dir']}/image_prompts_log.txt"
    try:
        with open(prompts_log_path, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}] {final_topic}\n")
            f.write(f"📸 [THUMBNAIL PROMPT]\n{thumbnail_prompt if thumbnail_prompt else 'N/A'}\n")
            for idx, bp in enumerate(body_prompts, 1):
                f.write(f"🖼️ [BODY PROMPT {idx}]\n{bp}\n")
            f.write("-" * 60 + "\n")
        print(f"    💾 이미지 프롬프트가 로그 파일에 백업되었습니다: {prompts_log_path}")
        sync_text_to_github(prompts_log_path) # 프롬프트 로그도 깃허브에 함께 동기화
    except Exception as log_error:
        print(f"    ⚠️ 로그 파일 저장 중 오류 발생 (진행은 계속됩니다): {log_error}")
    
    # 핵심 엔진 호출 (gemini_agent 내부에서 무료 인물 배제 FLUX 인프라로 연결됨)
    image_urls = gemini_agent.generate_official_images(thumbnail_prompt, body_prompts, image_dir)
    
    clean_content = draft_content
    
    # 치환 정규식 안전장치 적용 (/ 기호 누락 및 퍼지 매칭 대응)
    if image_urls.get("thumbnail"):
        thumb_img_tag = f'<p style="text-align: center;"><img src="{image_urls["thumbnail"]}" alt="Thumbnail" style="max-width: 100%; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);"></p>'
        # AI 오타 대응을 위해 유연화 패턴 적용
        clean_content = re.sub(r'\[\s*THUMB\w*?PROMPT\s*\].*?\[/?\s*THUMB\w*?PROMPT\s*\]', thumb_img_tag, clean_content, count=1, flags=re.DOTALL | re.IGNORECASE)
    
    for img_url in image_urls.get("body", []):
        if img_url:
            body_img_tag = f'<p style="text-align: center;"><img src="{img_url}" alt="Body Image" style="max-width: 100%; border-radius: 8px; margin: 20px 0;"></p>'
            clean_content = re.sub(r'\[BODY_IMAGE_PROMPT\].*?\[/?BODY_IMAGE_PROMPT\]', body_img_tag, clean_content, count=1, flags=re.DOTALL | re.IGNORECASE)
            
    # 본문에 남은 미매칭 찌꺼기 태그 소거
    clean_content = re.sub(r'\[\s*THUMB\w*?PROMPT\s*\].*?\[/?\s*THUMB\w*?PROMPT\s*\]', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
    clean_content = re.sub(r'\[BODY_IMAGE_PROMPT\].*?\[/?BODY_IMAGE_PROMPT\]', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
    
    print("🚀 [진행 3/4] 마크다운 변환 및 구글 블로거 초안 전송 중...")
    html_content = markdown.markdown(clean_content, extensions=['extra', 'nl2br'])
    
    upload_success = blog_publisher.post_to_blogger(config['id'], final_topic, html_content, is_draft=True)
    
    if upload_success:
        print("💾 [진행 4/4] 데이터 업데이트 및 히스토리 깃헙 동기화 중...")
        file_manager.append_to_history(history_path, final_topic, clean_content)
        with open(titles_history_path, "a", encoding="utf-8") as f:
            f.write(f"- {final_topic}\n")
            
        # 원격 저장소 영구 동기화
        sync_text_to_github(history_path)
        sync_text_to_github(titles_history_path)
            
        print(f"✅ [{config['name']}] 포스팅 자동화 공정 완료!")
    else:
        print(f"❌ [{config['name']}] 업로드 실패.")

def main():
    print("========================================")
    print("🚀 완전 무인 멀티 채널 블로그 자동화 배치 시스템 (GitHub Actions 완전 대응)")
    print("========================================\n")
    
    # 🌟 깃허브 액션 환경 자동 감지 샌드박스 필터링
    if os.getenv("GITHUB_ACTIONS") == "true":
        print("🤖 [GitHub Actions 배치 환경 감지됨]: 키보드 입력을 건너뛰고 전 채널 연속 자동 기동을 시작합니다.")
        choice = "7"
    else:
        # PC에서 마우스/키보드로 직접 수동 실행할 때의 인터랙티브 선택기 유지
        for key, config in CHANNEL_CONFIG.items():
            print(f" {key}. {config['name']} ({config['lang']})")
        print(" 7. 🔥 전체 채널 연속 자동 포스팅 실행")
        
        while True:
            choice = input("\n👉 채널 번호를 선택하세요 (1~7): ").strip()
            if choice in CHANNEL_CONFIG or choice == "7":
                break
            print("❌ 잘못된 입력입니다. 1에서 7 사이의 번호를 선택해 주세요.")
        
    if choice == "7":
        print("\n📢 전 채널 연속 마스터 자동화를 시작합니다. 순차적으로 포스팅 공정이 진행됩니다.")
        for key in sorted(CHANNEL_CONFIG.keys()):
            try:
                run_auto_posting(key)
            except Exception as e:
                print(f"❌ {CHANNEL_CONFIG[key]['name']} 채널 진행 중 예외 발생: {e}")
        print("\n🎉 모든 채널의 자동 포스팅 배치 공정 완료!")
    else:
        run_auto_posting(choice)

if __name__ == "__main__":
    main()
