import os
import re
import base64
import requests
import datetime
import time
import urllib.parse
import urllib.request
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_REPO = os.getenv("GITHUB_REPO")

# 제미나이 텍스트 생성용 클라이언트 (무료 티어 활용)
client = genai.Client(api_key=GEMINI_API_KEY)

def suggest_topics(brand_guide, titles_history, language="Korean"):
    """현재 시스템 연도를 동적으로 반영하고 과거 제목 DB를 대조하여 완전히 새로운 주제를 제안합니다."""
    current_year = datetime.datetime.now().year
    
    prompt = f"""
    당신은 전 세계 트렌드를 꿰뚫어 보는 천재 콘텐츠 기획자입니다.
    [브랜드 가이드]에 적힌 참조 사이트들의 가장 최신 뉴스나 트렌드를 구글 검색(Google Search)으로 파악한 뒤, 해당 채널에 올리기 가장 좋은 매력적인 블로그 글 주제 4가지를 제안해 주세요.
    
    [시점 제약 조건]
    현재 시점은 {current_year}년입니다. 과거 연도(2025년 등)의 데이터나 지나간 트렌드는 절대 제외하고, 오직 {current_year}년 최신 정보에만 집중하세요.

    [핵심 제약 조건 - 중복 절대 금지]
    아래 제공되는 [과거 발행된 글 제목 리스트]는 이 블로그에 이미 포스팅된 글들의 제목입니다.
    1. 이 리스트에 등장하는 핵심 키워드나 주요 소재와 유사하거나 겹치는 주제는 절대로 제안하지 마세요.
    2. 완전히 새로운 도메인, 차별화된 관점, 기존 글의 연장선이 아닌 신선한 테마의 주제 4가지를 기획하세요.

    응답은 반드시 부연 설명이나 인사말 없이 1부터 4까지의 번호 매기기 목록으로만 출력하세요.
    작성 언어: {language}
    
    [브랜드 가이드]
    {brand_guide}

    [과거 발행된 글 제목 리스트]
    {titles_history}
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(tools=[{"google_search": {}}], temperature=0.5)
        )
        return response.text.strip().split('\n')
    except Exception as e:
        print(f"❌ 주제 추천 실패: {e}")
        return ["1. 최신 테크 및 비즈니스 트렌드 분석"]


def generate_blog_content(topic, brand_guide, titles_history, language="Korean"):
    """브랜드 가이드와 과거 제목 DB를 읽고, 인물이 배제된 이미지 프롬프트와 명품 포스팅을 생성합니다."""
    current_year = datetime.datetime.now().year
    
    prompt = f"""
    당신은 글로벌 톱클래스 블로그 에디터입니다. 제시된 주제 "{topic}"에 대한 명품 블로그 글을 작성해 주세요.
    반드시 구글 검색(Google Search)을 활용하여 이 주제와 관련된 최신 뉴스, 구체적인 수치 데이터, 트렌드를 찾아 본문에 풍부하게 반영하세요.

    [핵심 지시사항 - 매우 엄격함]
    1. STRICTLY GENERATE ONLY ONE POST: 단 한 편의 글만 작성하세요. 결론이 끝나면 즉시 출력을 중단하고 절대 하단에 동일한 내용이나 다른 버전의 글을 반복하여 출력하지 마세요.
    2. 현재 시점은 {current_year}년입니다. 본문 전반에 걸쳐 과거 연도를 언급하거나 시점을 잡지 말고, 오직 {current_year}년 기준으로 시점을 전개하세요.
    3. 아래 제공되는 [과거 발행된 글 제목 리스트]를 참고하여, 기존에 다뤘던 내용과 중복되지 않도록 새롭고 차별화된 관점으로 쓰세요.
    4. [브랜드 가이드]에 명시된 페르소나, 말투(Tone & Manner), 타겟 독자의 취향을 철저히 반영하세요.
    5. 구조는 Markdown 형식(H2, H3 소제목, 글머리 기호 등)을 사용하여 가독성 있게 작성하세요.
    
    🚨 [이미지 프롬프트 생성 규칙 - 기괴함 방지 필터]
    - 글 맨 앞부분에 썸네일용 이미지 프롬프트 1개를 [THUMBNAIL_PROMPT]영문[/THUMBNAIL_PROMPT] 형태로 감싸주세요.
    - 글 본문 중간중간 맥락과 어울리는 본문용 이미지 프롬프트를 3~4개 기획하여 [BODY_IMAGE_PROMPT]영문[/BODY_IMAGE_PROMPT] 형태로 분산 배치해 주세요.
    - CRITICAL WARNING: 모든 영문 이미지 프롬프트에는 인간(Human, Person, Woman, Man, Face, Hands, Crowd 등)이 절대 포함되어서는 안 됩니다. 사람이 포함되면 렌더링 에러가 납니다.
    - 대신 주제를 상징하는 세련된 사물, 3D 가상 그래픽, 홀로그램 차트, 미니멀한 테크 기기 단독 샷, 자연 풍경, 타이포그래피 또는 네온 개념 아트 위주로만 프롬프트를 영문으로 묘사하세요.
    
    작성 언어: {language}

    [브랜드 가이드]
    {brand_guide}

    [과거 발행된 글 제목 리스트]
    {titles_history}
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(tools=[{"google_search": {}}], temperature=0.5)
        )
        
        content = response.text
        lines = content.split('\n')
        if len(lines) > 10:
            title_line = lines[0].strip()
            for idx, line in enumerate(lines[1:], start=1):
                if title_line in line.strip() and len(line.strip()) > 10:
                    content = '\n'.join(lines[:idx])
                    break
                    
        return content
    except Exception as e:
        print(f"❌ 본문 생성 에러: {e}")
        return f"## {topic}\n본문 생성 도중 오류가 발생했습니다."


