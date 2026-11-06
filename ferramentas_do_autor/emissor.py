"""Ferramenta privada de operação do autor. Não distribuir a chave privada.

init-author: primeira chave e licença local de desenvolvimento, sem cartório.
issue: exige documento PDF final e declaração explícita de conferência real.
"""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from guardian.config import Settings
from guardian.licensing import AUTHOR, CAPABILITIES, LicenseGuard, device_fingerprint, installation_id, sign_payload
from guardian.security import protect_file, read_protected


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['init-author','issue'])
    parser.add_argument('--installation')
    parser.add_argument('--tenant')
    parser.add_argument('--device-fingerprint')
    parser.add_argument('--document',type=Path)
    parser.add_argument('--verification-reference')
    parser.add_argument('--authorization-method',choices=['govbr','notary'],default='govbr')
    parser.add_argument('--attest-document-checked',action='store_true')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--days',type=int,default=365)
    args=parser.parse_args()
    settings=Settings.load()
    private_path=settings.data/'issuer'/'private.key'
    public_path=Path(__file__).resolve().parents[1]/'lumen10_guardian_ia'/'guardian'/'issuer-public.pem'
    if args.command=='init-author':
        if private_path.exists() or public_path.exists():
            raise SystemExit('Emissor já existe. Não substituir a raiz de confiança existente.')
        key=Ed25519PrivateKey.generate()
        private_path.parent.mkdir(parents=True,exist_ok=True)
        if __import__('os').name!='nt':private_path.parent.chmod(0o700)
        raw=key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())
        protect_file(private_path,base64.b64encode(raw).decode())
        public_path.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        installation=installation_id(settings)
        fingerprint=device_fingerprint()
        authorization={"method":"author-local-development","notarized":False,"basis":"Implementação local solicitada pelo autor; não constitui licença para terceiros"}
        edition,tenants='author-development',['*']
        output=settings.data/'license.json'
    else:
        if not all([args.installation,args.tenant,args.device_fingerprint,args.document,args.verification_reference,args.output,args.attest_document_checked]):
            parser.error('Exige instalação, fingerprint, tenant, PDF final, referência de conferência, --output e --attest-document-checked após conferência real')
        document=args.document.read_bytes()
        if not document.startswith(b'%PDF-'):
            raise SystemExit('Documento final deve ser PDF')
        key=Ed25519PrivateKey.from_private_bytes(base64.b64decode(read_protected(private_path)))
        installation=args.installation
        fingerprint=args.device_fingerprint
        authorization={"method":"govbr-document-manually-verified" if args.authorization_method=='govbr' else "notarized-document-manually-verified","verification_reference":args.verification_reference,
                       "document_sha256":hashlib.sha256(document).hexdigest(),"verified_by":AUTHOR,
                       "automated_notary_validation":False}
        edition,tenants,output='commercial',[args.tenant],args.output
    if not 1<=args.days<=366:
        parser.error('Validade deve ser de 1 a 366 dias')
    payload={"product":"lumen10-guardian","license_id":str(uuid.uuid4()),"edition":edition,"issuer":AUTHOR,
             "installation_id":installation,"device_fingerprint":fingerprint,"tenant_ids":tenants,"capabilities":sorted(CAPABILITIES),
             "issued_at":datetime.now(timezone.utc).isoformat(),
             "expires_at":(datetime.now(timezone.utc)+timedelta(days=args.days)).isoformat(),"authorization":authorization}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(sign_payload(key,payload),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Licença assinada criada. Tipo: '+edition+'. Não é certificado notarial ou ICP-Brasil.')
    if edition=='author-development':print(json.dumps(LicenseGuard(settings).status(),ensure_ascii=False))


if __name__=='__main__':main()
