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


def process_mercado_listing(source_df, template_bytes, sheet_name, mapping_config, static_fills, upc_list=None,
                            start_row=None):
    """执行最终的表格填充任务 (已通过动态列定位锁定起始行)"""
    in_io = io.BytesIO(template_bytes)
    wb = openpyxl.load_workbook(in_io)
    ws = wb[sheet_name]

    # 1. 寻找表头行 & 确定核心列索引
    header_row_idx = 1
    headers = []
    h_counts = {}
    char_count_col_idx = 2

    for i in range(1, 15):
        row_vals_raw = []
        for j in range(1, 100):
            val = ws.cell(row=i, column=j).value
            val_clean = str(val or "").replace('\n', ' ').replace('\r', ' ').strip()
            row_vals_raw.append(val_clean)

        if any("Title" in v for v in row_vals_raw):
            header_row_idx = i
            for idx, n in enumerate(row_vals_raw):
                if "Number of characters" in n:
                    char_count_col_idx = idx + 1

                if n == "Mexico":
                    h_counts["Mexico"] = h_counts.get("Mexico", 0) + 1
                    final_name = "Mexico (full)" if h_counts["Mexico"] == 1 else (
                        "Mexico" if h_counts["Mexico"] == 2 else f"Mexico_{h_counts['Mexico']}")
                elif n == "" or n == "None":
                    final_name = ""
                else:
                    h_counts[n] = h_counts.get(n, 0) + 1
                    final_name = f"{n}_{h_counts[n]}" if h_counts[n] > 1 else n
                headers.append(final_name)
            break

    col_map = {name: idx + 1 for idx, name in enumerate(headers) if name != ''}

    # --- 2. 核心逻辑：寻找第一个公式行作为 start_row ---
    if start_row is None:
        for r in range(header_row_idx + 1, 40):
            cell_val = ws.cell(row=r, column=char_count_col_idx).value
            val_str = str(cell_val or "").strip()
            if "=LEN" in val_str.upper():
                start_row = r
                break
        if not start_row:
            start_row = header_row_idx + 4

    # 3. 识别特殊功能列名
    ml_upc_key = next((k for k in col_map.keys() if "Universal product code" in k), None)
    color_key = next((k for k in col_map.keys() if "Color" in k), None)
    sku_key = next((k for k in col_map.keys() if "SKU" in k), None)

    # --- 颜色递增预准备 ---
    color_start_val = static_fills.get(color_key, "")
    color_prefix = ""
    color_num = None
    # 匹配 A100 这种格式：(字母部分)(数字部分)
    color_match = re.match(r"([a-zA-Z]+)([0-9]+)", str(color_start_val))
    if color_match:
        color_prefix = color_match.group(1)
        color_num = int(color_match.group(2))

    # 4. 执行数据填充
    for i, (_, row_data) in enumerate(source_df.iterrows()):
        curr_row = start_row + i

        # 标题和图片
        real_title_key = next((k for k in col_map.keys() if "Title" in k and "Number" not in k), None)
        if real_title_key:
            safe_write(ws, curr_row, col_map[real_title_key], row_data[mapping_config['title_col']])

        photo_key = next((k for k in col_map.keys() if "Photos" in k), None)
        if photo_key:
            safe_write(ws, curr_row, col_map[photo_key], row_data[mapping_config['img_col']])

        # SKU 自动生成
        if sku_key:
            safe_write(ws, curr_row, col_map[sku_key], f"ML-{int(time.time()) % 100000}-{i}")

        # UPC 填充
        if ml_upc_key and upc_list and i < len(upc_list):
            safe_write(ws, curr_row, col_map[ml_upc_key], upc_list[i])

        # 5. 字段填充 (包含颜色递增逻辑)
        for header, val in static_fills.items():
            if header in col_map:
                # --- 如果是颜色列，执行递增 ---
                if header == color_key:
                    if color_num is not None:
                        # 每一行自动 +i (例如 A100, A101...)
                        final_color = f"{color_prefix}{color_num + i}"
                    else:
                        final_color = val  # 如果不是 A100 格式，填固定值
                    safe_write(ws, curr_row, col_map[header], final_color)

                # --- 其他普通静态字段 ---
                else:
                    safe_write(ws, curr_row, col_map[header], val)

    out_io = io.BytesIO()
    wb.save(out_io)
    return out_io.getvalue()