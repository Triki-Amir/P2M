import uuid
import logging
import json
from ingestion_service.database import SessionLocal
from ingestion_service.models import Tenant, Document, Chunk, DocumentCompliance
from compliance_service.app.extractor import run_compliance_for_document

logging.basicConfig(level=logging.INFO)

def test_compliance():
    db = SessionLocal()
    try:
        # 1. Créer un locataire (Tenant) fictif pour le test
        tenant = db.query(Tenant).filter_by(name="Test Tenant").first()
        if not tenant:
            tenant = Tenant(
                name="Test Tenant",
                email="test@tenant.com",
                tenant_metadata={
                    "geo_zone": "Tunisie, ariana ",
                    "guarantee": "5 ans",
                    "staff_count": {
                        "others": 10,
                        "engineers": 15,
                        "technicians": 50
                    },
                    "annual_revenue": 100.0,
                    "certifications": [
                        "ISO 9001"
                    ]
                }
            )
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
        
        print(f"[*] Utilisation du Tenant : {tenant.id} - {tenant.name}")

        # 2. Récupérer un document existant dans la base de données
        # (on suppose qu'un document est déjà passé par la pipeline NLP/OCR)
        doc = db.query(Document).first()
        if not doc:
            print("[!] Aucun document trouvé dans la base de données.")
            print("Veuillez d'abord uploader ou traiter un document via la pipeline.")
            return

        print(f"[*] Utilisation du Document : {doc.id} - {doc.filename}")
        
        # Vérifier si des chunks existent pour ce document
        chunks_count = db.query(Chunk).filter_by(document_id=doc.id).count()
        print(f"[*] {chunks_count} chunks trouvés pour ce document.")
        if chunks_count == 0:
            print("[!] Le document n'a pas de chunks associés. Impossible de tester la conformité.")
            return

        # 3. Lancer la logique de compliance
        print("[*] Lancement de l'extraction LLM et de la comparaison de conformité...")
        run_compliance_for_document(str(doc.id), str(tenant.id))

        # 4. Afficher le résultat stocké dans la base
        compliance_result = db.query(DocumentCompliance).filter_by(document_id=doc.id).first()
        if compliance_result:
            print("\n" + "="*40)
            print(" RESULTAT DE LA CONFORMITE")
            print("="*40)
            print(f"-> Est Éligible (Compliant) : {compliance_result.is_compliant}\n")
            
            print("-> Critères Extraits par l'LLM :")
            print(json.dumps(compliance_result.extracted_criteria, indent=2, ensure_ascii=False))
            
            print("\n-> Détails de la Comparaison :")
            print(json.dumps(compliance_result.compliance_details, indent=2, ensure_ascii=False))
            print("="*40)
        else:
            print("[!] Échec: Aucun enregistrement DocumentCompliance n'a été créé.")
            
    finally:
        db.close()

if __name__ == "__main__":
    test_compliance()
