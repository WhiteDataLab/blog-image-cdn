import os
import datetime

# 🌟 대한민국 표준시(KST) 타임존 정의 (해외 클라우드 서버 시각 동기화용)
KST = datetime.timezone(datetime.timedelta(hours=9))

def read_markdown_file(file_path):
    """지정된 경로의 마크다운 파일을 읽어옵니다."""
    if not os.path.exists(file_path):
        print(f"경고: {file_path} 파일을 찾을 수 없습니다. 빈 텍스트로 처리합니다.")
        return ""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def append_to_history(file_path, title, content):
    """새로 작성된 포스팅을 히스토리 파일 하단에 누적합니다."""
    # 폴더가 없으면 생성
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # 🌟 미국 서버에서도 무조건 한국 시간 기준으로 히스토리 타임스탬프 생성
    today = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(f"\n\n---\n")
        f.write(f"## [{today}] {title}\n")
        f.write(f"{content}\n")
    print(f"[{file_path}] 히스토리 업데이트 완료!")
