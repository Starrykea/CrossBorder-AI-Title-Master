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

    # 初始默认值，稍后会通过循环动态修正
    char_count_col_idx = 2

    # 扫描前 15 行寻找表头
    for i in range(1, 15):
        row_vals_raw = []
        for j in range(1, 100):
            val = ws.cell(row=i, column=j).value
            # 这里的清理逻辑必须和 UI 端完全一致：粉碎换行符
            val_clean = str(val or "").replace('\n', ' ').replace('\r', ' ').strip()
            row_vals_raw.append(val_clean)

        # 只要这一行包含 "Title"，就认定为表头行
        if any("Title" in v for v in row_vals_raw):
            header_row_idx = i

            # --- 关键修正：动态锁定 Number of characters 所在的列 ---
            for idx, n in enumerate(row_vals_raw):
                # 寻找字符计数列的位置
                if "Number of characters" in n:
                    char_count_col_idx = idx + 1  # 索引从1开始

                # 处理 Mexico 等重名列的计数逻辑 (保持你原有的逻辑)
                if n == "Mexico":
                    h_counts["Mexico"] = h_counts.get("Mexico", 0) + 1
                    if h_counts["Mexico"] == 1:
                        final_name = "Mexico (full)"
                    elif h_counts["Mexico"] == 2:
                        final_name = "Mexico"
                    else:
                        final_name = f"Mexico_{h_counts['Mexico']}"
                elif n == "" or n == "None":
                    final_name = ""
                else:
                    h_counts[n] = h_counts.get(n, 0) + 1
                    final_name = f"{n}_{h_counts[n]}" if h_counts[n] > 1 else n

                headers.append(final_name)
            break

    # 建立【列名】到【列索引】的映射
    col_map = {name: idx + 1 for idx, name in enumerate(headers) if name != ''}

    # --- 2. 核心逻辑：寻找第一个公式行作为 start_row ---
    if start_row is None:
        for r in range(header_row_idx + 1, 40):
            cell_val = ws.cell(row=r, column=char_count_col_idx).value
            val_str = str(cell_val or "").strip()

            # 找到第一个公式，立即锁定
            if "=LEN" in val_str.upper():
                start_row = r
                break

        # 保底逻辑
        if not start_row:
            start_row = header_row_idx + 4
    # 3. 识别功能列名（用于后续填充）
    ml_upc_key = next((k for k in col_map.keys() if "Universal product code" in k), None)
    color_key = next((k for k in col_map.keys() if "Color" in k), None)
    sku_key = next((k for k in col_map.keys() if "SKU" in k), None)

    # 4. 执行数据填充
    for i, (_, row_data) in enumerate(source_df.iterrows()):
        curr_row = start_row + i

        # 标题和图片写入
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

        # 静态字段填充 (Brand, Condition, Package 等)
        for header, val in static_fills.items():
            if header in col_map:
                # 颜色列跳过，如果需要随机颜色逻辑可在此添加
                if header == color_key:
                    continue
                safe_write(ws, curr_row, col_map[header], val)

    out_io = io.BytesIO()
    wb.save(out_io)
    return out_io.getvalue()