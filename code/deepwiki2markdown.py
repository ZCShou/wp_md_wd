import os
import re
import json
import time
from bs4 import BeautifulSoup
from typing import Any
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from code.printf import printf

def convert_flowchart_svg_to_mermaid_text(svg_content):
    """
    将流程图 SVG 转换为 Mermaid 文本

    Parameters:
        svg_content (str): 网页中 <svg> 标签中的内容

    Returns:
        str: 转换后的 Mermaid 文本
    """
    try:
        # 1. 提取所有节点
        nodes = {}
        id_map = {}
        for node in svg_content.select('g.node.default'):
            original_id = node.get('id', '')
            if not original_id.startswith('flowchart-'):
                continue
                
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

        # 2. 精确构建集群层级结构
        clusters = {}
        
        # 首先收集所有集群
        all_clusters = list(svg_content.select('g.cluster'))
        for cluster in all_clusters:
            cluster_id = cluster.get('id', f'cluster_{len(clusters)+1}')
            
            # 提取集群标题
            label = cluster.select_one('.cluster-label')
            title = "Untitled Cluster"
            if label:
                foreign = label.select_one('foreignObject div')
                if foreign:
                    title = foreign.get_text(strip=True).replace('"', "'")
                else:
                    title = label.get_text(strip=True).replace('"', "'")
            
            # 获取集群边界
            rect = cluster.select_one('rect')
            if not rect:
                continue
                
            try:
                x = float(rect.get('x', 0))
                y = float(rect.get('y', 0))
                width = float(rect.get('width', 0))
                height = float(rect.get('height', 0))
            except (ValueError, AttributeError):
                continue
            
            clusters[cluster_id] = {
                'title': title,
                'nodes': [],
                'children': [],
                'rect': (x, y, x + width, y + height),
                'element': cluster
            }

        # 3. 确定集群嵌套关系（基于包含关系）
        cluster_ids = list(clusters.keys())
        for i in range(len(cluster_ids)):
            for j in range(len(cluster_ids)):
                if i == j:
                    continue
                    
                # 检查cluster_i是否完全包含cluster_j
                (x1_i, y1_i, x2_i, y2_i) = clusters[cluster_ids[i]]['rect']
                (x1_j, y1_j, x2_j, y2_j) = clusters[cluster_ids[j]]['rect']
                
                if (x1_i <= x1_j and y1_i <= y1_j and 
                    x2_i >= x2_j and y2_i >= y2_j):
                    # 确保没有更近的父集群
                    is_direct_child = True
                    for k in range(len(cluster_ids)):
                        if k == i or k == j:
                            continue
                            
                        (x1_k, y1_k, x2_k, y2_k) = clusters[cluster_ids[k]]['rect']
                        if (x1_k <= x1_j and y1_k <= y1_j and 
                            x2_k >= x2_j and y2_k >= y2_j and
                            x1_i <= x1_k and y1_i <= y1_k and 
                            x2_i >= x2_k and y2_i >= y2_k):
                            is_direct_child = False
                            break
                    
                    if is_direct_child:
                        clusters[cluster_ids[i]]['children'].append(cluster_ids[j])

        # 4. 分配节点到最内层集群
        # 按面积从小到大排序（从最内层到最外层）
        sorted_clusters = sorted(
            clusters.items(),
            key=lambda x: (x[1]['rect'][2] - x[1]['rect'][0]) * (x[1]['rect'][3] - x[1]['rect'][1])
        )

        for cluster_id, data in sorted_clusters:
            (x1, y1, x2, y2) = data['rect']
            
            for node in svg_content.select('g.node.default'):
                node_id = node.get('id', '')
                if node_id not in id_map:
                    continue
                    
                # 检查节点是否已经在更内层的集群中
                already_clustered = any(
                    id_map[node_id] in clusters[c]['nodes'] 
                    for c in data['children']
                )
                
                if already_clustered:
                    continue
                    
                # 检查坐标是否在当前集群内
                node_transform = node.get('transform', '')
                if not node_transform.startswith('translate('):
                    continue
                    
                coords = re.findall(r'translate\(([\d.]+),\s*([\d.]+)\)', node_transform)
                if not coords:
                    continue
                    
                try:
                    node_x, node_y = map(float, coords[0])
                    if x1 <= node_x <= x2 and y1 <= node_y <= y2:
                        clusters[cluster_id]['nodes'].append(id_map[node_id])
                except (ValueError, IndexError):
                    continue

        # 5. 边关系解析
        edges = []
        for path in svg_content.select('path.flowchart-link'):
            path_id = path.get('id', '')
            if not path_id.startswith('L_'):
                continue
                
            parts = path_id[2:].split('_')
            
            # 处理多种可能的边ID格式
            if len(parts) >= 2:
                # 尝试从长到短的各种组合
                for i in range(1, len(parts)):
                    source = '_'.join(parts[:i])
                    target = '_'.join(parts[i:])
                    
                    # 去除数字后缀
                    source = re.sub(r'_\d+$', '', source)
                    target = re.sub(r'_\d+$', '', target)
                    
                    if source in nodes and target in nodes:
                        edges.append(f"{source} --> {target}")
                        break

        # 6. 生成Mermaid代码（确保正确嵌套）
        mermaid = ["flowchart TD"]
        
        # 递归添加集群
        def add_cluster(cluster_id, indent=0):
            data = clusters[cluster_id]
            prefix = "    " * indent
            
            # 集群开始
            title = data['title'] or f"Cluster {cluster_id}"
            mermaid.append(f"{prefix}subgraph {cluster_id}[\"{title}\"]")
            
            # 添加节点
            for node_id in data['nodes']:
                mermaid.append(f"{prefix}    {node_id}[\"{nodes[node_id]}\"]")
            
            # 递归添加子集群
            for child_id in data['children']:
                add_cluster(child_id, indent + 1)
            
            # 集群结束
            mermaid.append(f"{prefix}end")
        
        # 先添加顶级集群（没有父集群的）
        top_level_clusters = [
            cid for cid, data in clusters.items() 
            if not any(cid in clusters[other]['children'] for other in clusters)
        ]
        
        # 确保最大的集群（MSR Configuration）在最外层
        main_cluster = None
        for cid in top_level_clusters:
            if "MSR Configuration" in clusters[cid]['title']:
                main_cluster = cid
                break
                
        if main_cluster:
            add_cluster(main_cluster)
            # 添加其他顶级集群（如果有）
            for cid in top_level_clusters:
                if cid != main_cluster:
                    add_cluster(cid)
        else:
            for cid in top_level_clusters:
                add_cluster(cid)
        
        # 添加游离节点（不在任何集群中的）
        clustered_nodes = set()
        for data in clusters.values():
            clustered_nodes.update(data['nodes'])
            
        for node_id, text in nodes.items():
            if node_id not in clustered_nodes:
                mermaid.append(f"{node_id}[\"{text}\"]")
        
        # 添加边关系
        if edges:
            mermaid.append("")
            mermaid.extend(sorted(set(edges)))
        
        return "```mermaid\n" + "\n".join(mermaid) + "\n```"
    
    except Exception as e:
        print(f"转换过程中出错: {str(e)}")
        return None


