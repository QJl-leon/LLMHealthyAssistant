from __future__ import annotations
import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exam_report_multipage.pdf')
FONT = 'STSong-Light'
COLS = [50.0, 130.0, 260.0, 330.0, 395.0, 495.0, 545.0]
ROW_H = 20.0
HEADER = ['项目类别', '检查项目', '结果', '单位', '参考区间', '提示']

def _setup_font():
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(FONT))
    except Exception:
        pass
    return FONT

def _text(c, x, y, s, size=10.0):
    c.setFont(FONT, size)
    c.drawString(x, y, s)

def _cell(c, y_top: float, r0: int, c0: int, r1: int, c1: int, text: str=''):
    x0, x1 = (COLS[c0], COLS[c1 + 1])
    y1 = y_top - r0 * ROW_H
    y0 = y_top - (r1 + 1) * ROW_H
    c.setLineWidth(0.7)
    c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0)
    if text:
        _text(c, x0 + 4, y0 + (y1 - y0) / 2 - 3.2, text)

def _row_cells(c, y_top: float, r: int, cells: list[str], skip_col0: int=-1):
    for ci, txt in enumerate(cells):
        if ci == skip_col0:
            continue
        _cell(c, y_top, r, ci, r, ci, txt)

def _table_with_merged_category(c, y_top: float):
    for ci, h in enumerate(HEADER):
        _cell(c, y_top, 0, ci, 0, ci, h)
    _cell(c, y_top, 1, 0, 3, 0, '血常规')
    _row_cells(c, y_top, 1, ['', '白细胞计数', '6.2', '10^9/L', '3.5-9.5', ''], skip_col0=0)
    _row_cells(c, y_top, 2, ['', '红细胞计数', '4.8', '10^12/L', '4.3-5.8', ''], skip_col0=0)
    _row_cells(c, y_top, 3, ['', '血红蛋白', '148', 'g/L', '130-175', ''], skip_col0=0)
    _cell(c, y_top, 4, 0, 5, 0, '肝功能')
    _row_cells(c, y_top, 4, ['', '丙氨酸氨基转移酶', '28', 'U/L', '9-50', ''], skip_col0=0)
    _row_cells(c, y_top, 5, ['', '天冬氨酸氨基转移酶', '24', 'U/L', '15-40', ''], skip_col0=0)
    _row_cells(c, y_top, 6, ['血糖', '空腹血糖', '5.4', 'mmol/L', '3.9-6.1', ''])
    _row_cells(c, y_top, 7, ['血糖', '糖化血红蛋白', '', '', '', ''])
    _cell(c, y_top, 8, 0, 8, 5, '备注：本报告仅对本次送检样本负责，如有疑问请咨询检验科。')

def _plain_table(c, y_top: float, rows: list[list[str]], with_header: bool=True):
    r = 0
    if with_header:
        for ci, h in enumerate(HEADER):
            _cell(c, y_top, 0, ci, 0, ci, h)
        r = 1
    for cells in rows:
        for ci, txt in enumerate(cells):
            _cell(c, y_top, r, ci, r, ci, txt)
        r += 1
    return r

