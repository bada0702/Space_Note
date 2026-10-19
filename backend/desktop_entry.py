"""Windows 설치판(Tauri sidecar)용 백엔드 진입점. PyInstaller가 이 파일을 실행 파일로 묶는다."""
import uvicorn

HOST = "127.0.0.1"
PORT = 18001


def main() -> None:
    from main import app

    # PyInstaller 번들에서는 "main:app" 문자열 import가 동작하지 않아 app 객체를 직접 넘긴다
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
