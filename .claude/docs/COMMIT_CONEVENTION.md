# Git Commit Convention

## 커밋 메시지 형식

```
:[emoji]: [type] 메시지
```

### 예시

```
:sparkles: [feat] 새로운 로그인 기능 추가
:bug: [fix] 로그인 오류 수정
:memo: [docs] README 업데이트
```

---

## Type & Emoji 가이드

| Type | Emoji | 설명 | 예시 |
|------|-------|------|------|
| `feat` | `:sparkles:` ✨ | 새로운 기능 | 새 API 엔드포인트, 새 페이지 |
| `fix` | `:bug:` 🐛 | 버그 수정 | 오류 해결, 동작 수정 |
| `docs` | `:memo:` 📝 | 문서 변경 | README, 주석, API 문서 |
| `style` | `:art:` 🎨 | 코드 스타일 | 포맷팅, 세미콜론 추가 (로직 변경 X) |
| `refactor` | `:recycle:` ♻️ | 코드 리팩토링 | 기능 변경 없는 구조 개선 |
| `test` | `:white_check_mark:` ✅ | 테스트 | 테스트 추가/수정 |
| `chore` | `:wrench:` 🔧 | 기타 작업 | 설정 파일, 빌드 스크립트 |
| `perf` | `:zap:` ⚡ | 성능 개선 | 쿼리 최적화, 캐싱 |
| `ci` | `:construction_worker:` 👷 | CI/CD | GitHub Actions, 배포 설정 |
| `build` | `:package:` 📦 | 빌드 시스템 | 의존성 추가, 빌드 설정 |
| `revert` | `:rewind:` ⏪ | 되돌리기 | 이전 커밋 롤백 |

---

## 추가 이모지 (선택 사용)

| Emoji | 코드 | 용도 |
|-------|------|------|
| 🚀 | `:rocket:` | 배포 |
| 🔒 | `:lock:` | 보안 |
| 🗃️ | `:card_file_box:` | DB 관련 |
| 🌐 | `:globe_with_meridians:` | 국제화/번역 |
| 💄 | `:lipstick:` | UI/스타일 |
| 🔊 | `:loud_sound:` | 로깅 추가 |
| 🔇 | `:mute:` | 로깅 제거 |
| 🏗️ | `:building_construction:` | 아키텍처 변경 |
| 🚧 | `:construction:` | WIP (작업 중) |
| ⬆️ | `:arrow_up:` | 의존성 업그레이드 |
| ⬇️ | `:arrow_down:` | 의존성 다운그레이드 |
| 🔥 | `:fire:` | 코드/파일 삭제 |
| 🚚 | `:truck:` | 파일/폴더 이동/이름 변경 |

---

## 좋은 커밋 메시지 작성법

### DO ✅

```
:sparkles: [feat] 사용자 프로필 편집 기능 추가
:bug: [fix] 로그인 시 토큰 만료 처리 오류 수정
:recycle: [refactor] 인증 로직을 별도 서비스로 분리
```

### DON'T ❌

```
:sparkles: [feat] 기능 추가          # 너무 모호함
:bug: [fix] 버그 수정                # 무슨 버그인지 불명확
:wrench: [chore] 수정               # 무엇을 수정했는지 없음
```

---

## 브랜치 전략

| 브랜치 | 용도 |
|--------|------|
| `main` / `master` | 프로덕션 |
| `dev` / `develop` | 개발 통합 |
| `feature/*` | 기능 개발 |
| `fix/*` | 버그 수정 |
| `hotfix/*` | 긴급 수정 |

### 워크플로우

```
1. feature/xxx 브랜치 생성
2. 작업 및 커밋
3. dev로 PR 생성
4. 리뷰 후 머지
5. main으로 릴리즈
```

---

## Husky Hooks

| Hook | 역할 |
|------|------|
| `pre-commit` | main/master 직접 커밋 경고, 구조 문서 알림 |
| `commit-msg` | 커밋 메시지 형식 검증 |

### 설치

```bash
npm install  # Husky 자동 설치 (prepare 스크립트)
```

### Docker에서

`HUSKY=0` 환경 변수로 자동 비활성화됩니다.