def build():
    _setup_font()
    c = canvas.Canvas(OUT, pagesize=A4)
    W, H = A4
    _text(c, 50, H - 55, '健康体检报告', 16)
    _text(c, 50, H - 80, '体检机构：康泰市第一人民医院', 10)
    _text(c, 50, H - 98, '体检日期：2026-09-15', 10)
    _text(c, 300, H - 98, '报告编号：TJ20260915001', 10)
    _text(c, 50, H - 116, '姓名：张三    性别：男    年龄：45', 10)
    _text(c, 50, H - 143, '一、血常规与生化检验', 11)
    _table_with_merged_category(c, H - 163)
    c.showPage()
    _text(c, 50, H - 55, '（续上页：血常规与生化检验）', 11)
    _plain_table(c, H - 80, [['血糖', '', '6.2', '%', '4.0-6.0', '↑']], with_header=False)
    _text(c, 50, H - 175, '二、尿常规', 11)
    _plain_table(c, H - 195, [['尿常规', '尿蛋白', '阴性', '', '阴性', ''], ['', '尿糖', '阴性', '', '阴性', ''], ['', '尿隐血', '阴性', '', '阴性', ''], ['', '尿比重', '1.020', '', '1.003-1.030', '']])
    c.showPage()
    _text(c, 50, H - 55, '（续上页：尿常规，本页不重复表头）', 11)
    _plain_table(c, H - 80, [['', '尿白细胞', '阴性', '', '阴性', ''], ['', '尿胆原', '阴性', '', '阴性', ''], ['', '尿酸碱度', '6.0', '', '4.5-8.0', '']], with_header=False)
    _text(c, 50, H - 175, '三、影像与心电', 11)
    _plain_table(c, H - 195, [['影像', '肝脏超声', '正常', '', '未见异常', ''], ['', '胆囊超声', '正常', '', '未见异常', ''], ['', '心电图', '正常', '', '未见异常', '']])
    c.showPage()
    _text(c, 50, H - 55, '（续上页：影像与心电，本页重复表头）', 11)
    _plain_table(c, H - 80, [['', '胸部正位片', '正常', '', '未见异常', ''], ['', '骨密度', '-1.2', 'SD', '-1.0-1.0', '']])
    _text(c, 50, H - 195, '四、体检结论', 11)
    _text(c, 50, H - 215, '1. 血脂偏高，建议低脂饮食并复查血脂四项。', 10)
    _text(c, 50, H - 233, '2. 其余检验项目未见明显异常。', 10)
    _text(c, 50, H - 260, '体检医师：李医生', 10)
    c.save()
    return OUT
OUT_BORDERLESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exam_report_borderless.pdf')

def build_borderless():
    _setup_font()
    c = canvas.Canvas(OUT_BORDERLESS, pagesize=A4)
    W, H = A4
    _text(c, 50, H - 55, '健康体检报告（无表格线版）', 16)
    _text(c, 50, H - 80, '体检机构：康泰市第一人民医院', 10)
    _text(c, 50, H - 98, '体检日期：2026-09-15', 10)
    rows = [('项目类别', '检查项目', '结果', '单位', '参考区间', '提示'), ('血常规', '白细胞计数', '6.2', '10^9/L', '3.5-9.5', ''), ('', '红细胞计数', '4.8', '10^12/L', '4.3-5.8', ''), ('肝功能', '丙氨酸氨基转移酶', '28', 'U/L', '9-50', ''), ('', '天冬氨酸氨基转移酶', '24', 'U/L', '15-40', '')]
    y = H - 125
    for cells in rows:
        for ci, txt in enumerate(cells):
            if txt:
                _text(c, COLS[ci], y, txt)
        y -= ROW_H
    _text(c, COLS[0], y, '备注：本报告仅对本次送检样本负责，如有疑问请咨询检验科。', 9)
    y -= ROW_H
    for ci, txt in enumerate(['血糖', '糖化血红蛋白', '', '', '', '']):
        if txt:
            _text(c, COLS[ci], y, txt)
    y -= ROW_H
    for ci, txt in enumerate(['', '', '6.2', '%', '4.0-6.0', '↑']):
        if txt:
            _text(c, COLS[ci], y, txt)
    y -= ROW_H * 1.5
    _text(c, COLS[0], y, '二、尿常规', 11)
    y -= ROW_H
    for cells in [('尿常规', '尿蛋白', '阴性', '', '阴性', ''), ('', '尿糖', '阴性', '', '阴性', '')]:
        for ci, txt in enumerate(cells):
            if txt:
                _text(c, COLS[ci], y, txt)
        y -= ROW_H
    c.save()
    return OUT_BORDERLESS
OUT_IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'report_images')

def build_report_images():
    import pypdfium2 as pdfium
    os.makedirs(OUT_IMAGES_DIR, exist_ok=True)
    made: list[str] = []
    for pdf_path, tag in ((OUT, 'multipage'), (OUT_BORDERLESS, 'borderless')):
        doc = pdfium.PdfDocument(pdf_path)
        for i in range(len(doc)):
            img = doc[i].render(scale=1.5).to_pil()
            out = os.path.join(OUT_IMAGES_DIR, f'exam_{tag}_p{i + 1}.png')
            img.save(out)
            made.append(out)
        doc.close()
    return made
if __name__ == '__main__':
    print(f'已生成测试夹具: {build()}')
    print(f'已生成测试夹具: {build_borderless()}')
    for p in build_report_images():
        print(f'已生成报告图片: {p}')
