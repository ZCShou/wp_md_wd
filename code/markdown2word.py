
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

def create_table_in_doc(doc, table_lines):
    """在 Word 文档中创建表格"""
    if len(table_lines) < 2:
        return
    
    # 解析表格头
    header_line = table_lines[0]
    headers = [cell.strip() for cell in header_line.split('|') if cell.strip()]
    
    if not headers:
        return
    
    # 跳过分隔符行
    data_lines = table_lines[2:] if len(table_lines) > 2 else []
    
    # 创建表格
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = 'Table Grid'
    
    # 添加表头
    hdr_cells = table.rows[0].cells
    for i, header in enumerate(headers):
        if i < len(hdr_cells):
            hdr_cells[i].text = header
            hdr_cells[i].paragraphs[0].runs[0].bold = True
    
    # 添加数据行
    for line in data_lines:
        cells_data = [cell.strip() for cell in line.split('|') if cell.strip()]
        if cells_data:
            row_cells = table.add_row().cells
            for i, cell_data in enumerate(cells_data):
                if i < len(row_cells):
                    row_cells[i].text = cell_data

def markdown2word(markdown_content, output_path):
    """将 Markdown 内容转换为格式化的 Word 文档"""
    doc = Document()
    
    # 设置文档样式
    style = doc.styles['Normal']
    font = style.font
    font.name = '微软雅黑'
    font.size = Pt(12)
    
    # 解析 Markdown 内容并转换为 Word
    lines = markdown_content.split('\n')
    current_table = []
    in_code_block = False
    code_lines = []
    
    for line in lines:
        original_line = line
        line = line.strip()
        
        if not line and not in_code_block:
            continue
            
        # 处理代码块
        if line.startswith('```'):
            if in_code_block:
                # 结束代码块
                if code_lines:
                    code_text = '\n'.join(code_lines)
                    p = doc.add_paragraph(code_text)
                    p.style = 'No Spacing'
                    font = p.runs[0].font
                    font.name = 'Consolas'
                    font.size = Pt(10)
                code_lines = []
                in_code_block = False
            else:
                # 开始代码块
                in_code_block = True
            continue
        
        if in_code_block:
            code_lines.append(original_line)
            continue
            
        # 处理表格
        if '|' in line and line.count('|') >= 2:
            current_table.append(line)
            continue
        else:
            # 如果有积累的表格，先处理表格
            if current_table:
                create_table_in_doc(doc, current_table)
                current_table = []
        
        # 处理标题
        if line.startswith('# '):
            heading = doc.add_heading(line[2:], level=1)
            heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
        elif line.startswith('## '):
            heading = doc.add_heading(line[3:], level=2)
            heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
        elif line.startswith('### '):
            heading = doc.add_heading(line[4:], level=3)
            heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
        elif line.startswith('#### '):
            heading = doc.add_heading(line[5:], level=4)
            heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
        elif line.startswith('- '):
            # 列表项
            p = doc.add_paragraph(line[2:], style='List Bullet')
        elif line.startswith('* '):
            # 列表项
            p = doc.add_paragraph(line[2:], style='List Bullet')
        elif line.startswith('**') and line.endswith('**'):
            # 粗体段落
            p = doc.add_paragraph()
            run = p.add_run(line[2:-2])
            run.bold = True
        else:
            # 普通段落
            if line:
                doc.add_paragraph(line)
    
    # 处理剩余的表格
    if current_table:
        create_table_in_doc(doc, current_table)
    
    # 保存文档
    doc.save(output_path)
