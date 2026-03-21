import openpyxl
from openpyxl.cell import MergedCell
from openpyxl.utils import range_boundaries, get_column_letter
import io
import pandas as pd


def get_column_options(ws, tpl_workbook, col_idx, header_row_idx):
    """动态解析数据验证，获取下拉选项"""
    # 探测数据区的第一个单元格（表头下第3行，即第7行左右）
    target_cell_coord = f"{get_column_letter(col_idx)}{header_row_idx + 3}"
    options = []

    if not hasattr(ws, 'data_validations') or ws.data_validations is None:
        return options

    for dv in ws.data_validations.dataValidation:
        if target_cell_coord in dv:
            formula = dv.formula1
            if not formula: continue

            if '"' in formula or ("," in formula and "!" not in formula):
                options = formula.replace('"', '').split(',')
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
                            if val and str(val).strip() not in ["Select", "Type or select a value"]:
                                options.append(str(val).strip())
                except:
                    pass
            break
    return options


def process_mercado_listing(source_df, template_bytes, sheet_name, mapping_config, static_fills):
    in_io = io.BytesIO(template_bytes)
    # 保持完整模式加载，以保留公式和格式
    wb = openpyxl.load_workbook(in_io)
    ws = wb[sheet_name]

    # 1. 定位表头
    header_row_idx = 1
    headers = []
    for i in range(1, 10):
        row_vals = [str(ws.cell(row=i, column=j).value) for j in range(1, ws.max_column + 1)]
        if any("Title" in (v or "") for v in row_vals):
            header_row_idx = i
            headers = row_vals
            break

    col_map = {name: idx + 1 for idx, name in enumerate(headers) if name and name != 'None'}

    # 2. 安全写入函数
    def safe_write(row, col, value):
        cell = ws.cell(row=row, column=col)
        if isinstance(cell, MergedCell):
            return

            # --- 自动类型转换逻辑 ---
        if isinstance(value, str):
            # 去掉空格
            clean_val = value.strip()

            # 1. 尝试转换为整数 (如 "5" -> 5)
            if clean_val.isdigit():
                value = int(clean_val)
            else:
                # 2. 尝试转换为浮点数 (如 "5.5" -> 5.5)
                try:
                    value = float(clean_val)
                except ValueError:
                    # 3. 如果转换失败（如 "Generic"），则保持原样字符串
                    pass

        cell.value = value

    # 3. 确定起始行
    # header_row_idx (4) + 1 = 描述行 (5)
    # header_row_idx (4) + 2 = 示例行 (6)
    # header_row_idx (4) + 3 = 数据开始行 (7)
    start_row = header_row_idx + 4

    ml_title_key = next((k for k in col_map.keys() if "Title" in k), None)
    ml_img_key = next((k for k in col_map.keys() if "Photos" in k), None)
    ml_sku_key = next((k for k in col_map.keys() if "SKU" in k), None)
    char_count_col = next((k for k in col_map.keys() if "Number of characters" in k), None)

    # 4. 批量填充
    for i, row in source_df.iterrows():
        curr_row = start_row + i

        # 标题写入 (会自动触发 Excel 表格第二列的 LEN 公式)
        if ml_title_key:
            safe_write(curr_row, col_map[ml_title_key], row[mapping_config['title_col']])

        if ml_img_key:
            safe_write(curr_row, col_map[ml_img_key], row[mapping_config['img_col']])

        if ml_sku_key:
            sku_val = row.get('SKU') or row.get('sku') or f"ML-{i + 1}"
            safe_write(curr_row, col_map[ml_sku_key], sku_val)

        # 静态参数写入（自动避开字数统计列）
        for header, val in static_fills.items():
            if header == char_count_col: continue
            if header in col_map:
                safe_write(curr_row, col_map[header], val)

    out_io = io.BytesIO()
    wb.save(out_io)
    return out_io.getvalue()