def convert_sequence_svg_to_mermaid_text(svg_content):
    """
    解析 SVG 序列图并转换为 mermaid 格式
    
    参数:
        html_content: 包含SVG的HTML字符串
        
    返回:
        str: mermaid序列图文本
    """
    try:
        soup = BeautifulSoup(svg_content, 'html.parser') if isinstance(svg_content, str) else svg_content
        
        # ===== 1. 提取唯一参与者 =====
        participants = {}  # {actor_name: x_position}
        actor_rects = {}  # 保存参与者矩形元素 {actor_name: rect_element}
        actor_labels = set()  # 保存参与者标签文本元素
        
        # 先提取所有参与者
        for g in soup.find_all('g'):
            if rect := g.find('rect', class_=lambda x: x and 'actor' in x.lower()):
                if text := (g.find('text', class_='label') or g.find('text')):
                    try:
                        x = float(rect.get('x', 0)) + float(rect.get('width', 0)) / 2
                        actor_name = text.get_text(strip=True)
                        # 只保留每个参与者的最左侧出现
                        participants[actor_name] = x
                        actor_rects[actor_name] = rect
                        actor_labels.add(text)
                    except (ValueError, AttributeError):
                        continue
        
        if not participants:
            return "错误：未识别到参与者"

        # ===== 2. 处理消息线 =====
        elements = []
        used_texts = set()
        
        # 预处理所有非参与者标签的文本元素
        texts = []
        for text in soup.find_all('text'):
            if text not in actor_labels:  # 排除参与者名称文本
                try:
                    texts.append({
                        'x': float(text.get('x', 0)),
                        'y': float(text.get('y', 0)),
                        'text': text.get_text(strip=True),
                        'element': text
                    })
                except (ValueError, AttributeError):
                    continue
        
        # 辅助函数：查找最近的参与者
        def find_actor(x_pos):
            return min(participants.items(), key=lambda p: abs(p[1] - x_pos))[0]
        
        # 处理消息线
        for elem in soup.find_all(['line', 'path'], class_=lambda x: x and 'message' in x.lower()):
            try:
                # 获取坐标
                if elem.name == 'line':
                    x1, y1 = float(elem.get('x1', 0)), float(elem.get('y1', 0))
                    x2, y2 = float(elem.get('x2', 0)), float(elem.get('y2', 0))
                else:  # path
                    points = re.findall(r'([A-Za-z])\s*([\d\.]+)[,\s]*([\d\.]+)', elem.get('d', ''))
                    if not points: continue
                    x1, y1 = float(points[0][1]), float(points[0][2])
                    x2, y2 = float(points[-1][1]), float(points[-1][2])
                
                sender = find_actor(x1)
                receiver = find_actor(x2)
                
                # 查找最近的未使用文本（排除参与者标签）
                mid_y = (y1 + y2) / 2
                closest_text = min(
                    (t for t in texts if t['element'] not in used_texts),
                    key=lambda t: abs(t['y'] - mid_y) + 0.3 * abs(t['x'] - (x1 + x2)/2),
                    default=None
                )
                
                if closest_text:
                    if sender == receiver:  # 自调用
                        elements.append((mid_y, f"{sender}->>{sender}: {closest_text['text']}"))
                    else:
                        elements.append((mid_y, f"{sender}->>{receiver}: {closest_text['text']}"))
                    used_texts.add(closest_text['element'])
            except Exception:
                continue
        
        # 处理剩余文本作为注释
        for text in (t for t in texts if t['element'] not in used_texts):
            try:
                actor = find_actor(text['x'])
                elements.append((text['y'], f"note over {actor}: {text['text']}"))
            except Exception:
                continue
        
        # ===== 3. 生成Mermaid代码 =====
        mermaid = ["sequenceDiagram"]
        # 按x坐标排序参与者
        for actor, _ in sorted(participants.items(), key=lambda x: x[1]):
            mermaid.append(f"    participant {actor}")
        
        # 按垂直位置排序元素
        for _, elem in sorted(elements, key=lambda x: x[0]):
            mermaid.append(f"    {elem}")
        
        return "```mermaid\n" + "\n".join(mermaid) + "\n```"
    
    except Exception as e:
        return f"转换错误: {str(e)}"




