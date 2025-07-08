import re
import json
from bs4 import BeautifulSoup
from typing import Dict, List, Tuple, Optional, Set, Any

def convert_flowchart_svg_to_mermaid_text(svg_element: BeautifulSoup) -> Optional[str]:
    """将流程图 SVG 转换为 Mermaid 文本"""
    if not svg_element:
        return None
    
    print("Starting flowchart conversion with hierarchical logic...")
    mermaid_code = "flowchart TD\n\n"
    nodes: Dict[str, Dict] = {}
    clusters: Dict[str, Dict] = {}
    parent_map: Dict[str, str] = {}
    all_elements: Dict[str, Dict] = {}
    
    # 1. 收集所有节点
    for node_el in svg_element.select('g.node'):
        svg_id = node_el.get('id')
        if not svg_id:
            continue
            
        # 提取文本内容
        text_content = ""
        p_element = node_el.select_one('.label foreignObject div > span > p, .label foreignObject div > p')
        if p_element:
            raw_parts = []
            for child in p_element.children:
                if child.name is None:  # 文本节点
                    raw_parts.append(child.string.strip())
                elif child.name.lower() == 'br':
                    raw_parts.append('<br>')
                elif child.name:  # 元素节点
                    raw_parts.append(child.get_text(strip=True))
            text_content = ''.join(raw_parts).strip().replace('"', '#quot;')
        
        if not text_content.strip():
            node_label = node_el.select_one('.nodeLabel, .label, foreignObject span, foreignObject div, text')
            if node_label and node_label.get_text(strip=True):
                text_content = node_label.get_text(strip=True).replace('"', '#quot;')
        
        mermaid_id = re.sub(r'^flowchart-', '', svg_id)
        mermaid_id = re.sub(r'-\d+$', '', mermaid_id)
        
        # 使用近似边界框计算
        bbox = node_el.get('bbox', {})
        if bbox.get('width', 0) > 0 or bbox.get('height', 0) > 0:
            nodes[svg_id] = {
                'type': 'node',
                'mermaid_id': mermaid_id,
                'text': text_content,
                'svg_id': svg_id,
                'bbox': bbox
            }
            all_elements[svg_id] = nodes[svg_id]
    
    # 2. 收集所有集群
    for cluster_el in svg_element.select('g.cluster'):
        svg_id = cluster_el.get('id')
        if not svg_id:
            continue
            
        title = ""
        label_el = cluster_el.select_one('.cluster-label, .label')
        if label_el and label_el.get_text(strip=True):
            title = label_el.get_text(strip=True)
        
        if not title:
            title = svg_id
        
        # 使用近似边界框
        bbox = cluster_el.get('bbox', {})
        if bbox.get('width', 0) > 0 or bbox.get('height', 0) > 0:
            clusters[svg_id] = {
                'type': 'cluster',
                'mermaid_id': svg_id,
                'title': title,
                'svg_id': svg_id,
                'bbox': bbox
            }
            all_elements[svg_id] = clusters[svg_id]
    
    # 3. 构建层次结构
    for child_id, child in all_elements.items():
        potential_parent_id = None
        min_area = float('inf')
        
        for parent_id, parent in clusters.items():
            if child_id == parent_id:
                continue
                
            if (child['bbox']['left'] >= parent['bbox']['left'] and
                child['bbox']['right'] <= parent['bbox']['right'] and
                child['bbox']['top'] >= parent['bbox']['top'] and
                child['bbox']['bottom'] <= parent['bbox']['bottom']):
                
                area = parent['bbox']['width'] * parent['bbox']['height']
                if area < min_area:
                    min_area = area
                    potential_parent_id = parent_id
        
        if potential_parent_id:
            parent_map[child_id] = potential_parent_id
    
    # 4. 处理边和标签
    edges = []
    edge_labels = {}
    
    for label_el in svg_element.select('g.edgeLabel'):
        text = label_el.get_text(strip=True)
        if text:
            edge_labels[label_el.get('id')] = {
                'text': text,
                'x': label_el.get('x', 0),
                'y': label_el.get('y', 0)
            }
    
    for path in svg_element.select('path.flowchart-link'):
        path_id = path.get('id')
        if not path_id:
            continue
            
        # 解析路径ID获取源节点和目标节点
        id_parts = re.sub(r'^(L_|FL_)', '', path_id).split('_')
        source_node = None
        target_node = None
        
        # 尝试多种方式解析节点
        for i in range(1, len(id_parts)):
            potential_source = '_'.join(id_parts[:i])
            potential_target = '_'.join(id_parts[i:])
            
            for node in nodes.values():
                if node['mermaid_id'] == potential_source:
                    source_node = node
                if node['mermaid_id'] == potential_target:
                    target_node = node
            
            if source_node and target_node:
                break
        
        if not source_node or not target_node:
            print(f"无法确定边的源/目标: {path_id}")
            continue
        
        # 获取标签文本
        label = ""
        # 简化处理：在实际应用中需要计算路径中点位置
        # 这里使用近似方法
        closest_label = None
        min_dist = float('inf')
        
        for label_id, lbl in edge_labels.items():
            # 简化距离计算
            dist = abs(lbl['x'] - path.get('x', 0)) + abs(lbl['y'] - path.get('y', 0))
            if dist < min_dist:
                min_dist = dist
                closest_label = lbl
        
        if closest_label and min_dist < 75:
            label = closest_label['text']
        
        label_part = f'|"{label}"|' if label else ""
        edge_text = f"{source_node['mermaid_id']} -->{label_part} {target_node['mermaid_id']}"
        
        # 寻找最低共同祖先
        source_ancestors = []
        current = source_node['svg_id']
        while current in parent_map:
            source_ancestors.append(parent_map[current])
            current = parent_map[current]
        
        lca = parent_map.get(target_node['svg_id'])
        while lca and lca not in source_ancestors:
            lca = parent_map.get(lca)
        
        edges.append({'text': edge_text, 'parent_id': lca or 'root'})
    
    # 5. 生成Mermaid输出
    defined_node_mermaid_ids = set()
    for node in nodes.values():
        if node['mermaid_id'] not in defined_node_mermaid_ids:
            mermaid_code += f"{node['mermaid_id']}[\"{node['text']}\"]\n"
            defined_node_mermaid_ids.add(node['mermaid_id'])
    
    mermaid_code += '\n'
    
    # 按父级分组
    children_map: Dict[str, List] = {}
    edge_map: Dict[str, List] = {}
    
    for child_id, parent_id in parent_map.items():
        if parent_id not in children_map:
            children_map[parent_id] = []
        children_map[parent_id].append(child_id)
    
    for edge in edges:
        parent_id = edge['parent_id'] or 'root'
        if parent_id not in edge_map:
            edge_map[parent_id] = []
        edge_map[parent_id].append(edge['text'])
    
    # 添加顶层边
    for edge_text in edge_map.get('root', []):
        mermaid_code += f"{edge_text}\n"
    
    # 递归构建子图
    def build_subgraph_output(cluster_id: str):
        cluster = clusters.get(cluster_id)
        if not cluster:
            return
            
        mermaid_code += f"\nsubgraph {cluster['mermaid_id']} [\"{cluster['title']}\"]\n"
        
        child_items = children_map.get(cluster_id, [])
        
        # 添加节点
        for child_id in child_items:
            if child_id in nodes:
                mermaid_code += f"    {nodes[child_id]['mermaid_id']}\n"
        
        # 添加边
        for edge_text in edge_map.get(cluster_id, []):
            mermaid_code += f"    {edge_text}\n"
        
        # 添加嵌套子图
        for child_id in child_items:
            if child_id in clusters:
                build_subgraph_output(child_id)
        
        mermaid_code += "end\n"
    
    # 添加顶层集群
    top_level_clusters = [cid for cid in clusters if cid not in parent_map]
    for cluster_id in top_level_clusters:
        build_subgraph_output(cluster_id)
    
    if not nodes and not clusters:
        return None
        
    return f'```mermaid\n{mermaid_code.strip()}\n```'

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
        
    print("Converting state diagram...")
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
        # 根据标签类型处理
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
        
        else:
            # 处理其他元素
            content = ''.join(process_node(child) for child in node.children)
            result_md = content + "\n\n" if content.strip() else ""
    
    except Exception as e:
        print(f"处理节点错误: {node.name} - {str(e)}")
        return f"[ERROR_PROCESSING:{node.name}]"
    
    return result_md

def deepwiki2markdown(html_content: str) -> str:
    """将 HTML 内容转换为 Markdown"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 获取内容容器
    container = soup.body

    # 处理所有子节点
    markdown = ""
    for child in container.children:
        markdown += process_node(child)
    
    # 规范化空白行
    markdown = re.sub(r'\n{3,}', '\n\n', markdown.strip())
    
    return markdown
