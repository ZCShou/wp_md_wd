import os
import re
import json
import time
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from code.printf import printf

def convert_flowchart_svg_to_mermaid_text(svg_content):
    try:
        # 1. 提取所有节点（改进ID处理）
        nodes = {}
        id_map = {}  # 映射原始ID到标准化ID
        for node in svg_content.select('g.node.default'):
            original_id = node.get('id', '')
            if not original_id.startswith('flowchart-'):
                continue
                
            # 提取标准节点ID（去除flowchart-前缀和数字后缀）
            base_id = re.sub(r'flowchart-([^-]+)(-\d+)?$', r'\1', original_id)
            
            # 提取节点文本
            label = node.select_one('.label')
            text = ''
            if label:
                foreign = label.select_one('foreignObject div')
                if foreign:
                    text = foreign.get_text(strip=True).replace('"', "'")
                else:
                    text = label.get_text(strip=True).replace('"', "'")
            
            nodes[base_id] = text
            id_map[original_id] = base_id
        # 2. 提取所有集群（保持原始结构）
        clusters = {}
        for cluster in svg_content.select('g.cluster'):
            cluster_id = cluster.get('id', '')
            if not cluster_id.startswith('subGraph'):
                continue
                
            # 提取集群标题
            label = cluster.select_one('.cluster-label')
            title = cluster_id.replace('subGraph', 'cluster_')
            if label:
                foreign = label.select_one('foreignObject div')
                if foreign:
                    title = foreign.get_text(strip=True).replace('"', "'")
                else:
                    title = label.get_text(strip=True).replace('"', "'")
            
            # 收集集群中的节点（通过坐标判断包含关系）
            cluster_nodes = []
            cluster_rect = cluster.select_one('rect')
            if cluster_rect:
                x1 = float(cluster_rect.get('x', 0))
                y1 = float(cluster_rect.get('y', 0))
                x2 = x1 + float(cluster_rect.get('width', 0))
                y2 = y1 + float(cluster_rect.get('height', 0))
                
                for node in svg_content.select('g.node.default'):
                    node_transform = node.get('transform', '')
                    if not node_transform.startswith('translate('):
                        continue
                        
                    # 提取节点坐标
                    coords = re.findall(r'translate\(([\d.]+),\s*([\d.]+)\)', node_transform)
                    if not coords:
                        continue
                        
                    node_x, node_y = map(float, coords[0])
                    
                    # 检查节点是否在集群矩形内
                    if x1 <= node_x <= x2 and y1 <= node_y <= y2:
                        node_id = node.get('id', '')
                        if node_id in id_map:
                            cluster_nodes.append(id_map[node_id])
            
            clusters[cluster_id] = {
                'title': title,
                'nodes': cluster_nodes
            }
        # 3. 完全重构边关系解析（关键修正）
        edges = []
        for path in svg_content.select('path.flowchart-link'):
            path_id = path.get('id', '')
            if not path_id.startswith('L_'):
                continue
                
            # 精确解析边关系（支持多种格式）
            parts = path_id[2:].split('_')  # 去掉L_前缀
            
            # 情况1：标准格式 L_source_target
            if len(parts) == 2:
                source, target = parts
                if source in nodes and target in nodes:
                    edges.append(f"{source} --> {target}")
            
            # 情况2：带数字后缀 L_source_target_0
            elif len(parts) == 3 and parts[2].isdigit():
                source, target, _ = parts
                if source in nodes and target in nodes:
                    edges.append(f"{source} --> {target}")
            
            # 情况3：多段名称 L_GicDistributorRegs_tock_registers_0
            else:
                # 尝试所有可能的组合
                for i in range(1, len(parts)):
                    source_candidate = '_'.join(parts[:i])
                    target_candidate = '_'.join(parts[i:])
                    
                    # 去除数字后缀
                    source_candidate = re.sub(r'_\d+$', '', source_candidate)
                    target_candidate = re.sub(r'_\d+$', '', target_candidate)
                    
                    if source_candidate in nodes and target_candidate in nodes:
                        edges.append(f"{source_candidate} --> {target_candidate}")
                        break
        # 4. 生成完全正确的Mermaid代码
        mermaid = ["flowchart TD"]
        
        # 添加所有集群
        for cluster_id, data in clusters.items():
            mermaid.append(f"\nsubgraph {cluster_id}[\"{data['title']}\"]")
            for node_id in data['nodes']:
                mermaid.append(f"    {node_id}[\"{nodes[node_id]}\"]")
            mermaid.append("end")
        
        # 添加游离节点
        clustered_nodes = set()
        for data in clusters.values():
            clustered_nodes.update(data['nodes'])
            
        for node_id, text in nodes.items():
            if node_id not in clustered_nodes:
                mermaid.append(f"{node_id}[\"{text}\"]")
        
        # 添加所有边关系（确保顺序正确）
        if edges:
            mermaid.append("")
            mermaid.extend(sorted(set(edges)))  # 去重并排序
        
        return "```mermaid\n" + "\n".join(mermaid) + "\n```"
    
    except Exception as e:
        print(f"转换过程中出错: {str(e)}")
        return None

