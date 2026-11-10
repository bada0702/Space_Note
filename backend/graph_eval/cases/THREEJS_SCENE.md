# Three.js 장면 성능 정리

시각화 화면에 오브젝트가 수천 개 올라가면서 프레임이 떨어졌다. 개선한 내용을 정리한다.

## 기본
Three.js는 WebGL을 사용하는 3D 라이브러리이고 JavaScript로 작성되어 있다. 우리 화면은 ES Modules로 불러온다.

## draw call 증가
같은 모양의 박스를 개별 Mesh로 만들어서 draw call 증가 문제가 있었다. Three.js에 포함된 InstancedMesh로 바꿔 draw call 증가 문제를 해결했다.

## 메모리 누수
장면을 여러 번 열고 닫으면 GPU 메모리가 계속 늘어나는 메모리 누수가 있었다. geometry와 material을 dispose로 정리해서 메모리 누수를 해결했다.

## 규칙
- 렌더 루프 안에서 객체를 새로 만들지 않는다
- 화면을 떠날 때 renderer.dispose()까지 호출한다
