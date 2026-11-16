# RiseOn UPM

Registry UPM tĩnh của RiseOn, gồm hai loại gói:

- **Gói của RiseOn** (`com.riseon.*`): đóng gói từ tag git của repo từng pack.
- **Bản mirror gói của bên thứ ba**, giữ nguyên tên và nội dung như bên phát hành đưa ra:
  - **Firebase:** cả 13 gói Google phát hành cho Unity, từ 13.17.0 trở đi, lấy từ tarball UPM của Google.
  - **AppsFlyer:** `appsflyer-unity-plugin`, lấy từ nhánh `upm` của AppsFlyer.

Workflow `Mirror` được lên lịch 5 phút một lần (GitHub có thể chạy trễ hoặc bỏ lượt); muốn có ngay thì chạy tay bằng Actions > Mirror > Run workflow.

## Dùng trong project

Thêm hai registry vào `Packages/manifest.json`, rồi khai báo gói theo version như gói Unity thường:

```json
"scopedRegistries": [
  {
    "name": "RiseOn",
    "url": "https://upm.riseongamestudio.com",
    "scopes": [ "com.riseon", "com.google.firebase", "appsflyer-unity-plugin" ]
  },
  {
    "name": "OpenUPM",
    "url": "https://package.openupm.com",
    "scopes": [ "com.cysharp", "com.annulusgames", "com.google" ]
  }
]
```

```json
"com.riseon.utils": "1.0.13",
"com.google.firebase.analytics": "13.17.0",
"appsflyer-unity-plugin": "7.0.41"
```

Mục OpenUPM là cho các gói mà pack RiseOn và Firebase phụ thuộc: UniTask, LitMotion, Google Mobile Ads, External Dependency Manager. Không khai `com.riseon` cho OpenUPM: mọi gói `com.riseon.*` lấy từ registry này. Unity chọn registry theo scope khớp dài nhất, nên `com.google.firebase` vẫn lấy từ đây dù OpenUPM khai `com.google`.

## Phát hành pack của RiseOn

| Repo | Tag |
|---|---|
| Một pack, ở gốc repo | `v<version>`, ví dụ `v1.0.2` |
| Nhiều pack, mỗi pack một thư mục | `<tên gói>/<version>`, ví dụ `com.riseon.utils/1.0.13` |

Phát hành một version: tăng `version` trong `package.json`, commit, push tag.

- Version gồm ba số, có thể kèm hậu tố pre-release, ví dụ `1.0.2` hoặc `1.1.0-preview.1`.
- Workflow chỉ đưa lên tag có `package.json` trùng tên gói và version, và version đúng dạng trên. Tag sai thì bị bỏ qua tới khi được dời sang commit khác; lý do in ra log của lượt chạy đầu tiên gặp tag đó, và tag nằm trong file `-/skipped` ở nhánh `registry`.
- Version đã lên registry thì không bao giờ bị ghi lại, kể cả khi tag bị dời: sửa bản đã phát hành thì tăng version rồi đặt tag mới.

## Tạo pack mới

1. Trên GitHub, tạo repo từ template [`riseongamestudio/PackageTemplate`](https://github.com/riseongamestudio/PackageTemplate) (*Use this template*): owner `riseongamestudio`, **Public** (registry chỉ đọc được repo public), tên repo là tên pack, ví dụ `Wipe2D`.
2. Clone về `D:\Unity\Projects\<tên repo>`, thay `PackageName` bằng tên repo và `packagename` bằng tên repo viết thường trong mọi file, đổi tên hai file asmdef (`Runtime/RiseOn.PackageName.asmdef`, `Editor/Requirements/RiseOn.PackageName.Requirements.asmdef`). Trong Git Bash, với repo `Wipe2D`:

   ```bash
   grep -rlI --exclude-dir=.git -e PackageName -e packagename . | xargs sed -i 's/PackageName/Wipe2D/g; s/packagename/wipe2d/g'
   git mv Runtime/RiseOn.PackageName.asmdef Runtime/RiseOn.Wipe2D.asmdef
   git mv Editor/Requirements/RiseOn.PackageName.Requirements.asmdef Editor/Requirements/RiseOn.Wipe2D.Requirements.asmdef
   ```

   Rồi viết `displayName`, `description` trong `package.json` và các mục còn để trống (có ghi chú `<!-- -->`) trong `README.md`, `CHANGELOG.md`.
3. Thêm `"com.riseon.<tên viết thường>": "file:D:/Unity/Projects/<tên repo>"` vào `Packages/manifest.json` của PackageSandbox rồi mở project đó: Unity sinh file `.meta` cho pack. Commit cả các file `.meta`. Template không chứa `.meta` để hai pack tạo từ nó không trùng GUID.
4. Thêm repo, tên gói và thư mục (để trống nếu gói ở gốc repo) vào `RISEON_REPOS` trong `mirror.py`, rồi push lên repo này. Pack không có trong `RISEON_REPOS` thì không bao giờ lên registry.
5. Phát hành như mục trên.
