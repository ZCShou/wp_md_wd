import os
import re
import json
import time
import math
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

def convert_statediagram_svg_to_mermaid_text(soup):
    """
    将SVG状态图转换为Mermaid状态图
    输入: SVG字符串内容
    输出: Mermaid状态图代码
    """
    # 1. 收集所有状态节点
    nodes = soup.find_all('g', class_='node')
    node_data = []
    for node in nodes:
        # 提取状态名称（从 <p> 标签）。没有太好的方法可以区分开始节点和结束节点，只能通过 ID 中的字符判断，不一定通用
        state_name = None
        if 'start' in node.get('id'):
            state_name = 'start'
        elif 'end' in node.get('id'):
            state_name = 'end'
        else:
            state_name = node.find('p').get_text(strip=True)

        # 提取坐标（从 transform）
        transform = node.get('transform', '')
        x, y = map(float, re.findall(r'translate\(([^,]+),\s*([^)]+)', transform)[0])
        
        node_data.append({
            "id": node.get('id'),
            "state": state_name,
            "x": x,
            "y": y
        })

    # 2. 收集所有连线
    paths = soup.find_all('path', class_='transition')
    labels = soup.find_all('g', class_='edgeLabel')
    edge_data = []
    for path in paths:
        # 提取路径的起点和终点（简化版：取第一个和最后一个坐标）
        d = path.get('d', '')
        points = re.findall(r'([MLC])([\d.,-]+)', d)
        coords = []
        for cmd, coord_str in points:
            nums = list(map(float, re.findall(r'[-+]?\d*\.\d+|[-+]?\d+', coord_str)))
            coords.extend(list(zip(nums[::2], nums[1::2])))

        start_point = coords[0] if coords else None
        end_point = coords[-1] if coords else None

        # 关联标签（通过位置匹配）
        label_text = None
        for label in labels:
            transform = label.get('transform', '')
            if not transform:
                label_x, label_y = map(float, [0, 0])
            else:
                label_x, label_y = map(float, re.findall(r'translate\(([^,]+),\s*([^)]+)', transform)[0])


            # 检查标签是否在路径附近（简化逻辑）
            if start_point and end_point:
                path_mid_x = (start_point[0] + end_point[0]) / 2
                path_mid_y = (start_point[1] + end_point[1]) / 2
                if abs(label_x - path_mid_x) < 80 and abs(label_y - path_mid_y) < 80:
                    label_text = label.find('p').get_text(strip=True) if label.find('p') else None
        
        edge_data.append({
            "id": path.get('id'),
            "start": start_point,
            "end": end_point,
            "label": label_text
        })

    # 3. 关联节点和边
    matched_edges = []
    for edge in edge_data:
        start_node = None
        end_node = None
        
        # 找到最近的起点节点
        min_start_dist = float('inf')
        for node in node_data:
            if node["state"]:  # 忽略起始/结束节点
                dist = math.dist(edge["start"], (node["x"], node["y"]))
                if dist < min_start_dist:
                    min_start_dist = dist
                    start_node = node["state"]
        
        # 找到最近的终点节点
        min_end_dist = float('inf')
        for node in node_data:
            if node["state"]:
                dist = math.dist(edge["end"], (node["x"], node["y"]))
                if dist < min_end_dist:
                    min_end_dist = dist
                    end_node = node["state"]
        
        matched_edges.append({
            "from": start_node,
            "to": end_node,
            "label": edge["label"]
        })

    # 3. 生成 Mermaid 代码
    mermaid_lines = ["stateDiagram-v2"]
    for edge in matched_edges:
        if edge["from"] and edge["to"]:
            label = f" : {edge['label']}" if edge['label'] else ""
            if edge['from'] == 'start':
                mermaid_lines.append(f"    [*] --> {edge['to']}{label}")
            elif edge['to'] == 'end':
                mermaid_lines.append(f"    {edge['from']} --> [*]{label}")
            else:
                mermaid_lines.append(f"    {edge['from']} --> {edge['to']}{label}")
    
    return "```mermaid\n" + "\n".join(mermaid_lines) + "\n```"

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
    # svg = '<svg aria-roledescription="stateDiagram" role="graphics-document document" viewBox="0 0 481.77606201171875 462" style="max-width: 481.77606201171875px;" class="statediagram" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns="http://www.w3.org/2000/svg" width="100%" id="mermaid-jb4fwweijp"><style>#mermaid-jb4fwweijp{font-family:ui-sans-serif,-apple-system,system-ui,Segoe UI,Helvetica;font-size:16px;fill:#333;}@keyframes edge-animation-frame{from{stroke-dashoffset:0;}}@keyframes dash{to{stroke-dashoffset:0;}}#mermaid-jb4fwweijp .edge-animation-slow{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 50s linear infinite;stroke-linecap:round;}#mermaid-jb4fwweijp .edge-animation-fast{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 20s linear infinite;stroke-linecap:round;}#mermaid-jb4fwweijp .error-icon{fill:#dddddd;}#mermaid-jb4fwweijp .error-text{fill:#222222;stroke:#222222;}#mermaid-jb4fwweijp .edge-thickness-normal{stroke-width:1px;}#mermaid-jb4fwweijp .edge-thickness-thick{stroke-width:3.5px;}#mermaid-jb4fwweijp .edge-pattern-solid{stroke-dasharray:0;}#mermaid-jb4fwweijp .edge-thickness-invisible{stroke-width:0;fill:none;}#mermaid-jb4fwweijp .edge-pattern-dashed{stroke-dasharray:3;}#mermaid-jb4fwweijp .edge-pattern-dotted{stroke-dasharray:2;}#mermaid-jb4fwweijp .marker{fill:#999;stroke:#999;}#mermaid-jb4fwweijp .marker.cross{stroke:#999;}#mermaid-jb4fwweijp svg{font-family:ui-sans-serif,-apple-system,system-ui,Segoe UI,Helvetica;font-size:16px;}#mermaid-jb4fwweijp p{margin:0;}#mermaid-jb4fwweijp defs #statediagram-barbEnd{fill:#999;stroke:#999;}#mermaid-jb4fwweijp g.stateGroup text{fill:#dddddd;stroke:none;font-size:10px;}#mermaid-jb4fwweijp g.stateGroup text{fill:#333;stroke:none;font-size:10px;}#mermaid-jb4fwweijp g.stateGroup .state-title{font-weight:bolder;fill:#333;}#mermaid-jb4fwweijp g.stateGroup rect{fill:#ffffff;stroke:#dddddd;}#mermaid-jb4fwweijp g.stateGroup line{stroke:#999;stroke-width:1;}#mermaid-jb4fwweijp .transition{stroke:#999;stroke-width:1;fill:none;}#mermaid-jb4fwweijp .stateGroup .composit{fill:#f4f4f4;border-bottom:1px;}#mermaid-jb4fwweijp .stateGroup .alt-composit{fill:#e0e0e0;border-bottom:1px;}#mermaid-jb4fwweijp .state-note{stroke:#e6d280;fill:#fff5ad;}#mermaid-jb4fwweijp .state-note text{fill:#333;stroke:none;font-size:10px;}#mermaid-jb4fwweijp .stateLabel .box{stroke:none;stroke-width:0;fill:#ffffff;opacity:0.5;}#mermaid-jb4fwweijp .edgeLabel .label rect{fill:#ffffff;opacity:0.5;}#mermaid-jb4fwweijp .edgeLabel{background-color:#ffffff;text-align:center;}#mermaid-jb4fwweijp .edgeLabel p{background-color:#ffffff;}#mermaid-jb4fwweijp .edgeLabel rect{opacity:0.5;background-color:#ffffff;fill:#ffffff;}#mermaid-jb4fwweijp .edgeLabel .label text{fill:#333;}#mermaid-jb4fwweijp .label div .edgeLabel{color:#333;}#mermaid-jb4fwweijp .stateLabel text{fill:#333;font-size:10px;font-weight:bold;}#mermaid-jb4fwweijp .node circle.state-start{fill:#999;stroke:#999;}#mermaid-jb4fwweijp .node .fork-join{fill:#999;stroke:#999;}#mermaid-jb4fwweijp .node circle.state-end{fill:#dddddd;stroke:#f4f4f4;stroke-width:1.5;}#mermaid-jb4fwweijp .end-state-inner{fill:#f4f4f4;stroke-width:1.5;}#mermaid-jb4fwweijp .node rect{fill:#ffffff;stroke:#dddddd;stroke-width:1px;}#mermaid-jb4fwweijp .node polygon{fill:#ffffff;stroke:#dddddd;stroke-width:1px;}#mermaid-jb4fwweijp #statediagram-barbEnd{fill:#999;}#mermaid-jb4fwweijp .statediagram-cluster rect{fill:#ffffff;stroke:#dddddd;stroke-width:1px;}#mermaid-jb4fwweijp .cluster-label,#mermaid-jb4fwweijp .nodeLabel{color:#333;}#mermaid-jb4fwweijp .statediagram-cluster rect.outer{rx:5px;ry:5px;}#mermaid-jb4fwweijp .statediagram-state .divider{stroke:#dddddd;}#mermaid-jb4fwweijp .statediagram-state .title-state{rx:5px;ry:5px;}#mermaid-jb4fwweijp .statediagram-cluster.statediagram-cluster .inner{fill:#f4f4f4;}#mermaid-jb4fwweijp .statediagram-cluster.statediagram-cluster-alt .inner{fill:#f8f8f8;}#mermaid-jb4fwweijp .statediagram-cluster .inner{rx:0;ry:0;}#mermaid-jb4fwweijp .statediagram-state rect.basic{rx:5px;ry:5px;}#mermaid-jb4fwweijp .statediagram-state rect.divider{stroke-dasharray:10,10;fill:#f8f8f8;}#mermaid-jb4fwweijp .note-edge{stroke-dasharray:5;}#mermaid-jb4fwweijp .statediagram-note rect{fill:#fff5ad;stroke:#e6d280;stroke-width:1px;rx:0;ry:0;}#mermaid-jb4fwweijp .statediagram-note rect{fill:#fff5ad;stroke:#e6d280;stroke-width:1px;rx:0;ry:0;}#mermaid-jb4fwweijp .statediagram-note text{fill:#333;}#mermaid-jb4fwweijp .statediagram-note .nodeLabel{color:#333;}#mermaid-jb4fwweijp .statediagram .edgeLabel{color:red;}#mermaid-jb4fwweijp #dependencyStart,#mermaid-jb4fwweijp #dependencyEnd{fill:#999;stroke:#999;stroke-width:1;}#mermaid-jb4fwweijp .statediagramTitleText{text-anchor:middle;font-size:18px;fill:#333;}#mermaid-jb4fwweijp :root{--mermaid-font-family:"trebuchet ms",verdana,arial,sans-serif;}</style><g><defs><marker orient="auto" markerUnits="userSpaceOnUse" markerHeight="14" markerWidth="20" refY="7" refX="19" id="mermaid-jb4fwweijp_stateDiagram-barbEnd"><path d="M 19,7 L9,13 L14,7 L9,1 Z"></path></marker></defs><g class="root"><g class="clusters"></g><g class="edgePaths"><path marker-end="url(#mermaid-jb4fwweijp_stateDiagram-barbEnd)" style="fill:none;" class="edge-thickness-normal edge-pattern-solid transition" id="edge0" d="M357.508,22L357.508,26.167C357.508,30.333,357.508,38.667,357.508,47C357.508,55.333,357.508,63.667,357.508,67.833L357.508,72"></path><path marker-end="url(#mermaid-jb4fwweijp_stateDiagram-barbEnd)" style="fill:none;" class="edge-thickness-normal edge-pattern-solid transition" id="edge1" d="M318.716,100.553L282.094,108.627C245.472,116.702,172.228,132.851,155.441,148.593C138.654,164.336,178.323,179.671,198.158,187.339L217.992,195.007"></path><path marker-end="url(#mermaid-jb4fwweijp_stateDiagram-barbEnd)" style="fill:none;" class="edge-thickness-normal edge-pattern-solid transition" id="edge2" d="M217.992,219.332L202.468,226.61C186.944,233.888,155.897,248.444,140.373,261.889C124.849,275.333,124.849,287.667,124.849,293.833L124.849,300"></path><path marker-end="url(#mermaid-jb4fwweijp_stateDiagram-barbEnd)" style="fill:none;" class="edge-thickness-normal edge-pattern-solid transition" id="edge3" d="M246.366,226L246.346,232.167C246.326,238.333,246.287,250.667,251.076,263C255.866,275.333,265.484,287.667,270.294,293.833L275.103,300"></path><path marker-end="url(#mermaid-jb4fwweijp_stateDiagram-barbEnd)" style="fill:none;" class="edge-thickness-normal edge-pattern-solid transition" id="edge4" d="M241.577,186L240.08,179.833C238.584,173.667,235.592,161.333,248.448,148.617C261.305,135.901,290.01,122.801,304.363,116.252L318.716,109.702"></path><path marker-end="url(#mermaid-jb4fwweijp_stateDiagram-barbEnd)" style="fill:none;" class="edge-thickness-normal edge-pattern-solid transition" id="edge5" d="M124.849,340L124.849,346.167C124.849,352.333,124.849,364.667,136.506,377C148.163,389.333,171.478,401.667,183.135,407.833L194.792,414"></path><path marker-end="url(#mermaid-jb4fwweijp_stateDiagram-barbEnd)" style="fill:none;" class="edge-thickness-normal edge-pattern-solid transition" id="edge6" d="M290.193,417.416L313.587,410.68C336.981,403.944,383.769,390.472,407.163,374.236C430.557,358,430.557,339,430.557,320C430.557,301,430.557,282,404.609,264.467C378.661,246.934,326.764,230.869,300.816,222.836L274.867,214.803"></path><path marker-end="url(#mermaid-jb4fwweijp_stateDiagram-barbEnd)" style="fill:none;" class="edge-thickness-normal edge-pattern-solid transition" id="edge7" d="M306.298,300L311.107,293.833C315.917,287.667,325.535,275.333,320.297,262.712C315.058,250.09,294.963,237.18,284.915,230.725L274.867,224.269"></path><path marker-end="url(#mermaid-jb4fwweijp_stateDiagram-barbEnd)" style="fill:none;" class="edge-thickness-normal edge-pattern-solid transition" id="edge8" d="M274.867,190.643L287.719,183.702C300.571,176.762,326.275,162.881,339.725,149.774C353.175,136.667,354.372,124.333,354.97,118.167L355.568,112"></path><path marker-end="url(#mermaid-jb4fwweijp_stateDiagram-barbEnd)" style="fill:none;" class="edge-thickness-normal edge-pattern-solid transition" id="edge9" d="M389.515,112L399.384,118.167C409.253,124.333,428.991,136.667,438.86,151.167C448.729,165.667,448.729,182.333,448.729,190.667L448.729,199"></path></g><g class="edgeLabels"><g class="edgeLabel"><g transform="translate(0, 0)" class="label"><foreignObject height="0" width="0"><div style="display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;" class="labelBkg" xmlns="http://www.w3.org/1999/xhtml"><span class="edgeLabel"></span></div></foreignObject></g></g><g transform="translate(98.984375, 149)" class="edgeLabel"><g transform="translate(-90.984375, -12)" class="label"><foreignObject height="24" width="181.96875"><div style="display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;" class="labelBkg" xmlns="http://www.w3.org/1999/xhtml"><span class="edgeLabel"><p>connect()/bind()/listen()</p></span></div></foreignObject></g></g><g transform="translate(124.84895706176758, 263)" class="edgeLabel"><g transform="translate(-35.833335876464844, -12)" class="label"><foreignObject height="24" width="71.66667175292969"><div style="display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;" class="labelBkg" xmlns="http://www.w3.org/1999/xhtml"><span class="edgeLabel"><p>connect()</p></span></div></foreignObject></g></g><g transform="translate(246.2473964691162, 263)" class="edgeLabel"><g transform="translate(-25.6875, -12)" class="label"><foreignObject height="24" width="51.375"><div style="display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;" class="labelBkg" xmlns="http://www.w3.org/1999/xhtml"><span class="edgeLabel"><p>listen()</p></span></div></foreignObject></g></g><g transform="translate(232.5989589691162, 149)" class="edgeLabel"><g transform="translate(-22.63020896911621, -12)" class="label"><foreignObject height="24" width="45.26041793823242"><div style="display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;" class="labelBkg" xmlns="http://www.w3.org/1999/xhtml"><span class="edgeLabel"><p>bind()</p></span></div></foreignObject></g></g><g transform="translate(124.84895706176758, 377)" class="edgeLabel"><g transform="translate(-80.578125, -12)" class="label"><foreignObject height="24" width="161.15625"><div style="display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;" class="labelBkg" xmlns="http://www.w3.org/1999/xhtml"><span class="edgeLabel"><p>handshake_complete</p></span></div></foreignObject></g></g><g transform="translate(430.5572929382324, 320)" class="edgeLabel"><g transform="translate(-43.21875, -12)" class="label"><foreignObject height="24" width="86.4375"><div style="display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;" class="labelBkg" xmlns="http://www.w3.org/1999/xhtml"><span class="edgeLabel"><p>shutdown()</p></span></div></foreignObject></g></g><g transform="translate(335.1536464691162, 263)" class="edgeLabel"><g transform="translate(-43.21875, -12)" class="label"><foreignObject height="24" width="86.4375"><div style="display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;" class="labelBkg" xmlns="http://www.w3.org/1999/xhtml"><span class="edgeLabel"><p>shutdown()</p></span></div></foreignObject></g></g><g transform="translate(351.9791679382324, 149)" class="edgeLabel"><g transform="translate(-76.75, -12)" class="label"><foreignObject height="24" width="153.5"><div style="display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;" class="labelBkg" xmlns="http://www.w3.org/1999/xhtml"><span class="edgeLabel"><p>operation_complete</p></span></div></foreignObject></g></g><g class="edgeLabel"><g transform="translate(0, 0)" class="label"><foreignObject height="0" width="0"><div style="display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;" class="labelBkg" xmlns="http://www.w3.org/1999/xhtml"><span class="edgeLabel"></span></div></foreignObject></g></g></g><g class="nodes"><g transform="translate(357.5078134536743, 15)" id="state-root_start-0" class="node default"><circle height="14" width="14" r="7" class="state-start"></circle></g><g transform="translate(357.5078134536743, 92)" id="state-CLOSED-9" class="node  statediagram-state"><rect height="40" width="77.58333587646484" y="-20" x="-38.79166793823242" ry="5" rx="5" style="" class="basic label-container"></rect><g transform="translate(-30.791667938232422, -12)" style="" class="label"><rect></rect><foreignObject height="24" width="61.583335876464844"><div style="display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;" xmlns="http://www.w3.org/1999/xhtml"><span class="nodeLabel"><p>CLOSED</p></span></div></foreignObject></g></g><g transform="translate(246.42968845367432, 206)" id="state-BUSY-8" class="node  statediagram-state"><rect height="40" width="56.875" y="-20" x="-28.4375" ry="5" rx="5" style="" class="basic label-container"></rect><g transform="translate(-20.4375, -12)" style="" class="label"><rect></rect><foreignObject height="24" width="40.875"><div style="display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;" xmlns="http://www.w3.org/1999/xhtml"><span class="nodeLabel"><p>BUSY</p></span></div></foreignObject></g></g><g transform="translate(124.84895706176758, 320)" id="state-CONNECTING-5" class="node  statediagram-state"><rect height="40" width="123.8125" y="-20" x="-61.90625" ry="5" rx="5" style="" class="basic label-container"></rect><g transform="translate(-53.90625, -12)" style="" class="label"><rect></rect><foreignObject height="24" width="107.8125"><div style="display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;" xmlns="http://www.w3.org/1999/xhtml"><span class="nodeLabel"><p>CONNECTING</p></span></div></foreignObject></g></g><g transform="translate(290.7005214691162, 320)" id="state-LISTENING-7" class="node  statediagram-state"><rect height="40" width="98.73958587646484" y="-20" x="-49.36979293823242" ry="5" rx="5" style="" class="basic label-container"></rect><g transform="translate(-41.36979293823242, -12)" style="" class="label"><rect></rect><foreignObject height="24" width="82.73958587646484"><div style="display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;" xmlns="http://www.w3.org/1999/xhtml"><span class="nodeLabel"><p>LISTENING</p></span></div></foreignObject></g></g><g transform="translate(232.5989589691162, 434)" id="state-CONNECTED-6" class="node  statediagram-state"><rect height="40" width="115.1875" y="-20" x="-57.59375" ry="5" rx="5" style="" class="basic label-container"></rect><g transform="translate(-49.59375, -12)" style="" class="label"><rect></rect><foreignObject height="24" width="99.1875"><div style="display: table-cell; white-space: nowrap; line-height: 1.5; max-width: 200px; text-align: center;" xmlns="http://www.w3.org/1999/xhtml"><span class="nodeLabel"><p>CONNECTED</p></span></div></foreignObject></g></g><g transform="translate(448.7291679382324, 206)" id="state-root_end-9" class="node default"><g><path style="" fill="#ffffff" stroke-width="0" stroke="none" d="M7 0 C7 0.40517908122283747, 6.964012880168563 0.816513743121899, 6.893654271085456 1.2155372436685123 C6.823295662002349 1.6145607442151257, 6.716427752933756 2.013397210557766, 6.5778483455013586 2.394141003279681 C6.439268938068961 2.7748847960015954, 6.26476736710249 3.149104622578984, 6.062177826491071 3.4999999999999996 C5.859588285879653 3.8508953774210153, 5.622755194947063 4.189128084166967, 5.362311101832846 4.499513267805774 C5.10186700871863 4.809898451444582, 4.809898451444583 5.10186700871863, 4.499513267805775 5.362311101832846 C4.189128084166968 5.622755194947063, 3.8508953774210166 5.859588285879652, 3.500000000000001 6.06217782649107 C3.149104622578985 6.264767367102489, 2.7748847960015963 6.439268938068961, 2.3941410032796817 6.5778483455013586 C2.013397210557767 6.716427752933756, 1.6145607442151264 6.823295662002349, 1.2155372436685128 6.893654271085456 C0.8165137431218992 6.964012880168563, 0.4051790812228379 7, 4.286263797015736e-16 7 C-0.405179081222837 7, -0.8165137431218985 6.964012880168563, -1.2155372436685121 6.893654271085456 C-1.6145607442151257 6.823295662002349, -2.0133972105577667 6.716427752933756, -2.394141003279681 6.5778483455013586 C-2.774884796001595 6.439268938068961, -3.149104622578983 6.26476736710249, -3.4999999999999982 6.062177826491071 C-3.8508953774210135 5.859588285879653, -4.189128084166966 5.6227551949470636, -4.499513267805773 5.362311101832848 C-4.809898451444581 5.101867008718632, -5.101867008718628 4.809898451444586, -5.3623111018328435 4.499513267805779 C-5.622755194947059 4.189128084166971, -5.859588285879649 3.8508953774210206, -6.062177826491068 3.5000000000000053 C-6.264767367102486 3.14910462257899, -6.439268938068958 2.774884796001602, -6.577848345501356 2.394141003279688 C-6.716427752933754 2.0133972105577738, -6.823295662002347 1.614560744215134, -6.893654271085454 1.215537243668521 C-6.9640128801685615 0.816513743121908, -6.999999999999999 0.4051790812228472, -7 1.0183126166254463e-14 C-7.000000000000001 -0.40517908122282686, -6.964012880168565 -0.8165137431218878, -6.893654271085459 -1.215537243668501 C-6.823295662002352 -1.6145607442151142, -6.716427752933759 -2.0133972105577542, -6.577848345501363 -2.394141003279669 C-6.439268938068967 -2.7748847960015834, -6.264767367102496 -3.149104622578972, -6.062177826491078 -3.4999999999999876 C-5.859588285879661 -3.8508953774210033, -5.6227551949470715 -4.1891280841669545, -5.362311101832856 -4.499513267805763 C-5.10186700871864 -4.809898451444571, -4.809898451444594 -5.10186700871862, -4.499513267805787 -5.362311101832836 C-4.189128084166979 -5.622755194947053, -3.850895377421028 -5.859588285879643, -3.5000000000000133 -6.062177826491062 C-3.1491046225789985 -6.264767367102482, -2.774884796001611 -6.439268938068954, -2.3941410032796973 -6.577848345501353 C-2.0133972105577835 -6.716427752933752, -1.6145607442151435 -6.823295662002345, -1.2155372436685306 -6.893654271085453 C-0.8165137431219176 -6.9640128801685615, -0.40517908122285695 -6.999999999999999, -1.9937625952807352e-14 -7 C0.4051790812228171 -7.000000000000001, 0.8165137431218781 -6.964012880168565, 1.2155372436684913 -6.89365427108546 C1.6145607442151044 -6.823295662002354, 2.013397210557745 -6.716427752933763, 2.3941410032796595 -6.5778483455013665 C2.774884796001574 -6.43926893806897, 3.149104622578963 -6.2647673671025, 3.499999999999979 -6.062177826491083 C3.8508953774209953 -5.859588285879665, 4.189128084166947 -5.622755194947077, 4.499513267805756 -5.362311101832862 C4.809898451444564 -5.1018670087186475, 5.101867008718613 -4.809898451444602, 5.362311101832829 -4.499513267805796 C5.622755194947046 -4.189128084166989, 5.859588285879637 -3.8508953774210393, 6.062177826491056 -3.500000000000025 C6.2647673671024755 -3.1491046225790105, 6.439268938068949 -2.774884796001623, 6.577848345501348 -2.3941410032797092 C6.716427752933747 -2.0133972105577955, 6.823295662002342 -1.6145607442151562, 6.893654271085451 -1.2155372436685434 C6.96401288016856 -0.8165137431219307, 6.982275711847575 -0.2025895406114567, 7 -3.2800750208310675e-14 C7.017724288152425 0.2025895406113911, 7.017724288152424 -0.2025895406114242, 7 0"></path><path style="" fill="none" stroke-width="2" stroke="#999" d="M7 0 C7 0.40517908122283747, 6.964012880168563 0.816513743121899, 6.893654271085456 1.2155372436685123 C6.823295662002349 1.6145607442151257, 6.716427752933756 2.013397210557766, 6.5778483455013586 2.394141003279681 C6.439268938068961 2.7748847960015954, 6.26476736710249 3.149104622578984, 6.062177826491071 3.4999999999999996 C5.859588285879653 3.8508953774210153, 5.622755194947063 4.189128084166967, 5.362311101832846 4.499513267805774 C5.10186700871863 4.809898451444582, 4.809898451444583 5.10186700871863, 4.499513267805775 5.362311101832846 C4.189128084166968 5.622755194947063, 3.8508953774210166 5.859588285879652, 3.500000000000001 6.06217782649107 C3.149104622578985 6.264767367102489, 2.7748847960015963 6.439268938068961, 2.3941410032796817 6.5778483455013586 C2.013397210557767 6.716427752933756, 1.6145607442151264 6.823295662002349, 1.2155372436685128 6.893654271085456 C0.8165137431218992 6.964012880168563, 0.4051790812228379 7, 4.286263797015736e-16 7 C-0.405179081222837 7, -0.8165137431218985 6.964012880168563, -1.2155372436685121 6.893654271085456 C-1.6145607442151257 6.823295662002349, -2.0133972105577667 6.716427752933756, -2.394141003279681 6.5778483455013586 C-2.774884796001595 6.439268938068961, -3.149104622578983 6.26476736710249, -3.4999999999999982 6.062177826491071 C-3.8508953774210135 5.859588285879653, -4.189128084166966 5.6227551949470636, -4.499513267805773 5.362311101832848 C-4.809898451444581 5.101867008718632, -5.101867008718628 4.809898451444586, -5.3623111018328435 4.499513267805779 C-5.622755194947059 4.189128084166971, -5.859588285879649 3.8508953774210206, -6.062177826491068 3.5000000000000053 C-6.264767367102486 3.14910462257899, -6.439268938068958 2.774884796001602, -6.577848345501356 2.394141003279688 C-6.716427752933754 2.0133972105577738, -6.823295662002347 1.614560744215134, -6.893654271085454 1.215537243668521 C-6.9640128801685615 0.816513743121908, -6.999999999999999 0.4051790812228472, -7 1.0183126166254463e-14 C-7.000000000000001 -0.40517908122282686, -6.964012880168565 -0.8165137431218878, -6.893654271085459 -1.215537243668501 C-6.823295662002352 -1.6145607442151142, -6.716427752933759 -2.0133972105577542, -6.577848345501363 -2.394141003279669 C-6.439268938068967 -2.7748847960015834, -6.264767367102496 -3.149104622578972, -6.062177826491078 -3.4999999999999876 C-5.859588285879661 -3.8508953774210033, -5.6227551949470715 -4.1891280841669545, -5.362311101832856 -4.499513267805763 C-5.10186700871864 -4.809898451444571, -4.809898451444594 -5.10186700871862, -4.499513267805787 -5.362311101832836 C-4.189128084166979 -5.622755194947053, -3.850895377421028 -5.859588285879643, -3.5000000000000133 -6.062177826491062 C-3.1491046225789985 -6.264767367102482, -2.774884796001611 -6.439268938068954, -2.3941410032796973 -6.577848345501353 C-2.0133972105577835 -6.716427752933752, -1.6145607442151435 -6.823295662002345, -1.2155372436685306 -6.893654271085453 C-0.8165137431219176 -6.9640128801685615, -0.40517908122285695 -6.999999999999999, -1.9937625952807352e-14 -7 C0.4051790812228171 -7.000000000000001, 0.8165137431218781 -6.964012880168565, 1.2155372436684913 -6.89365427108546 C1.6145607442151044 -6.823295662002354, 2.013397210557745 -6.716427752933763, 2.3941410032796595 -6.5778483455013665 C2.774884796001574 -6.43926893806897, 3.149104622578963 -6.2647673671025, 3.499999999999979 -6.062177826491083 C3.8508953774209953 -5.859588285879665, 4.189128084166947 -5.622755194947077, 4.499513267805756 -5.362311101832862 C4.809898451444564 -5.1018670087186475, 5.101867008718613 -4.809898451444602, 5.362311101832829 -4.499513267805796 C5.622755194947046 -4.189128084166989, 5.859588285879637 -3.8508953774210393, 6.062177826491056 -3.500000000000025 C6.2647673671024755 -3.1491046225790105, 6.439268938068949 -2.774884796001623, 6.577848345501348 -2.3941410032797092 C6.716427752933747 -2.0133972105577955, 6.823295662002342 -1.6145607442151562, 6.893654271085451 -1.2155372436685434 C6.96401288016856 -0.8165137431219307, 6.982275711847575 -0.2025895406114567, 7 -3.2800750208310675e-14 C7.017724288152425 0.2025895406113911, 7.017724288152424 -0.2025895406114242, 7 0"></path><g><path style="" fill="#dddddd" stroke-width="0" stroke="none" d="M2.5 0 C2.5 0.14470681472244193, 2.487147457203058 0.29161205111496386, 2.46201938253052 0.4341204441673258 C2.436891307857982 0.5766288372196877, 2.3987241974763416 0.7190704323420595, 2.3492315519647713 0.8550503583141718 C2.299738906453201 0.991030284286284, 2.2374169168223177 1.124680222349637, 2.165063509461097 1.2499999999999998 C2.092710102099876 1.3753197776503625, 2.0081268553382365 1.496117172916774, 1.915111107797445 1.6069690242163481 C1.8220953602566536 1.7178208755159223, 1.7178208755159226 1.8220953602566536, 1.6069690242163484 1.915111107797445 C1.4961171729167742 2.0081268553382365, 1.375319777650363 2.0927101020998755, 1.2500000000000002 2.1650635094610964 C1.1246802223496375 2.2374169168223172, 0.9910302842862845 2.2997389064532, 0.8550503583141721 2.349231551964771 C0.7190704323420597 2.3987241974763416, 0.576628837219688 2.436891307857982, 0.43412044416732604 2.46201938253052 C0.291612051114964 2.487147457203058, 0.14470681472244212 2.5, 1.5308084989341916e-16 2.5 C-0.1447068147224418 2.5, -0.2916120511149638 2.487147457203058, -0.43412044416732576 2.46201938253052 C-0.5766288372196877 2.436891307857982, -0.7190704323420595 2.3987241974763416, -0.8550503583141718 2.3492315519647713 C-0.991030284286284 2.299738906453201, -1.124680222349637 2.2374169168223177, -1.2499999999999996 2.165063509461097 C-1.375319777650362 2.092710102099876, -1.4961171729167733 2.008126855338237, -1.6069690242163475 1.9151111077974459 C-1.7178208755159217 1.8220953602566548, -1.822095360256653 1.7178208755159234, -1.9151111077974443 1.6069690242163495 C-2.0081268553382357 1.4961171729167755, -2.0927101020998746 1.3753197776503645, -2.1650635094610955 1.250000000000002 C-2.2374169168223164 1.1246802223496395, -2.2997389064531992 0.9910302842862865, -2.34923155196477 0.8550503583141743 C-2.3987241974763407 0.7190704323420621, -2.436891307857981 0.5766288372196907, -2.4620193825305194 0.434120444167329 C-2.487147457203058 0.29161205111496724, -2.5 0.14470681472244545, -2.5 3.636830773662308e-15 C-2.5 -0.14470681472243818, -2.4871474572030587 -0.2916120511149599, -2.4620193825305208 -0.4341204441673218 C-2.436891307857983 -0.5766288372196837, -2.398724197476343 -0.7190704323420553, -2.3492315519647726 -0.8550503583141675 C-2.2997389064532023 -0.9910302842862798, -2.23741691682232 -1.1246802223496328, -2.165063509461099 -1.2499999999999956 C-2.092710102099878 -1.3753197776503583, -2.00812685533824 -1.4961171729167695, -1.9151111077974488 -1.606969024216344 C-1.8220953602566576 -1.7178208755159183, -1.7178208755159263 -1.82209536025665, -1.6069690242163523 -1.9151111077974416 C-1.4961171729167784 -2.0081268553382334, -1.3753197776503672 -2.0927101020998724, -1.2500000000000047 -2.1650635094610937 C-1.1246802223496422 -2.237416916822315, -0.9910302842862897 -2.299738906453198, -0.8550503583141776 -2.3492315519647686 C-0.7190704323420656 -2.3987241974763394, -0.5766288372196942 -2.4368913078579806, -0.43412044416733236 -2.462019382530519 C-0.29161205111497057 -2.4871474572030574, -0.1447068147224489 -2.4999999999999996, -7.120580697431198e-15 -2.5 C0.14470681472243463 -2.5000000000000004, 0.29161205111495647 -2.487147457203059, 0.4341204441673183 -2.4620193825305217 C0.5766288372196802 -2.436891307857984, 0.7190704323420518 -2.3987241974763442, 0.8550503583141642 -2.349231551964774 C0.9910302842862766 -2.2997389064532037, 1.1246802223496295 -2.2374169168223212, 1.2499999999999925 -2.165063509461101 C1.3753197776503554 -2.0927101020998804, 1.4961171729167668 -2.008126855338242, 1.6069690242163412 -1.915111107797451 C1.7178208755159157 -1.82209536025666, 1.8220953602566472 -1.7178208755159294, 1.915111107797439 -1.6069690242163557 C2.0081268553382308 -1.496117172916782, 2.09271010209987 -1.3753197776503712, 2.1650635094610915 -1.2500000000000089 C2.237416916822313 -1.1246802223496466, 2.299738906453196 -0.9910302842862939, 2.3492315519647673 -0.855050358314182 C2.3987241974763385 -0.71907043234207, 2.4368913078579792 -0.5766288372196986, 2.462019382530518 -0.4341204441673369 C2.487147457203057 -0.29161205111497523, 2.4936698970884197 -0.07235340736123454, 2.5 -1.1714553645825241e-14 C2.5063301029115803 0.07235340736121111, 2.50633010291158 -0.07235340736122292, 2.5 0"></path><path style="" fill="none" stroke-width="2" stroke="#dddddd" d="M2.5 0 C2.5 0.14470681472244193, 2.487147457203058 0.29161205111496386, 2.46201938253052 0.4341204441673258 C2.436891307857982 0.5766288372196877, 2.3987241974763416 0.7190704323420595, 2.3492315519647713 0.8550503583141718 C2.299738906453201 0.991030284286284, 2.2374169168223177 1.124680222349637, 2.165063509461097 1.2499999999999998 C2.092710102099876 1.3753197776503625, 2.0081268553382365 1.496117172916774, 1.915111107797445 1.6069690242163481 C1.8220953602566536 1.7178208755159223, 1.7178208755159226 1.8220953602566536, 1.6069690242163484 1.915111107797445 C1.4961171729167742 2.0081268553382365, 1.375319777650363 2.0927101020998755, 1.2500000000000002 2.1650635094610964 C1.1246802223496375 2.2374169168223172, 0.9910302842862845 2.2997389064532, 0.8550503583141721 2.349231551964771 C0.7190704323420597 2.3987241974763416, 0.576628837219688 2.436891307857982, 0.43412044416732604 2.46201938253052 C0.291612051114964 2.487147457203058, 0.14470681472244212 2.5, 1.5308084989341916e-16 2.5 C-0.1447068147224418 2.5, -0.2916120511149638 2.487147457203058, -0.43412044416732576 2.46201938253052 C-0.5766288372196877 2.436891307857982, -0.7190704323420595 2.3987241974763416, -0.8550503583141718 2.3492315519647713 C-0.991030284286284 2.299738906453201, -1.124680222349637 2.2374169168223177, -1.2499999999999996 2.165063509461097 C-1.375319777650362 2.092710102099876, -1.4961171729167733 2.008126855338237, -1.6069690242163475 1.9151111077974459 C-1.7178208755159217 1.8220953602566548, -1.822095360256653 1.7178208755159234, -1.9151111077974443 1.6069690242163495 C-2.0081268553382357 1.4961171729167755, -2.0927101020998746 1.3753197776503645, -2.1650635094610955 1.250000000000002 C-2.2374169168223164 1.1246802223496395, -2.2997389064531992 0.9910302842862865, -2.34923155196477 0.8550503583141743 C-2.3987241974763407 0.7190704323420621, -2.436891307857981 0.5766288372196907, -2.4620193825305194 0.434120444167329 C-2.487147457203058 0.29161205111496724, -2.5 0.14470681472244545, -2.5 3.636830773662308e-15 C-2.5 -0.14470681472243818, -2.4871474572030587 -0.2916120511149599, -2.4620193825305208 -0.4341204441673218 C-2.436891307857983 -0.5766288372196837, -2.398724197476343 -0.7190704323420553, -2.3492315519647726 -0.8550503583141675 C-2.2997389064532023 -0.9910302842862798, -2.23741691682232 -1.1246802223496328, -2.165063509461099 -1.2499999999999956 C-2.092710102099878 -1.3753197776503583, -2.00812685533824 -1.4961171729167695, -1.9151111077974488 -1.606969024216344 C-1.8220953602566576 -1.7178208755159183, -1.7178208755159263 -1.82209536025665, -1.6069690242163523 -1.9151111077974416 C-1.4961171729167784 -2.0081268553382334, -1.3753197776503672 -2.0927101020998724, -1.2500000000000047 -2.1650635094610937 C-1.1246802223496422 -2.237416916822315, -0.9910302842862897 -2.299738906453198, -0.8550503583141776 -2.3492315519647686 C-0.7190704323420656 -2.3987241974763394, -0.5766288372196942 -2.4368913078579806, -0.43412044416733236 -2.462019382530519 C-0.29161205111497057 -2.4871474572030574, -0.1447068147224489 -2.4999999999999996, -7.120580697431198e-15 -2.5 C0.14470681472243463 -2.5000000000000004, 0.29161205111495647 -2.487147457203059, 0.4341204441673183 -2.4620193825305217 C0.5766288372196802 -2.436891307857984, 0.7190704323420518 -2.3987241974763442, 0.8550503583141642 -2.349231551964774 C0.9910302842862766 -2.2997389064532037, 1.1246802223496295 -2.2374169168223212, 1.2499999999999925 -2.165063509461101 C1.3753197776503554 -2.0927101020998804, 1.4961171729167668 -2.008126855338242, 1.6069690242163412 -1.915111107797451 C1.7178208755159157 -1.82209536025666, 1.8220953602566472 -1.7178208755159294, 1.915111107797439 -1.6069690242163557 C2.0081268553382308 -1.496117172916782, 2.09271010209987 -1.3753197776503712, 2.1650635094610915 -1.2500000000000089 C2.237416916822313 -1.1246802223496466, 2.299738906453196 -0.9910302842862939, 2.3492315519647673 -0.855050358314182 C2.3987241974763385 -0.71907043234207, 2.4368913078579792 -0.5766288372196986, 2.462019382530518 -0.4341204441673369 C2.487147457203057 -0.29161205111497523, 2.4936698970884197 -0.07235340736123454, 2.5 -1.1714553645825241e-14 C2.5063301029115803 0.07235340736121111, 2.50633010291158 -0.07235340736122292, 2.5 0"></path></g></g></g></g></g></g></svg>'

    # div_node = BeautifulSoup(f'{svg}', 'html.parser').find('svg')

    # convert_statediagram_svg_to_mermaid_text(div_node)

    # return


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
