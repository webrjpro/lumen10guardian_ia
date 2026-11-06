"""Gera minuta privada preenchível. Não assina nem verifica identidade."""
from pathlib import Path
import re

from pypdf import PdfReader
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph

from guardian.config import Settings
from guardian.licensing import AUTHOR

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'output'/'pdf'/'Termo_Autorizacao_Guardian.pdf'
NAVY=colors.HexColor('#142b3d')
GREEN=colors.HexColor('#17876d')
MUTED=colors.HexColor('#596b79')
W,H=A4
X=48
WIDTH=W-96
STYLE=ParagraphStyle('Body',fontName='Helvetica',fontSize=9.3,leading=14,textColor=NAVY)
fields=[]


def paragraph(c,text,y,width=WIDTH,size=9.3):
    style=ParagraphStyle('P',parent=STYLE,fontSize=size,leading=size*1.5)
    item=Paragraph(text,style)
    _,height=item.wrap(width,500)
    item.drawOn(c,X,y-height)
    return y-height-12


def header(c,page):
    c.setFillColor(NAVY)
    c.rect(0,H-94,W,94,fill=1,stroke=0)
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold',17)
    c.drawString(X,H-42,'LUMEN10 GUARDIAN AI')
    c.setFont('Helvetica',9)
    c.drawString(X,H-63,'TERMO PARTICULAR DE AUTORIZAÇÃO DE USO E OPERAÇÃO')
    c.setFillColor(GREEN)
    c.rect(X,H-112,108,17,fill=1,stroke=0)
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold',8)
    c.drawString(X+8,H-106,'MINUTA NÃO ASSINADA')
    c.setFillColor(MUTED)
    c.setFont('Helvetica',7)
    c.drawRightString(W-X,31,f'Guardian AI | Documento privado | Página {page} de 2')
    c.drawString(X,31,'Preencher, revisar e assinar o arquivo final. Sem certificação emitida pelo software.')


def section(c,title,y):
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold',10)
    c.drawString(X,y,title)
    c.setStrokeColor(colors.HexColor('#cfd9df'))
    c.line(X,y-7,W-X,y-7)
    return y-23


def field(c,name,label,y,width=WIDTH,value='',height=24):
    c.setFillColor(MUTED)
    c.setFont('Helvetica',8)
    c.drawString(X,y,label)
    kwargs={'name':name,'tooltip':label,'x':X,'y':y-height-7,'width':width,'height':height,
            'value':value,'fontName':'Helvetica','fontSize':9,'borderWidth':0.6,
            'borderColor':colors.HexColor('#aabcc8'),'fillColor':colors.HexColor('#f6f9fa'),
            'textColor':NAVY,'forceBorder':True}
    if height>30:kwargs['fieldFlags']='multiline'
    c.acroForm.textfield(**kwargs)
    fields.append((name,value))
    return y-height-25