def convert_class_diagram_svg_to_mermaid_text(svg_element: BeautifulSoup) -> Optional[str]:
    """将类图 SVG 转换为 Mermaid 文本"""
    if not svg_element:
        return None
        
    mermaid_lines = ['classDiagram']
    class_data: Dict[str, Dict] = {}
    
    # 1. 解析类信息
    for node in svg_element.select('g.node.default[id^="classId-"]'):
        class_id_svg = node.get('id')
        if not class_id_svg:
            continue
            
        match = re.match(r'^classId-([^-]+(?:-[^-]+)*)-(\d+)$', class_id_svg)
        if not match:
            continue
            
        class_name = match.group(1)
        
        # 获取位置信息
        transform = node.get('transform', '')
        tx, ty = 0, 0
        if transform:
            match = re.search(r'translate\(([^,]+),\s*([^)]+)\)', transform)
            if match:
                tx = float(match.group(1))
                ty = float(match.group(2))
        
        # 初始化类数据
        if class_name not in class_data:
            class_data[class_name] = {
                'stereotype': "",
                'members': [],
                'methods': [],
                'svg_id': class_id_svg,
                'x': tx,
                'y': ty,
                'width': 200,  # 默认值
                'height': 200  # 默认值
            }
        
        # 获取定型文本
        stereotype_elem = node.select_one('g.annotation-group.text foreignObject span.nodeLabel p, g.annotation-group.text foreignObject div p')
        if stereotype_elem and stereotype_elem.get_text(strip=True):
            class_data[class_name]['stereotype'] = stereotype_elem.get_text(strip=True)
        
        # 获取成员
        for m in node.select('g.members-group.text g.label foreignObject span.nodeLabel p, g.members-group.text g.label foreignObject div p'):
            txt = m.get_text(strip=True)
            if txt:
                class_data[class_name]['members'].append(txt)
        
        # 获取方法
        for m in node.select('g.methods-group.text g.label foreignObject span.nodeLabel p, g.methods-group.text g.label foreignObject div p'):
            txt = m.get_text(strip=True)
            if txt:
                class_data[class_name]['methods'].append(txt)
    
    # 2. 解析注释
    notes = []
    # 简化处理：在实际应用中需要完整实现
    
    # 3. 生成Mermaid代码
    for class_name, data in class_data.items():
        if data['stereotype']:
            mermaid_lines.append(f"    class {class_name} {{")
            mermaid_lines.append(f"        {data['stereotype']}")
        else:
            mermaid_lines.append(f"    class {class_name} {{")
        
        for member in data['members']:
            mermaid_lines.append(f"        {member}")
        
        for method in data['methods']:
            mermaid_lines.append(f"        {method}")
        
        mermaid_lines.append('    }')
    
    # 4. 添加关系
    # 简化处理：在实际应用中需要完整实现
    
    if len(mermaid_lines) <= 1 and not class_data and not notes:
        return None
        
    return f'```mermaid\n{"\n".join(mermaid_lines)}\n```'

def convert_sequence_diagram_svg_to_mermaid_text(svg_element: BeautifulSoup) -> Optional[str]:
    """将序列图 SVG 转换为 Mermaid 文本"""
    if not svg_element:
        return None
        
    # 1. 解析参与者
    participants = []
    for text_el in svg_element.select('text.actor-box'):
        name = text_el.get_text(strip=True).replace('"', '')
        x = float(text_el.get('x', 0))
        participants.append({'name': name, 'x': x})
    
    participants.sort(key=lambda p: p['x'])
    
    # 去重
    unique_participants = []
    seen_names = set()
    for p in participants:
        if p['name'] not in seen_names:
            unique_participants.append(p)
            seen_names.add(p['name'])
    
    # 2. 生成Mermaid代码
    mermaid_output = "sequenceDiagram\n"
    for p in unique_participants:
        mermaid_output += f"  participant {p['name']}\n"
    
    mermaid_output += "\n"
    
    # 3. 添加消息（简化处理）
    # 在实际应用中需要完整实现消息解析
    
    if not unique_participants:
        return None
        
    return f'```mermaid\n{mermaid_output.strip()}\n```'

