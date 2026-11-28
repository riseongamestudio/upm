# RiseOn UPM

Registry UPM tĩnh của RiseOn. Repo này chỉ dựng chỉ mục, không chứa gói nào: mỗi gói nằm trong Release của repo phát hành ra nó.

| Nguồn | Gói | Release |
|---|---|---|
| Repo của từng pack RiseOn | `com.riseon.*` | Một Release cho mỗi tag, chứa `<tên gói>-<version>.tgz` |
| [FirebaseMirror](https://github.com/riseongamestudio/FirebaseMirror) | 13 gói `com.google.firebase.*`, mọi version Google còn cho tải | Một Release cho mỗi version Firebase |
| [AppsFlyerMirror](https://github.com/riseongamestudio/AppsFlyerMirror) | `appsflyer-unity-plugin` | Một Release cho mỗi version |

Workflow `Index` chạy ngay khi một repo pack hay repo mirror tạo Release, và theo lịch 5 phút một lần để chạy bù (GitHub thường chỉ chạy lịch này vài giờ một lần). Nó đọc Release của các repo trong `SOURCES` ở `index.py`, thêm version mới vào packument ở nhánh `registry`, rồi deploy GitHub Pages. Muốn có ngay thì chạy tay bằng Actions > Index > Run workflow.

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

Phát hành một version: tăng `version` trong `package.json`, commit, push tag. Workflow `Release` của repo pack (file `.github/workflows/release.yml`, gọi `pack-release.yml` của repo này) đóng gói thư mục của pack tại tag đó thành Release của repo pack. Xong, workflow đó gọi `Index` để đưa version lên registry. Push mỗi tag một lệnh `git push origin <tag>`: GitHub không tạo sự kiện nào khi một lần push có quá ba tag, nên workflow không chạy. Hai việc cần secret `UPM_INDEX_TOKEN` của tổ chức (fine-grained token, quyền Actions ghi trên repo này) và `secrets: inherit` trong `release.yml` của repo pack.

Mọi pack RiseOn đều cần Odin: mọi asmdef có `ODIN_INSPECTOR` trong `defineConstraints`, trừ assembly `*.Requirements` báo thiếu Odin. Trước khi push tag:

1. Trong thư mục repo, lệnh sau (Git Bash) không được in ra gì; mỗi dòng nó in là một asmdef còn thiếu `ODIN_INSPECTOR`:

   ```bash
   find . -name '*.asmdef' ! -name '*.Requirements.asmdef' -exec grep -L ODIN_INSPECTOR {} +
   ```

2. Thử pack trong một project mới không có Odin, cài pack đó bằng `file:` và các gói RiseOn khác từ registry (gói chưa phát hành thì cũng bằng `file:`). Console chỉ được có các lỗi `... needs Odin Inspector` từ những assembly `*.Requirements`. Còn lỗi khác, thường là CS0246 không tìm thấy kiểu của Sirenix hay của một assembly RiseOn, nghĩa là còn asmdef thiếu `ODIN_INSPECTOR`.

- Version gồm ba số, có thể kèm hậu tố pre-release, ví dụ `1.0.2` hoặc `1.1.0-preview.1`.
- Workflow `Release` chỉ phát hành tag có `package.json` trùng tên gói và version, và version đúng dạng trên. Tag sai thì lượt chạy đó báo lỗi trong tab Actions của repo pack và không tạo Release.
- Version đã lên registry thì không bao giờ bị ghi lại, kể cả khi tag bị dời hay file trong Release bị thay: sửa bản đã phát hành thì tăng version rồi đặt tag mới.

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
4. Thêm repo vào `SOURCES` trong `index.py`, rồi push lên repo này. Repo không có trong `SOURCES` thì không bao giờ lên registry. Workflow `Release` có sẵn trong template.
5. Phát hành như mục trên.
