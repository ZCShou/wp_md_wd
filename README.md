# 网页转文档

这是一个 Python 自动化工具，用于 Deepwiki 网页内容转换为 Markdown，然后翻译，并最终生成保留了原始格式的高质量 Word 文档。

# 使用

1. 首先将在线表格 https://docs.qq.com/sheet/DUEtjbUN6eEFCQUd3?tab=BB08J2 保存到 data 目录下，并命名为 task.xlsx。

   > 注意，从网络下载的 Word 文档默认会处于保护状态（编辑功能受限），需要打开之后另存为一下！

2. Markdown 转 Word 使用了 Pandoc 这个工具，需要手动从 https://www.pandoc.org/ 下载安装，并确保环境变量中可以访问 Pandoc 命令。

3. 由于 Pandoc 默认并不支持 mermaid，我们需要使用 mermaid-filter 来处理 Markdown 中的 mermaid 图表。而 mermaid-filter 是一个 Node.js 的包，因此需要安装 Node.js 环境，然后执行 `npm install --global mermaid-filter` 来进行安装

4. 通过 `pip install -r requirements.txt` 安装依赖包

5. 翻译使用的是 Deepseek API 需要修改 `main.py` 中的 `DEEPSEEK_API_KEY` 为自己的 KEY

6. 执行 `python main.py` 等待

# 问题

1. 目前使用的 selenium 库通过 Chrome 来请求页面，速度较慢。主要是因为 Deepwiki 网站很多动态资源是由 JS 来加载的，我们需要请求回动态 DOM 页面内容然后解析

2. 翻译过程比较慢。后续可以考虑多线程
