# Media Brief

선택한 기간 동안 매체별 주요 아티클을 모아 보는 읽기 전용 UI.

## 실행

`lgbr-api`가 `127.0.0.1:8787`에서 떠 있어야 합니다. 인증·API 키는 레포 루트 `.env`의 `LGBR_API_KEY`, `LGBR_UI_USER`, `LGBR_UI_PASSWORD`를 사용합니다.

```bash
cd frontend/media-brief
pnpm install
pnpm dev
```

브라우저: [http://127.0.0.1:8002](http://127.0.0.1:8002)
