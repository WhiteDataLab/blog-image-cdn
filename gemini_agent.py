import os
import re
import base64
import requests
import datetime
import time
import random  # 🌟 파일명 난수 생성을 위해 추가
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

# 🌟 Cloudflare Workers AI (무료 이미지 생성 엔진 - FLUX.1 schnell)
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CF_API_TOKEN")

# 🌟 대한민국 표준시(KST) 타임존 정의 (해외 클라우드 서버 대응용)
KST = datetime.timezone(datetime.timedelta(hours=9))

# 제미나이 텍스트 생성용 클라이언트 (무료 티어 활용)
client = genai.Client(api_key=GEMINI_API_KEY)


def _generate_with_retry(contents, config, what, max_retries=5):
    """Gemini 호출을 일시적 오류(503 과부하/429 등) 발생 시 지수 백오프로 재시도합니다.
    최종 실패 시 예외를 그대로 올려보내 호출부가 발행을 중단(가드)하도록 합니다."""
    transient_signals = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "500", "INTERNAL", "deadline")
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            return client.models.generate_content(
                model='gemini-2.5-flash', contents=contents, config=config
            )
        except Exception as e:
            last_err = e
            msg = str(e)
            is_transient = any(sig in msg for sig in transient_signals)
            if attempt < max_retries and is_transient:
                wait = min(2 ** attempt, 30)  # 2,4,8,16,30s
                print(f"   ⏳ [{what}] 일시 오류 감지 ({msg[:70]}...) → {attempt}/{max_retries}회차, {wait}초 후 재시도")
                time.sleep(wait)
                continue
            break
    raise last_err

