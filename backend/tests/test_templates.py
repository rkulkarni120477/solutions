import io
import zipfile
import pytest
from docx import Document
from docx.shared import Inches as WordInches, Pt
from pptx import Presentation
from pptx.util import Inches
from app import artifacts, worker
from app.templates import validate_template, prepare_template
from app.artifacts import create_document
from test_workspace import sample_solution, fake_render
from test_proposals import COMPLETE


def word_template():
    doc = Document()
    doc.styles['Normal'].font.name = 'Cambria'
    doc.styles['Normal'].font.size = Pt(12)
    doc.sections[0].header.paragraphs[0].text = 'CONTOSO PRIVATE PROPOSALS'
    doc.sections[0].footer.paragraphs[0].text = 'CONTOSO CONFIDENTIAL'
    doc.sections[0].left_margin = WordInches(1.2)
    cover = doc.add_paragraph('Company cover ')
    cover.add_run('{{ti')
    cover.add_run('tle}}')
    doc.add_paragraph('{{proposal_content}}')
    doc.add_paragraph('Standard terms retained after the proposal')
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def powerpoint_template():
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(10), Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = 'SAMPLE SLIDE DO NOT KEEP'
    logo = slide.shapes.add_textbox(Inches(7.4), Inches(.15), Inches(2.2), Inches(.3))
    logo.text_frame.paragraphs[0].text = 'CONTOSO MASTER BRAND'
    from pptx.util import Pt as SlidePt
    logo.text_frame.paragraphs[0].font.size = SlidePt(10)
    logo._element.xpath('.//p:cNvPr')[0].set('id', '1000')
    prs.slide_master.shapes._spTree.insert_element_before(logo._element, 'p:extLst')
    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()


def upload(client, name, data):
    response = client.post('/api/templates', files={'file': (name, data)})
    assert response.status_code == 201, response.text
    return response.json()


def test_private_template_library_and_validation(workspace):
    alice, bob, _ = workspace
    data = word_template()
    row = upload(alice, 'brand.docx', data)
    assert alice.get('/api/templates').json()[0]['id'] == row['id']
    assert bob.get('/api/templates').json() == []
    assert bob.get(f"/api/templates/{row['id']}/file").status_code == 404
    assert bob.delete(f"/api/templates/{row['id']}").status_code == 404
    saved = alice.get(f"/api/templates/{row['id']}/file").content
    assert row['size'] == len(saved)
    assert 'CONTOSO' not in Document(io.BytesIO(saved)).sections[0].header.paragraphs[0].text
    assert 'Company cover' not in '\n'.join(p.text for p in Document(io.BytesIO(saved)).paragraphs)
    for name, content in [('bad.docx', b'not an office file'), ('legacy.doc', data), ('wrong.pptx', data)]:
        assert alice.post('/api/templates', files={'file': (name, content)}).status_code == 400
    pid = bob.post('/api/projects', json={'title': 'Bob project'}).json()['id']
    assert bob.post(f'/api/projects/{pid}/proposals', json={'request': COMPLETE, 'preferences': {'word_template_id': row['id']}}).status_code == 400
    assert alice.delete(f"/api/templates/{row['id']}").status_code == 200
    assert alice.get('/api/templates').json() == []
    assert alice.get(f"/api/templates/{row['id']}/file").status_code == 404


@pytest.mark.parametrize('kind,ext,factory', [('docx','dotx',word_template), ('pptx','potx',powerpoint_template)])
def test_native_template_types_normalize(kind, ext, factory):
    source = factory()
    from app.templates import TYPES
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as package, zipfile.ZipFile(out, 'w') as converted:
        for entry in package.infolist():
            data = package.read(entry)
            if entry.filename == '[Content_Types].xml':
                replacement = TYPES[kind].replace('document.main','template.main') if kind == 'docx' else TYPES[kind].replace('presentation.main','template.main')
                data = data.replace(TYPES[kind].encode(), replacement.encode())
            converted.writestr(entry.filename, data)
    actual_kind, normalized = validate_template('brand.' + ext, out.getvalue())
    assert actual_kind == kind
    assert (Document(io.BytesIO(normalized)) if kind == 'docx' else Presentation(io.BytesIO(normalized)))


def test_docx_uses_format_without_reusing_source_content():
    s = sample_solution()
    doc = Document(io.BytesIO(create_document('docx', s, 'demo', template=word_template())))
    assert doc.sections[0].header.paragraphs[0].text == ''
    assert doc.sections[0].footer.paragraphs[0].text == ''
    assert doc.styles['Normal'].font.name == 'Cambria'
    text = '\n'.join(p.text for p in doc.paragraphs)
    assert '{{proposal_content}}' not in text and '{{title}}' not in text
    assert 'Executive summary' in text
    assert 'Standard terms retained' not in text and 'Company cover' not in text
    assert all(paragraph in text for paragraph in s.summary.split('\n\n'))