def extract_and_format_prompts(content):
    """본문에서 썸네일 및 본문 이미지 프롬프트를 정규식으로 추출합니다."""
    # 🌟 /? 를 추가하여 AI가 닫는 태그의 슬래시를 누락해도 정상적으로 추출하도록 방어 로직 추가
    thumbnail_match = re.search(r'\[THUMBNAIL_PROMPT\](.*?)\[/?THUMBNAIL_PROMPT\]', content, re.DOTALL | re.IGNORECASE)
    thumbnail_prompt = thumbnail_match.group(1).strip() if thumbnail_match else ""
    
    body_matches = re.finditer(r'\[BODY_IMAGE_PROMPT\](.*?)\[/?BODY_IMAGE_PROMPT\]', content, re.DOTALL | re.IGNORECASE)
    body_prompts = [match.group(1).strip() for match in body_matches]
    
    return thumbnail_prompt, body_prompts

def upload_to_github(image_path, file_name):
    """로컬 이미지를 내 GitHub 저장소에 업로드하고 영구 퍼블릭 URL을 반환합니다."""
    if not all([GITHUB_TOKEN, GITHUB_USERNAME, GITHUB_REPO]):
        print("❌ GitHub 설정이 누락되었습니다 (.env 파일을 확인해 주세요).")
        return ""
        
    now = datetime.datetime.now()
    github_path = f"images/{now.year}/{now.month:02d}/{file_name}"
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{github_path}"
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        with open(image_path, "rb") as file:
            content = base64.b64encode(file.read()).decode('utf-8')
            
        data = {
            "message": f"Auto-upload: {file_name}",
            "content": content
        }
        
        response = requests.put(url, headers=headers, json=data)
        if response.status_code in [200, 201]:
            return f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO}/main/{github_path}"
        else:
            print(f"❌ GitHub 업로드 에러: {response.text}")
            return ""
    except Exception as e:
        print(f"❌ GitHub API 연동 실패: {e}")
        return ""


def generate_official_images(thumbnail_prompt, body_prompts, output_dir):
    """
    100% 무료 초고품질 퍼블릭 인프라(FLUX 엔진) 우회 모듈.
    인물 생성을 강제로 차단하는 안전 프롬프트 필터(No People) 내장.
    """
    os.makedirs(output_dir, exist_ok=True)
    image_urls = {"thumbnail": "", "body": []}

    def fetch_free_flux_image(prompt, prefix, index=""):
        print(f"🎨 비용 0원 오브젝트 엔진 구동 중 (FLUX v1): {prefix} {index}")
        
        # 🌟 2중 안전 장치: 프롬프트에 인물 배제용 부정 명령어 강제 삽입 및 스타일 튜닝
        refined_prompt = prompt + ", no people, no human, no face, no hands, vector graphic illustration, clean tech aesthetic, cinematic lighting, 4k resolution"
        
        encoded_prompt = urllib.parse.quote(refined_prompt)
        target_url = f"https://image.pollinations.ai/p/{encoded_prompt}?width=1024&height=576&nologo=true&model=flux"
        
        timestamp = datetime.datetime.now().strftime("%H%M%S")
        file_name = f"{prefix}_{index}_{timestamp}.jpg" if index else f"{prefix}_{timestamp}.jpg"
        file_path = os.path.join(output_dir, file_name)
        
        req = urllib.request.Request(
            target_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        
        try:
            time.sleep(3)
            with urllib.request.urlopen(req, timeout=90) as response:
                image_bytes = response.read()
                
            with open(file_path, "wb") as f:
                f.write(image_bytes)
            print(f"   ✅ 무인물 이미지 저장 완료: {file_name}")
            
            github_url = upload_to_github(file_path, file_name)
            if github_url:
                return github_url
        except Exception as e:
            print(f"   ❌ 이미지 생성 실패 또는 지연: {e}")
        return ""

    if thumbnail_prompt:
        image_urls["thumbnail"] = fetch_free_flux_image(thumbnail_prompt, "thumbnail")
        
    for i, prompt in enumerate(body_prompts):
        url = fetch_free_flux_image(prompt, "body", i+1)
        if url:
            image_urls["body"].append(url)
            
    return image_urls