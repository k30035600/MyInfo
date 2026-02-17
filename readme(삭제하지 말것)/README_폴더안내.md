# readme(삭제하지 말것) 폴더 안내

이 폴더는 **참고 문서·가이드·유틸 스크립트**를 모아 둔 곳입니다. 삭제하지 마세요.

## 문서 (.md)

- **파일_정리_가이드.md** — 프로젝트 파일 구조, 유틸 위치, 정리 이력
- **category_통합_가이드.md** — category.* 통합 가능성 (HTML/Python)
- **코드_개선_조언.md**, **category_table_xlsx_복구.md**, **category_create.md** 등 — 각 주제별 참고

## 유틸 스크립트 (필요 시 실행)

| 파일 | 용도 | 실행 예 |
|------|------|---------|
| setup-git-utf8.ps1 | Git UTF-8 설정 | `.\readme(삭제하지 말것)\setup-git-utf8.ps1` |
| create-workspace-junction.ps1 | C:\CursorWorkspace 정션 | `.\readme(삭제하지 말것)\create-workspace-junction.ps1` |
| start-cursor-no-hangul.ps1 | Cursor 한글 경로 오류 시 | `.\readme(삭제하지 말것)\start-cursor-no-hangul.ps1` |
| export_category_table_to_xlsx.py | category_table → xlsx | 프로젝트 루트에서 `python "readme(삭제하지 말것)/export_category_table_to_xlsx.py"` |
| add_virtual_asset_category.py | 가상자산 목록 추가 | 프로젝트 루트에서 `python "readme(삭제하지 말것)/add_virtual_asset_category.py"` |

자세한 내용은 **파일_정리_가이드.md**를 보세요.
