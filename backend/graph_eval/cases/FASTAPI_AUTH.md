# FastAPI 인증 구조 메모

사내 도구 백엔드의 인증 구조를 정리한다. 서버는 FastAPI로 만들었고, FastAPI는 Python으로 작성된 웹 프레임워크다.

## 인증 흐름
- FastAPI는 OAuth2 password flow를 사용해 로그인을 처리한다.
- 토큰은 JWT 형식이다. 발급과 검증은 PyJWT가 구현한다.
- 비밀 키는 코드에 넣지 않고 .env의 환경변수로 읽는다.

## 토큰 만료 문제
access token 만료 시간을 15분으로 줄였더니 사용자가 자주 로그아웃되는 토큰 만료 문제가 생겼다. refresh token을 도입해서 토큰 만료 문제를 해결했다.

## 테스트
pytest로 로그인 성공, 잘못된 비밀번호, 만료된 토큰 케이스를 확인한다.
