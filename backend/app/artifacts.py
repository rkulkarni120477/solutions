import base64
import io
import json
import re
import zipfile
from html import escape
from PIL import Image
import httpx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from pptx import Presentation
from pptx.util import Inches as SlideInches, Pt as SlidePt
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as PDFImage
from .config import settings
from .schemas import Solution, calculate
from .db import Artifact
from .storage import storage


MIMES = {'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'pdf': 'application/pdf', 'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'zip': 'application/zip', 'svg': 'image/svg+xml', 'png': 'image/png', 'jpg': 'image/jpeg', 'mmd': 'text/plain'}


def plan_artifacts(db, version):
    outputs = version.preferences.get('outputs', [])
    kinds = []
    if 'solution' in outputs:
        kinds += ['docx', 'pdf']
    if 'estimates' in outputs:
        kinds += ['xlsx']
    if 'presentation' in outputs:
        kinds += ['pptx']
    solution = Solution.model_validate(version.response)
    for i, _ in enumerate(solution.diagrams):
        kinds += [f'diagram:{i}:{ext}' for ext in ['mmd', 'svg', 'png', 'jpg']]
    if kinds:
        kinds += ['zip']
    result = []
    for kind in kinds:
        parts = kind.split(':')
        name = f'architecture-{int(parts[1])+1}.{parts[2]}' if len(parts) == 3 else f'solution-v{version.number}.{kind}'
        a = Artifact(project_id=version.project_id, version_id=version.id, kind=kind, filename=name)
        db.add(a)
        result.append(a)
    db.commit()
    return result


def render_diagram(source):
    if len(source) > 20000 or not re.match(r'^\s*(flowchart|graph|sequenceDiagram)\b', source):
        raise ValueError('Only flowchart, graph and sequenceDiagram syntax is supported by the controlled renderer.')
    if re.search(r'%%\{|<|>|\bclick\b|https?:|javascript:|data:|@\{|image:|href|style\s+.*url', source, re.I):
        # Mermaid arrows contain >; allow only arrow token characters there.
        cleaned = re.sub(r'[-=.]>{1,2}|--[xo]|<<[-=.]|[-=.]>>', '', source)
        if re.search(r'%%\{|[<>]|\bclick\b|https?:|javascript:|data:|@\{|image:|href|url\s*\(', cleaned, re.I):
            raise ValueError('Diagram contains unsafe markup, links or directives. Use plain text labels.')
    response = httpx.post(settings.renderer_url + '/render', headers={'Authorization': f'Bearer {settings.renderer_secret}'}, json={'source': source}, timeout=45)
    if response.status_code != 200:
        raise ValueError('Diagram rendering failed. Edit the Mermaid source and retry; verify the renderer is reachable.')
    return {key: base64.b64decode(value) for key, value in response.json().items()}


def text_blocks(s):
    yield 'Executive summary', s.summary
    for section in s.sections:
        yield section.title + f' [{section.classification}]', section.content + ('\nSources: ' + ', '.join(section.sources) if section.sources else '')
    yield 'Assumptions', '\n'.join(s.assumptions)
    yield 'Open questions', '\n'.join(s.questions)
    yield 'Delivery plan', '\n\n'.join(f'{p.name} — {p.duration}\n' + '\n'.join(p.activities) + '\nDependencies: ' + p.dependencies for p in s.phases)
    yield 'Estimate basis', f'Unit: {s.effort_unit}. Currency: {s.currency}. Contingency: {s.contingency_percent}%. Staffing: {s.staffing_fte} FTE.\n{s.duration_note}\nOperating cost: {s.operating_cost_note}\nExclusions: ' + '; '.join(s.exclusions)
    yield 'Calculated estimate totals', json.dumps(calculate(s), indent=2)


