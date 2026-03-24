import openpyxl
from openpyxl.cell import MergedCell
from openpyxl.utils import range_boundaries, get_column_letter
from openpyxl.styles import Alignment
import io
import time
import random
import re


def get_column_options(ws, tpl_workbook, col_idx, header_row_idx):
    """从 Excel 模板中动态解析下拉选项 (用于 UI 渲染)"""
    # 假设美克多的有效数据从表头下第 4 行开始，我们检查那一行的单元格是否有数据验证
    target_cell_coord = f"{get_column_letter(col_idx)}{header_row_idx + 4}"
    options = []
    header_name = str(ws.cell(row=header_row_idx, column=col_idx).value or "")

    # 1. 常见跨境电商字段保底选项
    if "Warranty type" in header_name:
        return ["No warranty", "Seller warranty", "Factory warranty"]
    if "Brand" in header_name:
        return ["generic"]
    if "weight unit" in header_name.lower():
        return ["g", "kg", "lb", "mg", "oz"]
    if any(k in header_name.lower() for k in ["length", "width", "height"]):
        if "unit" in header_name.lower():
            return ["cm", "\"", "m", "mm", "ft"]

    # 2. 从 Excel 内部的数据验证 (Data Validation) 提取列表
    if hasattr(ws, 'data_validations') and ws.data_validations:
        for dv in ws.data_validations.dataValidation:
            if target_cell_coord in dv:
                formula = dv.formula1
                if not formula: continue
                # 如果是直接写在公式里的列表 (如 "Yes,No")
                if '"' in formula or ("," in formula and "!" not in formula):
                    options = formula.replace('"', '').split(',')
                # 如果是引用其他 Sheet 的序列 (如 =Lists!$A$1:$A$10)
                elif "!" in formula:
                    try:
                        sheet_part, range_part = formula.split('!')
                        sheet_name = sheet_part.strip("='")
                        if sheet_name in tpl_workbook.sheetnames:
                            ref_ws = tpl_workbook[sheet_name]
                            clean_range = range_part.replace("$", "")
                            min_col, min_row, max_col, max_row = range_boundaries(clean_range)
                            for r in range(min_row, max_row + 1):
                                val = ref_ws.cell(row=r, column=min_col).value
                                if val: options.append(str(val).strip())
                    except:
                        pass
                break
    return list(set(options))


def safe_write(ws, row, col, value):
    """安全写入，支持数字转换与自动换行"""
    cell = ws.cell(row=row, column=col)
    if isinstance(cell, MergedCell): return
    if value is None: return

    val_str = str(value).strip()
    # 针对 Description 等长文本开启自动换行
    if "\n" in val_str:
        cell.alignment = Alignment(wrapText=True, vertical='top')

    # 尝试将纯数字字符串转为真正的数字类型，避免 Excel 警告
    if val_str.isdigit():
        cell.value = int(val_str)
    else:
        try:
            cell.value = float(val_str)
        except:
            cell.value = val_str


def process_mercado_listing(source_df, template_bytes, sheet_name, mapping_config, static_fills, upc_list=None):
    """执行最终的表格填充任务"""
    in_io = io.BytesIO(template_bytes)
    wb = openpyxl.load_workbook(in_io)
    ws = wb[sheet_name]

    # 1. 寻找表头行 (1-10行遍历)
    header_row_idx = 1
    headers = []
    for i in range(1, 11):
        row_vals = [str(ws.cell(row=i, column=j).value) for j in range(1, ws.max_column + 1)]
        if any("Title" in (v or "") for v in row_vals):
            header_row_idx = i
            headers = row_vals
            break

    # 建立【列名】到【列索引】的映射
    col_map = {name: idx + 1 for idx, name in enumerate(headers) if name and name != 'None'}

    # 2. 识别核心功能列
    ml_upc_key = next((k for k in col_map.keys() if "Universal product code" in k), None)
    color_key = next((k for k in col_map.keys() if "Color" in k), None)
    sku_key = next((k for k in col_map.keys() if "SKU" in k), None)

    # --- Color 随机保底逻辑修正 ---
    # 这里的 static_fills[color_key] 拿的是 UI 界面选的值
    json_color_val = str(static_fills.get(color_key, "")).strip()
    match = re.match(r"([a-zA-Z]+)([0-9]*)", json_color_val)

    if match and match.group(1):
        color_prefix = match.group(1)
        color_num = int(match.group(2)) if match.group(2) else 100
    else:
        # 如果 JSON 没写 Color 或格式不对，随机一个字母 + 100
        color_prefix = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        color_num = 100

    # 3. 执行填充逻辑
    start_row = header_row_idx + 4
    for i, row in source_df.iterrows():
        curr_row = start_row + i

        # A. 标题和图片
        t_idx = col_map.get(next((k for k in col_map.keys() if "Title" in k), ""))
        p_idx = col_map.get(next((k for k in col_map.keys() if "Photos" in k), ""))
        if t_idx: safe_write(ws, curr_row, t_idx, row[mapping_config['title_col']])
        if p_idx: safe_write(ws, curr_row, p_idx, row[mapping_config['img_col']])

        # B. SKU 自动生成
        if sku_key:
            safe_write(ws, curr_row, col_map[sku_key], f"ML-{int(time.time()) % 100000}-{i}")

        # C. UPC 批量填充 (独立逻辑，互不干扰)
        if ml_upc_key and upc_list and i < len(upc_list):
            safe_write(ws, curr_row, col_map[ml_upc_key], upc_list[i])

        # D. 静态属性与 Color 递增
        for header, val in static_fills.items():
            if header in col_map:
                if header == color_key:
                    # 字母前缀 + 随行递增的数字
                    safe_write(ws, curr_row, col_map[header], f"{color_prefix}{color_num + i}")
                else:
                    # 普通属性直接写入 (如 Brand, Material)
                    safe_write(ws, curr_row, col_map[header], val)

    out_io = io.BytesIO()
    wb.save(out_io)
    return out_io.getvalue()