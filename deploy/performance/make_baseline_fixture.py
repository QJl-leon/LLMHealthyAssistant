#!/usr/bin/env python3
"""Create a deterministic PDF table and rasterize it; contains no patient data."""
import argparse
import hashlib
import json
from pathlib import Path

import pypdfium2 as pdfium


def build(out):
    out.mkdir(parents=True, exist_ok=True)
    pdf, png = out/'baseline_synthetic.pdf', out/'baseline_synthetic.png'
    commands = ['0.86 0.86 0.86 rg 0 0 595 842 re f', '0 0 0 rg', '0 0 0 RG']
    def text(x,y,value,size=12):
        escaped=value.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
        commands.append(f'BT /F1 {size} Tf {x} {y} Td ({escaped}) Tj ET')
    text(40,795,'SYNTHETIC PERFORMANCE TEST - NO PATIENT DATA',13)
    text(40,755,'Health Examination / Laboratory Report',18)
    text(40,720,'Institution: SYNTHETIC TEST CENTER (fictional)')
    text(40,695,'Date: 2026-09-15     Sample: BASELINE-001')
    rows=[
        ['Test item','Result','Unit','Reference','Flag'],
        ['Fasting glucose (GLU)','6.5','mmol/L','3.9-6.1','HIGH'],
        ['Total cholesterol (TC)','6.2','mmol/L','3.1-5.2','HIGH'],
        ['LDL cholesterol','3.7','mmol/L','0-3.4','HIGH'],
        ['Triglycerides (TG)','2.0','mmol/L','0.3-1.7','HIGH'],
        ['HDL cholesterol','1.2','mmol/L','1.0-1.9','NORMAL'],
        ['ALT','28','U/L','9-50','NORMAL'],
    ]
    columns=[35,240,300,375,470,560]
    for row,values in enumerate(rows):
        y=650-row*46
        for col,value in enumerate(values):
            commands.append(f'{columns[col]} {y-46} {columns[col+1]-columns[col]} 46 re S')
            text(columns[col]+5,y-28,value,11)
    text(40,270,'All values are fabricated. This is not a real patient record.')
    text(40,245,'For OCR, retrieval and report-generation performance testing only.',11)
    stream='\n'.join(commands).encode('ascii')
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',
             b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
             b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
             b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
             f'<< /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream']
    data=bytearray(b'%PDF-1.4\n'); offsets=[0]
    for number,obj in enumerate(objects,1):
        offsets.append(len(data));data.extend(f'{number} 0 obj\n'.encode()+obj+b'\nendobj\n')
    start=len(data);data.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:data.extend(f'{offset:010d} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    pdf.write_bytes(data)
    doc=pdfium.PdfDocument(pdf)
    page=doc[0]
    bitmap=page.render(scale=2)
    bitmap.to_pil().save(png)
    bitmap.close();page.close();doc.close()
    manifest={'fixture':'baseline_synthetic_v1','synthetic':True,'patient_data':False,
              'language':'English','metrics':len(rows)-1,'sha256':hashlib.sha256(png.read_bytes()).hexdigest(),
              'generator':'deploy/performance/make_baseline_fixture.py',
              'background_note':'Gray scan background; no application quality thresholds changed.'}
    (out/'baseline_synthetic.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    print(json.dumps(build(parser.parse_args().out),ensure_ascii=False,indent=2))
