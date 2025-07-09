import re
import requests
from typing import List, Tuple
 
class MarkdownTranslator:
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    
    def translate_text(self, text: str) -> str:
        """使用 DeepSeek API 翻译文本"""
        # 如果文本全是空白字符，直接返回
        if not text.strip():
            return text
            
        prompt = (
            "你是一位专业的翻译人员，请将以下技术文档从英文翻译成中文。"
            "保持术语准确，技术细节无误，格式不变。"
            "不要添加任何额外的解释或说明，直接返回翻译结果。\n\n"
            f"{text}"
        )
        
        data = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 4000
        }
        
        try:
            response = requests.post(self.api_url, headers=self.headers, json=data)
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        except Exception as e:
            print(f"翻译出错: {e}")
            return text
    
    def parse_markdown(self, content: str) -> List[Tuple[str, str]]:
        """
        解析 Markdown 内容，将其分为可翻译和不可翻译的部分
        返回一个列表，每个元素是 (内容类型, 内容) 的元组
        内容类型可以是: "text", "code", "mermaid", "header"
        """
        # 改进后的正则表达式，能更好地处理代码块
        pattern = r'(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`]+`|^# .+$|^## .+$|^### .+$|^#### .+$|^##### .+$|^###### .+$)'
        parts = []
        last_end = 0
        
        for match in re.finditer(pattern, content):
            start, end = match.span()
            if last_end < start:
                # 添加普通文本部分，保留前后换行
                text_part = content[last_end:start]
                if text_part.strip():  # 只有非空文本才添加
                    parts.append(("text", text_part))
            
            matched_text = match.group()
            if matched_text.startswith(('```', '~~~')):
                # 代码块或 mermaid 图表，确保前后有换行
                parts.append(("newline", "\n"))
                if 'mermaid' in matched_text.split('\n')[0].lower():
                    parts.append(("mermaid", matched_text))
                else:
                    parts.append(("code", matched_text))
                parts.append(("newline", "\n"))
            elif matched_text.startswith('`') and matched_text.endswith('`'):
                # 行内代码，不添加额外换行
                parts.append(("code", matched_text))
            elif matched_text.startswith(('# ')):
                # 标题，确保前面有换行（除非是文件开头）
                if parts and parts[-1][0] not in ("newline", "header"):
                    parts.append(("newline", "\n"))
                parts.append(("header", matched_text))
                parts.append(("newline", "\n"))
            
            last_end = end
        
        if last_end < len(content):
            text_part = content[last_end:]
            if text_part.strip():  # 只有非空文本才添加
                parts.append(("text", text_part))
        
        return parts
    
    def translate_markdown(self, content: str) -> str:
        """翻译整个 Markdown 内容"""
        parts = self.parse_markdown(content)
        translated_parts = []
        
        for part_type, part_content in parts:
            if part_type == "newline":
                translated_parts.append(part_content)
            elif part_type in ["code", "mermaid"]:
                # 跳过代码和图表，保留原样
                translated_parts.append(part_content)
            elif part_type == "header":
                # 单独处理标题翻译
                translated_header = self.translate_text(part_content)
                translated_parts.append(translated_header)
            else:
                # 翻译普通文本
                translated_text = self.translate_text(part_content)
                translated_parts.append(translated_text)
        
        # 合并所有部分
        result = ''.join(translated_parts)
        
        # 确保文件末尾有一个换行
        if not result.endswith('\n'):
            result += '\n'
            
        return result
