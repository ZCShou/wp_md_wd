#!/usr/bin/env python3
import os
import requests
import re
import pandas as pd
from code.deepwiki2markdown import deepwiki2markdown
from code.translationmarkdown import translate_markdown
from code.markdown2word import markdown2word
from code.printf import printf

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
    try:
        df = pd.read_excel('data/task.xlsx')
        col_idx = sum((ord(c.upper()) - 64) * 26 ** i for i, c in enumerate(reversed('D'))) - 1
        column_data = df.values[: , col_idx]
        url_pattern = re.compile(r'https?://[^\s]+')
        urls = {url for url in map(str, column_data) if url_pattern.match(url)}     # 这里将自动过滤重复的内容
    except Exception as e:
        printf(f"Error: {e}")
    printf(f"成功获取 {len(urls)} 个 URL！")
    
    printf(f"\n开始依次提取 URL 页面内容...")
    markdown_num = 0
    for url in urls:
        try:
            printf(f"提取: {url}")
            deepwiki2markdown(url, 'data/files_markdown')
            markdown_num += 1
        except requests.exceptions.RequestException as e: 
            printf(f"请求错误: {e}")
        except Exception as e:
            printf(f"转换错误: {e}")
    printf(f"成功提取 {markdown_num} 个 URL 页面内容！")
    
    printf(f"\n开始翻译 Markdown 文件...")
    md_files = [f for f in os.listdir('data/files_markdown') if f.endswith('.md')]
    translated_num = 0
    for filename in enumerate(md_files):
        printf(f"翻译: {filename}")
        
        input_path = os.path.join('data/files_markdown', filename)
        output_path = os.path.join('data/files_markdown_translated', filename)
        
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 翻译内容
        # translated_content = translate_markdown(content)
        translated_content = 'translate_markdown(content)'
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(translated_content)
        
        printf(f"保存: {output_path}")
        translated_num += 1
    printf(f"成功翻译 {translated_num} 个 Markdown 文件！")

    # 步骤 4：转换为 Word 文档
    printf(f"\n开始转换为 Word 文档...")
    translated_files = [f for f in os.listdir('data/files_markdown_translated') if f.endswith('.md')]
    word_num = 0
    for filename in enumerate(translated_files):
        printf(f"转换: {filename}")
        
        input_path = os.path.join('data/files_markdown_translated', filename)
        output_path = os.path.join('data/files_word', filename.replace('.md', '.docx'))
        
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 创建 Word 文档
        try:
            markdown2word(content, output_path)
            printf(f"保存: {output_path}")
            word_num += 1
        except Exception as e:
            printf(f"转换失败: {e}")
    printf(f"成功转换 {word_num} 个 Word 文档！")

if __name__ == "__main__":
    main()
