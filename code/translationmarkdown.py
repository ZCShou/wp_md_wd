import re
import time
import requests

# 配置部分
DEEPSEEK_API_KEY = "sk-da3e2db4ed4b4f4384734af78174d570"  # 替换为你的DeepSeek API密钥
TRANSLATION_MODEL = "deepseek-chat"  # DeepSeek模型
LANGUAGE = "中文"  # 目标语言
API_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"  # DeepSeek API端点

"""
智能分割Markdown文档，保持结构完整
"""
def split_markdown(content, max_length=3000):
    """
    智能分割Markdown文档，保持结构完整
    """
    # 按双换行符分割
    parts = re.split(r'\n\s*\n', content)
    
    sections = []
    current_section = ""
    
    for part in parts:
        # 如果当前部分加上新部分不会超长，就合并
        if len(current_section) + len(part) < max_length:
            current_section += "\n\n" + part if current_section else part
        else:
            # 否则保存当前部分，开始新部分
            if current_section:
                sections.append(current_section)
            current_section = part
    
    if current_section:
        sections.append(current_section)
    
    return sections

"""
调用AI API翻译文本
"""
def translate_text_with_deepseek(text, max_retries=3):
    """
    调用DeepSeek API翻译文本
    """
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": TRANSLATION_MODEL,
        "messages": [
            {
                "role": "system",
                "content": f"你是一名专业翻译，请将以下内容准确翻译成{LANGUAGE}，保留原有的格式和特殊标记。"
            },
            {
                "role": "user",
                "content": text
            }
        ],
        "temperature": 0.3,
        "max_tokens": 4000  # DeepSeek支持更大的上下文
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(API_ENDPOINT, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise Exception(f"DeepSeek API请求失败: {str(e)}")
            print(f"翻译失败，重试 {attempt + 1}/{max_retries}: {str(e)}")
            time.sleep(5)  # 等待后重试

def should_translate(text):
    """
    判断文本是否需要翻译（跳过代码块、URL等）
    """
    text = text.strip()
    
    # 跳过空行或空白文本
    if not text:
        return False
    
    # 跳过代码块
    if text.startswith('```'):
        return False
    
    # 跳过表格行
    if re.match(r'^\|.+\|$', text):
        return False
    
    # 跳过纯URL
    if re.match(r'^https?://\S+$', text):
        return False
    
    # 跳过Markdown链接和图片
    if re.match(r'^!?$$.*$$$.*$$', text):
        return False
    
    # 跳过HTML标签
    if re.match(r'^<[^>]+>$', text):
        return False
    
    # 跳过数字和符号为主的文本
    if re.match(r'^[\d\s\W]+$', text):
        return False
    
    return True

"""
翻译指定内容
"""
def translate_content(content):
    # 分割Markdown为多个部分（避免超过API token限制）
    sections = split_markdown(content)
    
    translated_sections = []
    for section in sections:
        if should_translate(section):
            print(f"            正在翻译段落: {section[:50]}...")  # 打印前50字符便于调试
            translated = translate_text_with_deepseek(section)
            translated_sections.append(translated)
        else:
            translated_sections.append(section)
    
    # 合并翻译后的部分
    return "\n\n".join(translated_sections)