def suggest_topics(brand_guide, titles_history, language="Korean"):
    """현재 시스템 연도를 동적으로 반영하고 과거 제목 DB를 대조하여 완전히 새로운 주제를 제안합니다."""
    # 🌟 한국 시간 기준으로 현재 연도 추출
    current_year = datetime.datetime.now(KST).year
    
    prompt = f"""
    당신은 전 세계 트렌드를 꿰뚫어 보는 천재 콘텐츠 기획자입니다.
    [브랜드 가이드]에 적힌 참조 사이트들의 가장 최신 뉴스나 트렌드를 구글 검색(Google Search)으로 파악한 뒤, 해당 채널에 올리기 가장 좋은 매력적인 블로그 글 주제 4가지를 제안해 주세요.
    
    [시점 제약 조건]
    현재 시점은 {current_year}년입니다. 과거 연도(2025년 등)의 데이터나 지나간 트렌드는 절대 제외하고, 오직 {current_year}년 최신 정보에만 집중하세요.

    [핵심 제약 조건 - 중복 절대 금지]
    Below provided [과거 발행된 글 제목 리스트]는 이 블로그에 이미 포스팅된 글들의 제목입니다.
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
        response = _generate_with_retry(
            contents=prompt,
            config=types.GenerateContentConfig(tools=[{"google_search": {}}], temperature=0.5),
            what="주제 추천",
        )
        return response.text.strip().split('\n')
    except Exception as e:
        # 재시도까지 모두 실패하면 가짜 주제로 발행하지 않고 빈 리스트 반환 → 호출부가 채널을 건너뜀
        print(f"❌ 주제 추천 최종 실패 (재시도 소진): {e}")
        return []


def generate_blog_content(topic, brand_guide, titles_history, language="Korean"):
    """브랜드 가이드와 과거 제목 DB를 읽고, 인물이 배제된 이미지 프롬프트와 명품 포스팅을 생성합니다."""
    # 🌟 한국 시간 기준으로 현재 연도 추출
    current_year = datetime.datetime.now(KST).year
    
    prompt = f"""
    당신은 글로벌 톱클래스 블로그 에디터입니다. 제시된 주제 "{topic}"에 대한 명품 블로그 글을 작성해 주세요.
    반드시 구글 검색(Google Search)을 활용하여 이 주제와 관련된 최신 뉴스, 구체적인 수치 데이터, 트렌드를 찾아 본문에 풍부하게 반영하세요.

    [핵심 지시사항 - 매우 엄격함]
    1. STRICTLY GENERATE ONLY ONE POST: 단 한 편의 글만 작성하세요. 결론이 끝나면 즉시 출력을 중단하고 절대 하단에 동일한 내용이나 다른 버전의 글을 반복하여 출력하지 마세요.
    2. 현재 시점은 {current_year}년입니다. 본문 전반에 걸쳐 과거 연도를 언급하거나 시점을 잡지 말고, 오직 {current_year}년 기준으로 시점을 전개하세요.
    3. 아래 제공되는 [과거 발행된 글 제목 리스트]를 참고하여, 기존에 다뤘던 내용과 중복되지 않도록 새롭고 차별화된 관점으로 쓰세요.
    4. [브랜드 가이드]에 명시된 페르소나, 말투(Tone & Manner), 타겟 독자의 취향을 철저히 반영하세요.
    5. 구조는 Markdown 형식(H2, H3 소제목, 글머리 기호 등)을 사용하여 가독성 있게 작성하세요.
    
    🖼️ [이미지 프롬프트 생성 규칙]
    - 글 맨 앞부분에 썸네일용 이미지 프롬프트 1개를 [THUMBNAIL_PROMPT]영문[/THUMBNAIL_PROMPT] 형태로 감싸주세요.
    - 글 본문 중간중간 맥락과 어울리는 본문용 이미지 프롬프트를 3~4개 기획하여 [BODY_IMAGE_PROMPT]영문[/BODY_IMAGE_PROMPT] 형태로 분산 배치해 주세요.
    - 주제와 맥락에 맞다면 인물(사람)이 등장하는 장면도 자유롭게 묘사해도 됩니다. 단, 자연스럽고 사실적인 고품질 묘사를 지향하세요.
    - 인물이 어울리지 않는 맥락에서는 주제를 상징하는 세련된 사물, 3D 가상 그래픽, 홀로그램 차트, 미니멀한 테크 기기 단독 샷, 자연 풍경, 타이포그래피, 네온 개념 아트 등으로 표현하세요.
    
    작성 언어: {language}

    [브랜드 가이드]
    {brand_guide}

    [과거 발행된 글 제목 리스트]
    {titles_history}
    """

    try:
        response = _generate_with_retry(
            contents=prompt,
            config=types.GenerateContentConfig(tools=[{"google_search": {}}], temperature=0.5),
            what="본문 생성",
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
        # 재시도까지 모두 실패하면 None 반환 → 호출부가 "오류 초안" 발행을 중단함
        print(f"❌ 본문 생성 최종 실패 (재시도 소진): {e}")
        return None


def extract_and_format_prompts(content):
    """
    본문에서 썸네일 및 본문 이미지 프롬프트를 정규식으로 추출합니다.
    🌟 AI의 오타(예: THUMBNANAIL)도 잡아내도록 유연한 정규식으로 개선!
    """
    
    # --- [수정] 썸네일 정규식 유연화 ---
    # THUMB와 NAIL 사이에 어떤 문자가 와도, 심지어 NAIL이 빠져도 THUMB...PROMPT 구조면 잡아냅니다.
    # 예) THUMBNAIL, THUMBNANAIL, THUMB_PROMPT 모두 매칭 성공
    thumb_fuzzy_pattern = r'\[\s*THUMB\w*?PROMPT\s*\](.*?)\[/?\s*THUMB\w*?PROMPT\s*\]'
    thumbnail_match = re.search(thumb_fuzzy_pattern, content, re.DOTALL | re.IGNORECASE)
    thumbnail_prompt = thumbnail_match.group(1).strip() if thumbnail_match else ""
    
    # --- 본문 이미지 정규식 (기존 유지) ---
    body_pattern = r'\[BODY_IMAGE_PROMPT\](.*?)\[/?BODY_IMAGE_PROMPT\]'
    body_matches = re.finditer(body_pattern, content, re.DOTALL | re.IGNORECASE)
    body_prompts = [match.group(1).strip() for match in body_matches]
    
    return thumbnail_prompt, body_prompts

def upload_to_github(image_path, file_name):
    """로컬 이미지를 내 GitHub 저장소에 업로드하고 영구 퍼블릭 URL을 반환합니다."""
    if not all([GITHUB_TOKEN, GITHUB_USERNAME, GITHUB_REPO]):
        print("❌ GitHub 설정이 누락되었습니다 (.env 파일을 확인해 주세요).")
        return ""
        
    # 🌟 한국 시간 기준으로 깃허브 저장 폴더 경로 생성
    now = datetime.datetime.now(KST)
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
    무료 이미지 인프라(Cloudflare Workers AI - FLUX.1 schnell) 연동 모듈.
    인물 생성을 강제로 차단하는 안전 프롬프트 필터(No People) 내장.
    """
    os.makedirs(output_dir, exist_ok=True)
    image_urls = {"thumbnail": "", "body": []}

    if not all([CF_ACCOUNT_ID, CF_API_TOKEN]):
        print("   ⚠️ Cloudflare 설정(CF_ACCOUNT_ID/CF_API_TOKEN) 누락으로 이미지 생성을 건너뜁니다.")
        return image_urls

    cf_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    cf_headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}

    def fetch_free_flux_image(prompt, prefix, index=""):
        print(f"🎨 무료 이미지 엔진 구동 중 (Cloudflare FLUX.1 schnell): {prefix} {index}")

        refined_prompt = prompt + ", high quality, photorealistic, detailed, cinematic lighting, 4k resolution"

        # 🌟 1. 한국 시간(KST) 기준 연월일_시분초 타임스탬프 생성
        now_kst = datetime.datetime.now(KST)
        timestamp = now_kst.strftime("%Y%m%d_%H%M%S")

        # 🌟 2. 0.01초 사이 대량 생성 시 파일명 충돌을 방지하기 위한 4자리 고유 난수 결합
        rand_id = random.randint(1000, 9999)

        # 🌟 3. 최종 고유 파일명 조립
        if index:
            file_name = f"{prefix}_{index}_{timestamp}_{rand_id}.jpg"
        else:
            file_name = f"{prefix}_{timestamp}_{rand_id}.jpg"

        file_path = os.path.join(output_dir, file_name)

        # 일시적 오류(429/5xx) 대비 최대 3회 재시도
        for attempt in range(1, 4):
            try:
                resp = requests.post(
                    cf_url, headers=cf_headers,
                    json={"prompt": refined_prompt, "steps": 6},
                    timeout=120,
                )
                if resp.status_code != 200:
                    print(f"   ⚠️ Cloudflare 응답 오류 {resp.status_code}: {resp.text[:120]}")
                    if resp.status_code in (429, 500, 502, 503) and attempt < 3:
                        time.sleep(2 ** attempt)
                        continue
                    return ""

                # Cloudflare는 result.image 에 base64(JPEG) 문자열로 반환
                b64_img = resp.json().get("result", {}).get("image", "")
                if not b64_img:
                    print("   ❌ 응답에 이미지 데이터가 없습니다.")
                    return ""

                image_bytes = base64.b64decode(b64_img)
                with open(file_path, "wb") as f:
                    f.write(image_bytes)
                print(f"   ✅ 무인물 이미지 저장 완료: {file_name}")

                github_url = upload_to_github(file_path, file_name)
                return github_url or ""
            except Exception as e:
                print(f"   ❌ 이미지 생성 실패 또는 지연: {e}")
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
        return ""

    if thumbnail_prompt:
        image_urls["thumbnail"] = fetch_free_flux_image(thumbnail_prompt, "thumbnail")
        
    for i, prompt in enumerate(body_prompts):
        url = fetch_free_flux_image(prompt, "body", i+1)
        if url:
            image_urls["body"].append(url)
            
    return image_urls