def convert_state_diagram_svg_to_mermaid_text(svg_element: BeautifulSoup) -> Optional[str]:
    """将状态图 SVG 转换为 Mermaid 文本"""
    if not svg_element:
        return None
        
    printf("Converting state diagram...")
    nodes = []
    transitions = []
    
    # 1. 解析状态
    for state_el in svg_element.select('g.node.statediagram-state'):
        state_name_el = state_el.select_one('foreignObject .nodeLabel p, foreignObject .nodeLabel span')
        if not state_name_el:
            continue
            
        state_name = state_name_el.get_text(strip=True)
        transform = state_el.get('transform', '')
        
        # 获取位置信息
        tx, ty = 0, 0
        if transform:
            match = re.search(r'translate\(([^,]+),\s*([^)]+)\)', transform)
            if match:
                tx = float(match.group(1))
                ty = float(match.group(2))
        
        # 使用近似边界框
        nodes.append({
            'name': state_name,
            'x': tx,
            'y': ty,
            'width': 100,  # 默认值
            'height': 50   # 默认值
        })
    
    # 2. 生成Mermaid代码
    mermaid_code = "stateDiagram-v2\n"
    # 简化处理：在实际应用中需要完整实现转换逻辑
    
    if not transitions:
        return None
        
    return f'```mermaid\n{mermaid_code.strip()}\n```'