def convert_class_svg_to_mermaid_text(svg_content):
    return "```mermaid\n暂不支持类图\n```"

def convert_statediagram_svg_to_mermaid_text(svg_content):
    return "```mermaid\n暂不支持状态图\n```"

def detect_code_language(code_text: str) -> str:
    """
    通过不同编程语言的某些特征字来推测语言类型

    Parameters:
        code_text (int): 网页中的代码内容

    Returns:
        str: 编程语言的名字
    """
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
    """
    递归处理 DOM 节点转换为 Markdown

    Parameters:
        node (Any): 网页节点内容

    Returns:
        str: 转换后的 Markdown 内容
    """

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
                    mermaid_output = convert_class_svg_to_mermaid_text(svg_element)
                elif 'sequence' in diagram_type:
                    mermaid_output = convert_sequence_svg_to_mermaid_text(svg_element)
                elif 'stateDiagram' in diagram_type:
                    mermaid_output = convert_statediagram_svg_to_mermaid_text(svg_element)
            
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
                format_str = lambda s: f"{s.split()[0]}(L{s.split()[-1].replace('-', ' - L')})&emsp;"
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

def deepwiki2markdown(url: str, output_path: str):
    """
    解析 Deepwiki 的 URL 页面内容，并转为 Markdown 文件

    Parameters:
        url (str): Deepwiki 的 URL
        output_path (str): 转换后 Markdown 文档的保存路径

    Returns:
        None
    """
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
    finally:
        # 关闭浏览器
        if driver:
            driver.quit()
