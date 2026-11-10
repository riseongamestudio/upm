# RiseOn UPM

Registry UPM tĩnh chứa bản mirror các gói Unity của bên thứ ba. Tên và nội dung gói giữ nguyên như bên phát hành đưa ra:

- **Firebase:** cả 13 gói Google phát hành cho Unity, từ 13.17.0 trở đi, lấy từ tarball UPM của Google.
- **AppsFlyer:** `appsflyer-unity-plugin`, lấy từ nhánh `upm` của AppsFlyer.

Workflow `Mirror` chạy mỗi ngày và đưa các version mới lên; chạy tay bằng Actions > Mirror > Run workflow. Tarball nằm ở release của repo này, packument và file search nằm ở nhánh `registry`, phục vụ qua GitHub Pages.

## Dùng trong project

Thêm registry vào `Packages/manifest.json`, rồi khai báo gói theo version như gói Unity thường:

```json
"scopedRegistries": [
  {
    "name": "RiseOn",
    "url": "https://upm.riseongamestudio.com",
    "scopes": [ "com.google.firebase", "appsflyer-unity-plugin" ]
  }
]
```

```json
"com.google.firebase.analytics": "13.17.0",
"appsflyer-unity-plugin": "7.0.41"
```

Các gói Firebase phụ thuộc `com.google.external-dependency-manager`; gói này lấy từ OpenUPM, scope `com.google.external-dependency-manager`.
