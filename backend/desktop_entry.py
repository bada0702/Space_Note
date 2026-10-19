"""Windows 설치판(Tauri sidecar)용 백엔드 진입점. PyInstaller가 이 파일을 실행 파일로 묶는다."""
import os
import sys
import threading
from typing import Callable, TextIO

import uvicorn

HOST = "127.0.0.1"
PORT = 18001


def watch_parent(stream: TextIO | None = None, on_exit: Callable[[], None] = lambda: os._exit(0)) -> threading.Thread:
    """부모(Tauri)가 쥔 stdin 파이프가 닫히면(EOF) 종료한다.

    앱이 강제 종료·크래시되면 RunEvent::Exit의 kill이 실행되지 않아 백엔드가 18001을
    계속 점유하므로, OS가 파이프를 닫는 것을 신호로 스스로 종료한다.
    stdin을 읽을 수 없는 환경이면 감시하지 않는다.
    """
    src = sys.stdin if stream is None else stream

    def run() -> None:
        try:
            src.read()
        except (OSError, ValueError, AttributeError):
            return
        on_exit()

    t = threading.Thread(target=run, name="parent-watch", daemon=True)
    t.start()
    return t


def main() -> None:
    from main import app

    watch_parent()
    # PyInstaller 번들에서는 "main:app" 문자열 import가 동작하지 않아 app 객체를 직접 넘긴다
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