def test_pptx_preserves_master_canvas_and_removes_sample_slides():
    data = create_document('pptx', sample_solution(), 'demo', template=powerpoint_template())
    prs = Presentation(io.BytesIO(data))
    assert prs.slide_width == Inches(10)
    assert len(prs.slides) > 5
    text = '\n'.join(sh.text for slide in prs.slides for sh in slide.shapes if sh.has_text_frame)
    assert 'SAMPLE SLIDE DO NOT KEEP' not in text and 'Executive summary' in text
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        assert b'CONTOSO MASTER BRAND' not in package.read('ppt/slideMasters/slideMaster1.xml')
    for slide in prs.slides:
        for shape in slide.shapes:
            assert shape.left + shape.width <= prs.slide_width + 100
            assert shape.top + shape.height <= prs.slide_height + 100


def test_dark_template_background_remains_inherited_with_readable_text():
    from pptx.dml.color import RGBColor
    source = Presentation(io.BytesIO(powerpoint_template()))
    source.slide_master.background.fill.solid()
    source.slide_master.background.fill.fore_color.rgb = RGBColor.from_string('102030')
    data = io.BytesIO()
    source.save(data)
    prs = Presentation(io.BytesIO(create_document('pptx', sample_solution(), 'demo', template=data.getvalue())))
    assert not prs.slides[0]._element.xpath('./p:cSld/p:bg')
    title = prs.slides[1].shapes[0].text_frame.paragraphs[0]
    assert str(title.font.color.rgb) == 'FFFFFF'


def test_proposal_exports_use_selections_and_archived_templates_survive_refresh(workspace, monkeypatch):
    alice, _, _ = workspace
    monkeypatch.setattr(artifacts, 'render_diagram', fake_render)
    monkeypatch.setattr(worker, 'render_diagram', fake_render)
    word = upload(alice, 'company.docx', word_template())
    ppt = upload(alice, 'company.pptx', powerpoint_template())
    pid = alice.post('/api/projects', json={'title': 'Branded proposal'}).json()['id']
    preferences = {'word_template_id': word['id'], 'powerpoint_template_id': ppt['id']}
    r = alice.post(f'/api/projects/{pid}/proposals', json={'request': COMPLETE, 'formats':['docx','pptx'], 'preferences':preferences})
    assert r.status_code == 202
    while worker.run_once():
        pass
    detail = alice.get(f'/api/projects/{pid}').json()
    assert detail['proposals'][0]['status'] == 'Pending Review', detail['proposals'][0]['error']
    version = detail['versions'][-1]
    for kind in ['docx', 'pptx']:
        artifact = next(a for a in version['artifacts'] if a['kind'] == kind)
        assert artifact['status'] == 'Completed', artifact['error']
        url = alice.post(f"/api/artifacts/{artifact['id']}/download-link").json()['url']
        data = alice.get(url).content
        if kind == 'docx':
            assert Document(io.BytesIO(data)).sections[0].header.paragraphs[0].text == ''
            assert Document(io.BytesIO(data)).styles['Normal'].font.name == 'Cambria'
        else:
            assert Presentation(io.BytesIO(data)).slide_width == Inches(10)
    for row in [word, ppt]:
        assert alice.delete('/api/templates/'+row['id']).status_code == 200
    response = alice.post(f"/api/projects/{pid}/versions/{version['id']}/refresh-files")
    assert response.status_code == 202
    while worker.run_once():
        pass
    refreshed = alice.get(f'/api/projects/{pid}').json()
    assert all(a['status']=='Completed' for a in refreshed['versions'][-1]['artifacts'])
    assert alice.post(f'/api/projects/{pid}/proposals', json={'request': COMPLETE, 'preferences':preferences}).status_code == 400


def test_template_packages_reject_macros_and_zip_bombs():
    source = word_template()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as package, zipfile.ZipFile(out,'w') as altered:
        for entry in package.infolist():
            altered.writestr(entry.filename, package.read(entry))
        altered.writestr('word/vbaProject.bin', b'macro')
    with pytest.raises(ValueError, match='macros'):
        validate_template('brand.docx', out.getvalue())


def test_template_package_entry_limit():
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as package:
        for i in range(3001):
            package.writestr(f'part{i}', b'')
    with pytest.raises(ValueError, match='size limit'):
        validate_template('brand.docx', out.getvalue())


