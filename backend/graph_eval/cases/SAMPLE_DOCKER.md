# 컨테이너 배포 정리

Docker는 컨테이너 기술의 대표적인 구현이다.
Docker는 Linux 커널의 cgroups와 namespaces를 사용해 프로세스를 격리한다.
Docker Compose는 여러 컨테이너를 한 번에 띄우는 도구로, Docker를 사용한다.
이 프로젝트에서는 Docker 버전 24를 쓴다.
이미지가 커서 배포가 느린 문제는 멀티 스테이지 빌드로 해결한다.
