# Security

## 必须关注
- SQL Injection
- XSS / CSRF
- JWT 泄露
- 密码泄露
- 越权/IDOR
- 文件上传漏洞
- 路径穿越
- 暴力登录
- 接口刷请求
- 敏感日志泄露

## 认证与授权
Authentication != Authorization。
有效 Token 不代表拥有目标资源权限。访问 Task 必须验证 User -> Team -> Project -> Task 链路。

## 文件
限制大小、校验 MIME、处理安全文件名、阻止路径穿越、下载时检查任务访问权限。

## Secret
真实密码、JWT Secret、API Key 不得提交到仓库。

## 日志
禁止记录 password、access_token、refresh_token 和完整敏感信息。
