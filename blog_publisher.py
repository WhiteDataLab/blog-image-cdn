import os
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/blogger']

def get_blogger_service():
    """스트림릿 클라우드의 Secrets 환경변수로부터 토큰을 읽어 브라우저 없이 인증하는 모듈"""
    creds = None
    
    # 1. 스트림릿 클라우드 환경 변수(Secrets) 확인
    token_env = os.getenv("BLOGGER_TOKEN_JSON")
    
    if token_env:
        try:
            info = json.loads(token_env)
            creds = Credentials.from_authorized_user_info(info, SCOPES)
            print("☁️ [인증 완료] Streamlit Cloud Secrets로부터 구글 블로거 토큰을 로드했습니다.")
        except Exception as e:
            print(f"⚠️ 환경 변수 토큰 로드 실패: {e}")
            
    # 2. 로컬 PC 테스트 환경용 백업 (폴더 내에 token.json이 남아있을 때 작동)
    if not creds and os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        print("💻 [인증 완료] 로컬 token.json 파일로부터 토큰을 로드했습니다.")

    # 3. 만약 토큰 유효기간이 만료되었다면 자동으로 백그라운드 갱신(Refresh)
    if creds and creds.expired and creds.refresh_token:
        try:
            print("🔄 구글 토큰이 만료되어 백그라운드에서 자동 재발행(Refresh)을 시도합니다...")
            creds.refresh(Request())
        except Exception as e:
            print(f"❌ 토큰 자동 갱신 실패: {e}")
            creds = None

    if not creds:
        raise Exception("❌ 인증 토큰(BLOGGER_TOKEN_JSON)이 없습니다. 스트림릿 Secrets 설정을 확인해 주세요.")

    return build('blogger', 'v3', credentials=creds)

def post_to_blogger(blog_id, title, content, is_draft=True):
    """구글 블로거에 본문을 안전하게 업로드합니다."""
    try:
        print("📌 구글 블로거 API 연결 수립 중...")
        service = get_blogger_service()
        
        body = {
            "kind": "blogger#post",
            "title": title,
            "content": content
        }
        
        print(f"📤 블로그 전송 중... [상태: {'초안' if is_draft else '즉시발행'}]")
        request = service.posts().insert(blogId=blog_id, body=body, isDraft=is_draft)
        response = request.execute()
        
        print(f"✅ 구글 블로거 업로드 완료! 포스팅 고유 ID: {response.get('id')}")
        return True
        
    except Exception as e:
        print(f"❌ 구글 블로거 API 연동 실패 원인: {e}")
        return False