def detect_code_language(code_text: str) -> str:
    """自动检测代码语言"""
    if not code_text or len(code_text.strip()) < 10:
        return ''
    
    code = code_text.strip()
    first_line = code.split('\n')[0].strip()
    
    # 检测语言模式
    if 'function ' in code or 'const ' in code or 'let ' in code or 'var ' in code:
        if ': ' in code and ('interface ' in code or 'type ' in code):
            return 'typescript'
        return 'javascript'
    
    if 'def ' in code or 'import ' in code or 'from ' in code or 'print(' in code:
        return 'python'
    
    if 'public class ' in code or 'private ' in code or 'public static void main' in code:
        return 'java'
    
    if 'using System' in code or 'namespace ' in code:
        return 'csharp'
    
    if '#include' in code or 'int main' in code:
        return 'cpp' if 'std::' in code or 'cout' in code else 'c'
    
    if 'package ' in code or 'func ' in code:
        return 'go'
    
    if 'fn ' in code or 'let mut' in code:
        return 'rust'
    
    if '<?php' in code or '$' in code and ('echo ' in code or 'print ' in code):
        return 'php'
    
    if 'def ' in code and 'end' in code:
        return 'ruby'
    
    if first_line.startswith('#!') and ('bash' in first_line or 'sh' in first_line):
        return 'bash'
    
    if re.search(r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b', code, re.I):
        return 'sql'
    
    if '{' in code and '}' in code and ':' in code:
        return 'css'
    
    if '<!DOCTYPE' in code or '<html' in code:
        return 'html'
    
    if '<?xml' in code or ('<' in code and '>' in code and '</' in code):
        return 'xml'
    
    if (code.startswith('{') and code.endswith('}')) or (code.startswith('[') and code.endswith(']')):
        try:
            json.loads(code)
            return 'json'
        except:
            pass
    
    if any(re.match(r'^\s*\w+:\s*', line) for line in code.split('\n')):
        return 'yaml'
    
    if '# ' in code or '## ' in code or '```' in code:
        return 'markdown'
    
    if 'FROM ' in code or 'RUN ' in code:
        return 'dockerfile'
    
    return ''

def process_node(node: Any) -> str:
    """递归处理 DOM 节点转换为 Markdown"""
    # 文本节点处理
    if node.string and not node.name:
        return node.string
    
    # 元素节点处理
    if not node.name:
        return ""
    
    # 跳过隐藏元素
    if node.get('style', '') and ('display: none' in node['style'] or 'visibility: hidden' in node['style']):
        return ""
    
    # 跳过不需要的元素
    if node.name in ['button', 'script', 'style', 'noscript', 'iframe', 'header', 'footer']:
        return ""
    
    result_md = ""
    
    try:
        if node.name == 'p':
            content = ''.join(process_node(child) for child in node.children)
            content = content.strip()
            if content.startswith("```mermaid") and content.endswith("```"):
                result_md = content + "\n\n"
            elif content:
                result_md = content + "\n\n"
        
        elif node.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(node.name[1])
            text = node.get_text(strip=True)
            if text:
                result_md = f"{'#' * level} {text}\n\n"
        
        elif node.name == 'ul':
            items = []
            for li in node.find_all('li', recursive=False):
                content = ''.join(process_node(child) for child in li.children).strip()
                if content:
                    items.append(f"* {content}")
            if items:
                result_md = '\n'.join(items) + '\n\n'
        
        elif node.name == 'ol':
            items = []
            for i, li in enumerate(node.find_all('li', recursive=False), 1):
                content = ''.join(process_node(child) for child in li.children).strip()
                if content:
                    items.append(f"{i}. {content}")
            if items:
                result_md = '\n'.join(items) + '\n\n'
        
        elif node.name == 'pre':
            # 尝试转换图表
            svg_element = node.select_one('svg[id^="mermaid-"]')
            mermaid_output = None
            
            if svg_element:
                diagram_type = svg_element.get('aria-roledescription', '')
                if 'flowchart' in diagram_type:
                    mermaid_output = convert_flowchart_svg_to_mermaid_text(svg_element)
                elif 'class' in diagram_type:
                    mermaid_output = convert_class_diagram_svg_to_mermaid_text(svg_element)
                elif 'sequence' in diagram_type:
                    mermaid_output = convert_sequence_diagram_svg_to_mermaid_text(svg_element)
                elif 'stateDiagram' in diagram_type:
                    mermaid_output = convert_state_diagram_svg_to_mermaid_text(svg_element)
            
            if mermaid_output:
                result_md = f"\n{mermaid_output}\n\n"
            else:
                # 处理代码块
                code = node.find('code')
                lang = ""
                if code:
                    code_text = code.get_text()
                    # 检测语言
                    lang = detect_code_language(code_text)
                else:
                    code_text = node.get_text()
                
                result_md = f"```{lang}\n{code_text.strip()}\n```\n\n"
        
        elif node.name == 'a':
            href = node.get('href', '')
            text = ''.join(process_node(child) for child in node.children).strip()
            
            # 特殊处理：源码文件链接是 文件名 + 行号 格式
            if re.search(r'#L(\d+)(?:-L(\d+))?$', href):
                format_str = lambda s: f"{s.split()[0]} L{s.split()[-1].replace('-', '-L')}"
                text = format_str(text)
            
            if href:
                result_md = f"[{text}]({href})"
            else:
                result_md = text
        
        elif node.name == 'img':
            src = node.get('src', '')
            alt = node.get('alt', '')
            if src:
                result_md = f"![{alt}]({src})\n\n"
        
        elif node.name == 'blockquote':
            content = ''.join(process_node(child) for child in node.children).strip()
            if content:
                lines = content.split('\n')
                result_md = '\n'.join(f"> {line}" for line in lines) + '\n\n'
        
        elif node.name == 'hr':
            result_md = "\n---\n\n"
        
        elif node.name in ['strong', 'b']:
            content = ''.join(process_node(child) for child in node.children).strip()
            return f"**{content}**"
        
        elif node.name in ['em', 'i']:
            content = ''.join(process_node(child) for child in node.children).strip()
            return f"*{content}*"
        
        elif node.name == 'code':
            return f"`{node.get_text(strip=True)}`"
        
        elif node.name == 'br':
            return "  \n"
        
        elif node.name == "table":
            table_md = ""
            rows = node.find_all('tr')
            if rows:
                # Header
                header_cells = rows[0].find_all(['th', 'td'])
                header = "|" + "|".join(cell.get_text(strip=True).replace("|", "\\|") for cell in header_cells) + "|"
                sep = "|" + "|".join([" --- " for _ in header_cells]) + "|"
                table_md += header + "\n" + sep + "\n"
                # Body
                for row in rows[1:]:
                    cells = row.find_all(['th', 'td'])
                    row_md = "|" + "|".join(cell.get_text(strip=True).replace("|", "\\|").replace("\n", " <br> ") for cell in cells) + "|"
                    table_md += row_md + "\n"
            return table_md + ("\n" if table_md else "")
        
        elif node.name == "details":
            summary = node.find('summary')
            summary_text = process_node(summary) if summary else "Details"
            details_content = ''.join(process_node(c) for c in node.children if c.name != "summary")
            return f"> **{summary_text.strip()}**\n" + '\n'.join([f"> {l}" for l in details_content.strip().split('\n')]) + "\n\n"

        else:
            # 处理其他元素
            content = ''.join(process_node(child) for child in node.children)
            result_md = content + "\n\n" if content.strip() else ""
    
    except Exception as e:
        printf(f"处理节点错误: {node.name} - {str(e)}")
        return f"[ERROR_PROCESSING:{node.name}]"
    
    return result_md

def deepwiki2markdown(url: str, output_path: str) -> str:
    # 配置 Chrome 选项 (可选)：例如，无头模式运行
    chrome_options = Options()
    # # 禁用所有日志输出
    # chrome_options.add_argument('--log-level=3')  # 0=INFO, 1=WARNING, 2=ERROR, 3=FATAL
    # chrome_options.add_argument('--disable-logging')  # 禁用日志
    # chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])  # 排除日志开关
    # 禁用控制台输出
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--headless')  # 无头模式也会减少输出
    # 指定 ChromeDriver 的路径
    # 如果您将 chromedriver 放在系统 PATH 中，则无需指定 service_executable_path
    # service = Service(executable_path='/path/to/your/chromedriver') # 替换为您的chromedriver路径
    # driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # 如果 chromedriver 在 PATH 中，可以直接这样初始化
    driver = webdriver.Chrome(options=chrome_options)

    try:
        # 打开网页
        driver.get(url)

        # 等待页面加载完成 (可选，根据页面复杂度调整)。可以使用显式等待来等待某个元素出现，或者简单地等待几秒
        time.sleep(3) # 简单等待3秒，确保页面内容加载

        # 一个 URL 对应多个篇文章，我们用一个目录存放
        pdir = url.split('/')[-1]
        os.makedirs(f"{output_path}/{pdir}", exist_ok=True)

        # 获取侧边栏目录，每一个目录项都是一个页面，我们需要依次处理
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        sidebar = soup.select_one('.border-r-border')
        ul_elements = sidebar.find_all('ul')
        urls = []
        filenames = []
        for ul in ul_elements:
            # 查找 ul 下的所有直接 li 子元素
            li_elements = ul.find_all('li', recursive=False)
            for li in li_elements:
                # 查找li中的第一个a元素
                a_element = li.find('a')
                if a_element and a_element.get('href'):
                    href = a_element.get('href')
                    text = a_element.get_text(strip=True)
                    filenames.append(text)
                    urls.append(url + '/' + href.split('/')[-1])
        # 开始处理当前 URL 下所有页面（其中，第一个目录与基础 URL 实际是一个页面）
        for url, filename in zip(urls, filenames):
            printf(f"提取: {url}")
            # 打开网页
            driver.get(url)

            # 等待页面加载完成 (可选，根据页面复杂度调整)。可以使用显式等待来等待某个元素出现，或者简单地等待几秒
            time.sleep(3) # 简单等待3秒，确保页面内容加载
            
            # 主内容
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            content = soup.select_one(".container > div:nth-child(2) .prose") or \
                    soup.select_one(".container > div:nth-child(2) .prose-custom") or \
                    soup.select_one(".container > div:nth-child(2)") or \
                    soup.body
            
            markdown = ''.join(process_node(child) for child in content.children)
            markdown = re.sub(r'\n{3,}', '\n\n', markdown.strip())
            
            # 用于规范化文件名。示例：txt = sanitize(txt)
            sanitize = lambda f: re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', f).strip(' .')[:255] or 'unnamed'
            filename_f = sanitize(filename)
            markdown_name = f"{filename_f}.md"
            md_path = os.path.join(f"{output_path}/{pdir}", markdown_name)
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(markdown)
            printf(f"保存: {md_path}")
    except Exception as e:
        printf(f"An error occurred: {e}")
        return None
    finally:
        # 关闭浏览器
        if driver:
            driver.quit()
