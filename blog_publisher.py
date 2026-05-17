import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Blogger API 권한 설정 (읽기 및 쓰기 권한)
SCOPES = ['https://www.googleapis.com/auth/blogger']

def authenticate_blogger():
    """
    Blogger API OAuth 2.0 인증을 수행하고 서비스 객체를 반환합니다.
    최초 실행 시 브라우저가 열리며 구글 로그인 및 권한 승인이 필요합니다.
    """
    creds = None
    
    # 이전에 인증하여 저장해둔 토큰(token.pickle)이 있는지 확인
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
            
    # 토큰이 없거나 만료된 경우 새로 인증 프로세스 진행
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # 주의: 구글 클라우드 콘솔에서 다운받은 OAuth 2.0 클라이언트 보안 비밀 파일이 필요합니다.
            secret_file = 'client_secret.json'
            if not os.path.exists(secret_file):
                raise FileNotFoundError(
                    f"[{secret_file}] 파일이 없습니다! 구글 클라우드 콘솔(GCP)에서 "
                    "OAuth 2.0 클라이언트 ID를 생성하고 JSON 파일을 다운로드하여 "
                    "프로젝트 폴더에 'client_secret.json' 이름으로 저장해 주세요."
                )
            flow = InstalledAppFlow.from_client_secrets_file(secret_file, SCOPES)
            creds = flow.run_local_server(port=0)
            
        # 다음 실행 시 로그인을 생략하기 위해 인증된 토큰을 저장
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    # 인증된 정보로 Blogger 서비스 빌드
    service = build('blogger', 'v3', credentials=creds)
    return service

def post_to_blogger(blog_id, title, content_html, is_draft=True):
    """
    인증된 구글 계정의 특정 블로그에 글을 업로드합니다.
    """
    try:
        service = authenticate_blogger()
        
        # 포스팅할 데이터 구성
        body = {
            "title": title,
            "content": content_html
        }
        
        status = "초안(Draft)" if is_draft else "즉시 게시"
        print(f"Blogger 업로드 진행 중... [상태: {status}]")
        
        # API 호출하여 글 등록
        posts = service.posts()
        request = posts.insert(blogId=blog_id, body=body, isDraft=is_draft)
        response = request.execute()
        
        post_url = response.get('url', 'URL 없음(초안)')
        print(f"업로드 성공! 링크: {post_url}")
        return True
        
    except Exception as e:
        print(f"Blogger 업로드 중 오류 발생: {e}")
        return False