@pytest.mark.parametrize('filename,factory', [('format.docx',word_template), ('format.pptx',powerpoint_template)])
def test_saved_formats_contain_no_source_text_notes_or_metadata(filename, factory):
    source = factory()
    if filename.endswith('docx'):
        doc = Document(io.BytesIO(source))
        doc.core_properties.title = 'PRIVATE SOURCE METADATA'
        doc.core_properties.comments = 'PRIVATE SOURCE COMMENT'
        doc.add_paragraph('PRIVATE CUSTOMER PROPOSAL')
        doc.add_comment(doc.paragraphs[0].runs, text='PRIVATE COMMENT DATA', author='PRIVATE COMMENT AUTHOR')
    else:
        doc = Presentation(io.BytesIO(source))
        doc.core_properties.title = 'PRIVATE SOURCE METADATA'
        doc.slides[0].notes_slide.notes_text_frame.text = 'PRIVATE SPEAKER NOTES'
    out = io.BytesIO()
    doc.save(out)
    kind, saved = prepare_template(filename, out.getvalue())
    with zipfile.ZipFile(io.BytesIO(saved)) as package:
        all_parts = b''.join(package.read(name) for name in package.namelist())
        for text in [b'PRIVATE SOURCE',b'PRIVATE CUSTOMER',b'PRIVATE COMMENT',b'PRIVATE SPEAKER',b'CONTOSO',b'Company cover',b'Standard terms',b'SAMPLE SLIDE']:
            assert text not in all_parts
        assert not any('notesSlide' in name or 'comments' in name or 'thumbnail' in name for name in package.namelist())
    if kind == 'docx':
        cleaned = Document(io.BytesIO(saved))
        assert all(not p.text for p in cleaned.paragraphs)
        assert cleaned.styles['Normal'].font.name == 'Cambria'
        assert cleaned.sections[0].left_margin == WordInches(1.2)
    else:
        cleaned = Presentation(io.BytesIO(saved))
        assert len(cleaned.slides) == 0
        assert cleaned.slide_width == Inches(10)
        assert len(cleaned.slide_layouts) > 0
    _, twice = prepare_template(filename, saved)
    assert twice


def test_word_extracts_direct_body_font_and_removes_images():
    from PIL import Image
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(16)
    run = paragraph.add_run('PRIVATE BODY SAMPLE FOR FONT ANALYSIS')
    run.font.name, run.font.size = 'Cambria', Pt(14)
    picture = io.BytesIO()
    Image.new('RGB', (10,10), 'red').save(picture, format='PNG')
    picture.seek(0)
    doc.add_picture(picture)
    data = io.BytesIO()
    doc.save(data)
    _, saved = prepare_template('sample.docx', data.getvalue())
    cleaned = Document(io.BytesIO(saved))
    assert cleaned.styles['Normal'].font.name == 'Cambria'
    assert cleaned.styles['Normal'].font.size == Pt(14)
    assert cleaned.styles['Normal'].paragraph_format.space_after == Pt(16)
    with zipfile.ZipFile(io.BytesIO(saved)) as package:
        assert not any('/media/' in name for name in package.namelist())


def test_powerpoint_extracts_font_and_background_from_sample_slides():
    from pptx.dml.color import RGBColor
    from pptx.util import Pt as SlidePt
    doc = Presentation(io.BytesIO(powerpoint_template()))
    slide = doc.slides[0]
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = RGBColor.from_string('112233')
    run = slide.shapes.title.text_frame.paragraphs[0].runs[0]
    run.font.name, run.font.size = 'Cambria', SlidePt(32)
    data = io.BytesIO()
    doc.save(data)
    _, saved = prepare_template('sample.pptx', data.getvalue())
    cleaned = Presentation(io.BytesIO(saved))
    layout = min(cleaned.slide_layouts,key=lambda item:len(item.placeholders))
    assert layout._element.xpath('./p:cSld/p:bg//a:srgbClr/@val') == ['112233']
    with zipfile.ZipFile(io.BytesIO(saved)) as package:
        assert b'Cambria' in package.read('ppt/theme/theme1.xml')


def test_existing_library_cleanup_does_not_modify_generated_proposals(workspace, monkeypatch):
    import runpy
    from app import db as models
    from app.storage import storage
    alice, _, sessions = workspace
    raw = word_template()
    uploaded = upload(alice, 'legacy.docx', raw)
    with sessions() as db:
        row = db.get(models.ProposalTemplate, uploaded['id'])
        storage.put(row.key, raw)  # A library entry saved before format-only uploads.
        key = row.key
    storage.put('existing-proposal.docx', raw)
    monkeypatch.setattr(models, 'Session', sessions)
    runpy.run_path('scripts/clean-template-library.py', run_name='__main__')
    cleaned = storage.get(key)
    assert all(not p.text for p in Document(io.BytesIO(cleaned)).paragraphs)
    assert storage.get('existing-proposal.docx') == raw
    with sessions() as db:
        assert db.get(models.ProposalTemplate, uploaded['id']).size == len(cleaned)


def test_legacy_download_is_clean_without_rewriting_stored_original(workspace):
    from app import db as models
    from app.storage import storage
    alice, _, sessions = workspace
    raw = word_template()
    uploaded = upload(alice, 'legacy.docx', raw)
    with sessions() as db:
        row = db.get(models.ProposalTemplate, uploaded['id'])
        storage.put(row.key, raw)
        key = row.key
    downloaded = alice.get(f"/api/templates/{uploaded['id']}/file")
    assert downloaded.status_code == 200
    assert all(not p.text for p in Document(io.BytesIO(downloaded.content)).paragraphs)
    assert storage.get(key) == raw
