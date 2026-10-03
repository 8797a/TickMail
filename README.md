# TickMail

TickMail 是一款基于 Python 和 Tkinter 的 EmailTick 临时邮箱客户端，支持切换邮箱、检测邮件、自动轮询验证码、提取验证码并复制到剪贴板。

## 主要功能

- 自动获取 EmailTick 临时邮箱
- 支持切换不同类型的邮箱地址
- 检测并显示收件箱邮件
- 自动轮询新邮件
- 从邮件标题或正文提取验证码
- 自动将验证码复制到剪贴板
- 支持按邮件标题关键词过滤
- 同时提供图形界面和命令行模式

## 使用要求

- Python 3.9 或更高版本
- Windows、macOS 或 Linux
- 可正常访问 EmailTick

## 安装

```bash
pip install -r requirements.txt
```

## 运行图形界面

```bash
python emailtick_gui.py
```

Windows 用户也可以双击：

```text
run_emailtick_gui.bat
```

## 运行命令行版本

```bash
python emailtick_code_reader.py
```

常用参数：

```text
--interval 秒数       设置轮询间隔
--attempts 次数       设置最大轮询次数，0 表示持续等待
--subject 关键词      只读取标题包含关键词的邮件
--new                 启动后切换到新邮箱
--reuse               继续使用当前会话邮箱
--type 1|2|3          选择邮箱地址类型
--no-pause            结束后不等待按键
```

## 注意事项

本项目通过 EmailTick 网页会话工作，功能可能受到第三方网站改版、访问频率限制或网络环境影响。请合理控制检测频率，并遵守相关网站的服务条款。