def create_document(kind, solution, provider, diagrams=None):
    s = solution
    buffer = io.BytesIO()
    label = 'DEMO — illustrative template, not a live LLM response' if provider == 'demo' else f'Generated with {provider}; architect review required'
    if kind == 'docx':
        doc = Document()
        doc.core_properties.title = s.title
        style = doc.styles['Normal']
        style.font.name = 'Calibri'
        style.font.size = Pt(10)
        doc.add_heading(s.title, 0)
        doc.add_paragraph(label)
        for heading, text in text_blocks(s):
            doc.add_heading(heading, level=1)
            for paragraph in text.split('\n\n'):
                doc.add_paragraph(paragraph)
        for title, png in diagrams or []:
            doc.add_heading(title, 1)
            doc.add_picture(io.BytesIO(png), width=Inches(6))
        if s.estimates:
            table = doc.add_table(rows=1, cols=5)
            table.style = 'Light Shading Accent 1'
            for cell, value in zip(table.rows[0].cells, ['Activity', 'Role', 'Low', 'Expected', 'High']):
                cell.text = value
            for row in s.estimates:
                for cell, value in zip(table.add_row().cells, [row.activity, row.role, row.low, row.expected, row.high]):
                    cell.text = str(value)
        doc.sections[0].footer.paragraphs[0].text = 'Solution Architect Workspace • Review before implementation'
        doc.save(buffer)
    elif kind == 'pdf':
        styles = getSampleStyleSheet()
        styles['Title'].textColor = colors.HexColor('#152b4a')
        story = [Paragraph(escape(s.title), styles['Title']), Paragraph(escape(label), styles['Normal']), Spacer(1, 18)]
        for heading, text in text_blocks(s):
            story.append(Paragraph(escape(heading), styles['Heading2']))
            for p in text.split('\n'):
                if p:
                    story.append(Paragraph(escape(p), styles['BodyText']))
            story.append(Spacer(1, 10))
        for row in s.estimates:
            story.append(Paragraph(escape(f'{row.activity} / {row.role}: {row.low} / {row.expected} / {row.high} person-days'), styles['BodyText']))
        for title, png in diagrams or []:
            img = Image.open(io.BytesIO(png))
            w = 470
            h = min(500, w * img.height / img.width)
            story += [Paragraph(escape(title), styles['Heading2']), PDFImage(io.BytesIO(png), width=w, height=h, kind='proportional')]
        SimpleDocTemplate(buffer, pagesize=A4, title=s.title, author='Solution Architect Workspace').build(story)
    elif kind == 'xlsx':
        wb = Workbook()
        ws = wb.active
        ws.title = 'Effort estimate'
        ws.append([label])
        ws.append(['Currency', s.currency, 'Effort unit', 'person-days', 'Contingency', s.contingency_percent / 100])
        ws.append(['Activity', 'Role', 'Low', 'Expected', 'High', 'Rate / day', 'Expected cost', 'Dependency', 'Confidence'])
        def safe(value):
            return "'" + value if isinstance(value, str) and value.startswith(('=', '+', '-', '@')) else value
        for i, r in enumerate(s.estimates, 4):
            ws.append([safe(r.activity), safe(r.role), r.low, r.expected, r.high, r.rate, f'=IF(F{i}="","",D{i}*F{i})', safe(r.dependency), r.confidence])
        end = 3 + len(s.estimates)
        total = end + 1
        ws.cell(total, 1, 'TOTAL')
        for col in ['C', 'D', 'E']:
            ws[f'{col}{total}'] = f'=SUM({col}4:{col}{max(4,end)})' if s.estimates else 0
        ws[f'G{total}'] = f'=IF(COUNT(F4:F{end})={len(s.estimates)},SUM(G4:G{end}),"Rates required")' if s.estimates else 'No estimate requested'
        ws.cell(total + 1, 1, 'WITH CONTINGENCY')
        for col in ['C', 'D', 'E']:
            ws[f'{col}{total+1}'] = f'={col}{total}*(1+$F$2)'
        ws[f'G{total+1}'] = f'=IF(ISNUMBER(G{total}),G{total}*(1+$F$2),"Rates required")'
        ws.freeze_panes = 'C4'
        ws.auto_filter.ref = f'A3:I{max(3,end)}'
        for row in [1, 3, total, total + 1]:
            for cell in ws[row]:
                cell.fill = PatternFill('solid', fgColor='173554')
                cell.font = Font(color='FFFFFF', bold=True)
        for col, width in {'A':42,'B':28,'C':14,'D':14,'E':14,'F':18,'G':22,'H':45,'I':15}.items():
            ws.column_dimensions[col].width = width
        basis = wb.create_sheet('Basis and totals')
        for heading, value in [('Status',label), ('Duration',s.duration_note), ('Operating cost',s.operating_cost_note), ('Exclusions','; '.join(s.exclusions)), ('Calculated server totals',json.dumps(calculate(s)))]:
            basis.append([heading, safe(value)])
        basis.column_dimensions['A'].width = 28
        basis.column_dimensions['B'].width = 100
        for row in basis:
            row[1].alignment = Alignment(wrap_text=True, vertical='top')
            basis.row_dimensions[row[0].row].height = 60
        wb.save(buffer)
    elif kind == 'pptx':
        prs = Presentation()
        prs.slide_width = SlideInches(13.333)
        prs.slide_height = SlideInches(7.5)
        def slide(title, body):
            page = prs.slides.add_slide(prs.slide_layouts[6])
            box = page.shapes.add_textbox(SlideInches(.65),SlideInches(.5),SlideInches(12),SlideInches(1))
            p = box.text_frame.paragraphs[0]
            p.text = title[:110]
            p.font.size = SlidePt(28)
            box = page.shapes.add_textbox(SlideInches(.7),SlideInches(1.6),SlideInches(11.9),SlideInches(5.2))
            box.text_frame.word_wrap = True
            for i, line in enumerate(body.split('\n')):
                p = box.text_frame.paragraphs[0] if i == 0 else box.text_frame.add_paragraph()
                p.text = line
                p.font.size = SlidePt(17)
            return page
        slide(s.title, label)
        for heading, text in text_blocks(s):
            # Bound content per slide; preserve full text through continuation slides.
            parts = [text[i:i+850] for i in range(0, len(text), 850)] or ['']
            for i, part in enumerate(parts):
                slide(heading + (f' ({i+1}/{len(parts)})' if len(parts)>1 else ''), part)
        for title, png in diagrams or []:
            page = slide(title, '')
            img = Image.open(io.BytesIO(png))
            width = min(11.8, 4.8 * img.width / img.height)
            page.shapes.add_picture(io.BytesIO(png), SlideInches((13.333-width)/2), SlideInches(1.7), width=SlideInches(width))
        prs.save(buffer)
    else:
        raise ValueError('Unknown artifact format')
    return buffer.getvalue()


def build_artifact(db, artifact, version, cache):
    s = Solution.model_validate(version.response)
    if artifact.kind.startswith('diagram:'):
        _, index, ext = artifact.kind.split(':')
        source = s.diagrams[int(index)].source
        if ext == 'mmd':
            return source.encode()
        if source not in cache:
            cache[source] = render_diagram(source)
        return cache[source][ext]
    siblings = db.query(Artifact).filter_by(version_id=version.id).all()
    if artifact.kind == 'zip':
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
            manifest = []
            for a in siblings:
                if a.id == artifact.id:
                    continue
                manifest.append({'filename': a.filename, 'status': a.status, 'error': a.error})
                if a.status == 'Completed' and a.key:
                    z.writestr(a.filename, storage.get(a.key))
            z.writestr('manifest.json', json.dumps({'project_id':version.project_id, 'version':version.number,'provider':version.provider,'artifacts':manifest}, indent=2))
        return buffer.getvalue()
    diagrams = []
    for a in siblings:
        if a.status == 'Completed' and a.kind.endswith(':png') and a.key:
            idx = int(a.kind.split(':')[1])
            diagrams.append((s.diagrams[idx].title, storage.get(a.key)))
    return create_document(artifact.kind, s, version.provider, diagrams)
