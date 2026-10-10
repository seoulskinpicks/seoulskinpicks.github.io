# 성분 글 표지 사진 보관함

`<성분 id>.jpg` 이름으로 올리면 그 성분 글 표지에 자동으로 들어가요 (예: `niacinamide.jpg`).
성분 id는 content/ 폴더의 성분 목록의 `id` 값이에요.

- 세로 사진(4:5 이상)이 가장 예뻐요. 글자는 아래쪽에 올라가니 위쪽에 볼거리가 있으면 좋아요.
- AI로 만든 이미지는 `credits.json`에 표시해 두면 캡션에 "Image created with AI"가 자동으로 붙어요.

```json
{ "niacinamide": { "credit": "", "ai": true } }
```
