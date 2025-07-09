# 网页转文档

这是一个 Python 自动化工具，用于网页中提取内容转换为 Markdown，然后翻译，并最终生成保留了原始格式的高质量 Word 文档。

# 使用

1. 首先将在线表格 https://docs.qq.com/sheet/DUEtjbUN6eEFCQUd3?tab=BB08J2 保存到 data 目录下，并命名为 task.xlsx。注意，从网络下载的 Word 文档默认会处于保护状态（编辑功能受限），需要打开之后另存为一下！

2. Markdown 转 Word 使用了 Pandoc，需要手动从 https://www.pandoc.org/ 下载安装，并确保环境变量中可以访问 Pandoc 命令

3. 通过 `pip install -r requirements.txt` 安装依赖包

4. 执行 `python main.py` 等待

# 问题

1. 目前使用的 selenium 库通过 Chrome 来请求页面，速度较慢。主要是因为 Deepwiki 网站很多动态资源是由 JS 来加载的，我们需要请求会动态 DOM 页面内容

2. 翻译过程比较慢。后续可以考虑多线程

3. 目前，Markdown 转 Word 不能正常处理 mermaid 图