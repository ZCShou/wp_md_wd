#!/usr/bin/env python3
import os
import re
import pandas as pd
import pypandoc
from code.deepwiki2markdown import deepwiki2markdown
from code.translationmarkdown import MarkdownTranslator
from code.printf import printf

# 定义 DeepSeek API 密钥
DEEPSEEK_API_KEY = ''

def main():
    printf(">>> DeepWiki 页面 ➜  Markdown ➜  翻译 ➜  Word <<<")
    
    directories = [
        'data/files_markdown',
        'data/files_markdown_translated',
        'data/files_word'
    ]
    for dir_path in directories:
        os.makedirs(dir_path, exist_ok=True)

    printf(f"\n开始提取 Excel 中的链接...")
    df = pd.read_excel('data/task.xlsx')
    col_idx = sum((ord(c.upper()) - 64) * 26 ** i for i, c in enumerate(reversed('D'))) - 1
    column_data = df.values[: , col_idx]
    url_pattern = re.compile(r'https?://[^\s]+')
    urls = {url for url in map(str, column_data) if url_pattern.match(url)}     # 这里将自动过滤重复的内容
    printf(f"成功获取 {len(urls)} 个 URL！")
    
    printf(f"\n开始依次提取 URL 页面内容...")
    markdown_num = 0
    for url in urls:
        printf(f"提取: {url}")
        deepwiki2markdown(url, 'data/files_markdown')
        markdown_num += 1
    printf(f"成功提取 {markdown_num} 个 URL 页面内容！")
    
    printf(f"\n开始翻译 Markdown 文件...")
    translated_num = 0
    for root, _, files in os.walk('data/files_markdown'):
        for file in files:
            if file.endswith('.md'):
                src_path = os.path.join(root, file)
                rel_path = os.path.relpath(src_path, 'data/files_markdown')
                dst_path = os.path.join('data/files_markdown_translated', rel_path)
                
                # 正确处理目标目录创建（包括根目录情况）
                dst_dir = os.path.dirname(dst_path)
                if dst_dir:  # 只有当目标路径包含目录时才创建
                    os.makedirs(dst_dir, exist_ok=True)
                
                printf(f"翻译: {src_path}")
                try:
                    with open(src_path, 'r', encoding='utf-8') as f_in, \
                         open(dst_path, 'w', encoding='utf-8') as f_out:
                        translator = MarkdownTranslator(DEEPSEEK_API_KEY)
                        f_out.write(translator.translate_markdown(f_in.read()))
                    translated_num += 1
                    printf(f"保存: {dst_path}")
                except Exception as e:
                    printf(f"翻译 {src_path} 出错: {e}")
    printf(f"成功翻译 {translated_num} 个 Markdown 文件！")

    printf(f"\n开始转换为 Word 文档...")
    word_num = 0
    for root, _, files in os.walk('data/files_markdown_translated'):
        for file in files:
            if file.endswith('.md'):
                src_path = os.path.join(root, file)
                rel_path = os.path.relpath(src_path, 'data/files_markdown_translated')
                dst_path = os.path.join('data/files_word', rel_path)
                
                # 正确处理目标目录创建（包括根目录情况）
                dst_dir = os.path.dirname(dst_path)
                if dst_dir:  # 只有当目标路径包含目录时才创建
                    os.makedirs(dst_dir, exist_ok=True)
                
                printf(f"转换: {src_path}")
                dst_path = dst_path.removesuffix('.md').removesuffix('.markdown') + '.docx' if dst_path.endswith(('.md', '.markdown')) else dst_path
                if os.name == 'nt':
                    mermaid_filter = 'mermaid-filter.cmd'
                else:
                    mermaid_filter = 'mermaid-filter'
                pypandoc.convert_file(src_path, 'docx', outputfile=dst_path, filters=mermaid_filter, format='markdown')
                printf(f"保存: {dst_path}")
                word_num += 1
    printf(f"成功转换 {word_num} 个 Word 文件！")

if __name__ == "__main__":
    main()