def main():
    private=Settings.load().data/'legal'/'DADOS_DECLARADOS_DO_AUTOR.md'
    data=private.read_text(encoding='utf-8-sig')
    cpf=re.search(r'CPF informado pelo titular:\s*([^\r\n]+)',data)[1]
    filiation=re.search(r'Filiação informada:\s*([^\r\n]+)',data)[1]
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    c=canvas.Canvas(str(OUTPUT),pagesize=A4)
    c.setTitle('Minuta de autorização de uso - Lumen10 Guardian AI')
    c.setAuthor(AUTHOR)
    header(c,1)
    y=H-137
    y=paragraph(c,'<b>Finalidade:</b> individualizar o titular, o usuário autorizado, o projeto e as operações permitidas. Este arquivo é uma minuta para revisão e preenchimento; não comprova identidade, titularidade, assinatura ou reconhecimento de firma.',y)
    y=section(c,'1. DESENVOLVEDOR / TITULAR DECLARADO',y)
    y=paragraph(c,f'<b>{AUTHOR}</b><br/>CPF informado: {cpf}<br/>Filiação informada: {filiation}',y)
    y=section(c,'2. USUÁRIO / ORGANIZAÇÃO AUTORIZADA',y)
    y=field(c,'licensee_name','Nome completo ou razão social',y)
    y=field(c,'licensee_document','CPF/CNPJ e representante autorizado, quando aplicável',y)
    y=field(c,'licensee_contact','Contato administrativo responsável',y)
    y=section(c,'3. PROJETO E ESCOPO AUTORIZADO',y-2)
    y=field(c,'project','Projeto, repositório e ambientes abrangidos',y)
    y=field(c,'installation_id','ID da instalação / tenant / identificação técnica',y)
    y=field(c,'scope','Operações autorizadas e restrições',y,value='Monitoramento e diagnóstico. Publicação em produção: NÃO AUTORIZADA neste termo.',height=51)
    y=field(c,'validity','Início e fim da autorização / número de licença ou contrato',y)
    if y<55:raise RuntimeError('Layout excedeu página 1')
    c.showPage()
    header(c,2)
    y=H-139
    y=section(c,'4. CONDIÇÕES DE USO E CONTROLE OPERACIONAL',y)
    clauses=[
        '<b>4.1. Limites.</b> O uso fica restrito às pessoas, instalações, projetos e operações definidos neste termo e na licença emitida. A posse do código não concede licença geral de exploração ou redistribuição.',
        '<b>4.2. Produção.</b> Qualquer publicação depende de autorização específica, testes aplicáveis, versão identificada, política aprovada e recuperação compatível. Este termo não habilita recursos ainda não implementados no Guardian.',
        '<b>4.3. Credenciais e dados.</b> O usuário é responsável por disponibilizar acessos legítimos e proporcionais. Logs e contextos podem conter dados pessoais; devem ser minimizados. Senhas e chaves não devem ser incluídas em prompts, repositórios ou notificações.',
        '<b>4.4. Inteligência artificial.</b> O uso do Codex depende de conta autorizada, conectividade e limites do provedor. Diagnósticos podem conter erros e não garantem ausência de incidentes, vulnerabilidades ou regressões.',
        '<b>4.5. Licenciamento.</b> A liberação comercial ocorre após conferência do documento final assinado e emissão da licença digital pelo titular. A licença técnica do Guardian não é certificado gov.br, ICP-Brasil ou cartorial.',
        '<b>4.6. Suspensão e responsabilidade.</b> Descumprimento do escopo pode motivar suspensão conforme o instrumento contratual aplicável. Preço, suporte, prazos, tratamento de dados, responsabilidades e foro devem ser definidos no contrato específico, após revisão jurídica.',
    ]
    for item in clauses:y=paragraph(c,item,y,size=9)
    y=section(c,'5. ASSINATURAS E CONFERÊNCIA',y-1)
    y=paragraph(c,'As partes admitem, para este fluxo, assinatura pelo gov.br conferida no VALIDAR/ITI ou reconhecimento em cartório conforme o procedimento escolhido. Preencha todos os campos antes de assinar e preserve o PDF final original.',y,size=9)
    y=field(c,'city_date','Local e data',y)
    for title in ('Desenvolvedor / titular declarado','Usuário ou representante autorizado'):
        c.setStrokeColor(colors.HexColor('#cfd9df'))
        c.roundRect(X,y-51,WIDTH,46,4,fill=0,stroke=1)
        c.setFillColor(NAVY)
        c.setFont('Helvetica-Bold',8)
        c.drawString(X+10,y-18,title)
        c.setFont('Helvetica',8)
        c.setFillColor(MUTED)
        c.drawString(X+10,y-35,'Espaço reservado à assinatura eletrônica real - não assinado')
        y-=64
    y=paragraph(c,'Conferência oficial da assinatura: https://validar.iti.gov.br<br/>Serviço de assinatura: https://www.gov.br/pt-br/servicos/assinatura-eletronica',y-2,size=7.5)
    if y<53:raise RuntimeError('Layout excedeu página 2')
    c.save()
    reader=PdfReader(OUTPUT)
    actual=reader.get_fields() or {}
    assert len(reader.pages)==2
    assert set(actual)=={name for name,_ in fields}
    for name,value in fields:assert str(actual[name].get('/V',''))==value
    widgets=0
    for page in reader.pages:
        for ref in page.get('/Annots',[]):
            widget=ref.get_object()
            if widget.get('/Subtype')=='/Widget':
                widgets+=1
                assert widget['/AP']['/N'].get_object().get_data()
                assert str(widget.get('/V',''))==str(actual[widget['/T']].get('/V',''))
    assert widgets==len(fields)
    print(f'PDF privado criado: {len(reader.pages)} páginas, {len(fields)} campos canônicos e aparências verificadas.')


if __name__=='__main__':main()
