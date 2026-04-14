import os
import json
import logging
import httpx
from typing import List, Dict, Any

from app.database import SessionLocal
from app.models import Document, Chunk, Tenant, DocumentCompliance

logger = logging.getLogger(__name__)

# Constants for Ollama (or other LLM endpoint)
LLM_URL = os.getenv("LLM_URL", "http://localhost:11434/api/generate")
# It's better to use a model that outputs json reliably like llama3 or similar
MODEL_NAME = os.getenv("COMPLIANCE_LLM_MODEL", "llama3")

WINDOW_SIZE = 5

EXTRACTION_PROMPT_TEMPLATE = """Tu es un expert en analyse de marchés publics. À partir des extraits de texte suivants, extrais les critères d'éligibilité. Si une information est absente, utilise 'null'. Réponds uniquement en JSON valide.

Texte à analyser :
{chunks_text}

Format de réponse :
{{
  "admin_criteria": {{
    "deadline": "dd-mm-aaaa",
    "zone_geo": [],
    "required_specialization": []
  }},
  "financial_criteria": {{
    "min_ca": null,
    "guarantee": null
  }},
  "technical_criteria": {{
    "certs": [],
    "experience_years": null,
    "specific_lots": []
  }}
}}
"""

CONSOLIDATION_PROMPT = """Voici plusieurs extractions JSON issues du même document. Fusionne-les en un seul JSON final, supprime les doublons et résous les contradictions. 
Réponds uniquement en JSON valide sans aucun texte additionnel. Le format doit être identique à celui des entrées.

Extractions :
{extractions_json}
"""

def call_llm(prompt: str) -> dict:
    """Sync call to local Ollama for JSON extraction."""
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json"  # specific to ollama JSON mode
    }
    
    try:
        response = httpx.post(LLM_URL, json=payload, timeout=60.0)
        response.raise_for_status()
        data = response.json()
        result_text = data.get("response", "")
        return json.loads(result_text)
    except Exception as e:
        logger.error(f"Error calling LLM or parsing JSON: {e}")
        return {}

def extract_criteria_sliding_window(texts: List[str]) -> dict:
    """Extract criteria using a sliding window approach with no memory across windows."""
    results_list = []
    
    # Process by windows of size WINDOW_SIZE
    for i in range(0, len(texts), WINDOW_SIZE):
        window = texts[i:i+WINDOW_SIZE]
        combined_text = "\n---\n".join(window)
        
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(chunks_text=combined_text)
        logger.info(f"Processing window {i // WINDOW_SIZE + 1} with {len(window)} chunks...")
        
        extracted = call_llm(prompt)
        if extracted:
            results_list.append(extracted)
    
    if not results_list:
        return {}
    
    if len(results_list) == 1:
         return results_list[0]
         
    # Option B: LLM Consolideur
    consolidation_prompt = CONSOLIDATION_PROMPT.format(
        extractions_json=json.dumps(results_list, ensure_ascii=False, indent=2)
    )
    final_merged = call_llm(consolidation_prompt)
    if not final_merged:
         logger.warning("Consolidation returned empty, falling back to first result.")
         return results_list[0]
         
    return final_merged

def compare_with_tenant(extracted: dict, tenant: Tenant) -> dict:
    """
    Compare extracted criteria against the tenant's profile.
    Returns the details of the comparison and a final boolean.
    """
    details = {
        "admin": {},
        "financial": {},
        "technical": {}
    }
    
    is_compliant = True
    
    # Example logic: if extracted has a min_ca, it shouldn't exceed tenant's max_ca or capability
    # For now, simplistic exact matches or subset checks as placeholders
    
    ex_fin = extracted.get("financial_criteria", {})
    t_fin = tenant.financial_attrs or {}
    
    ex_min_ca = ex_fin.get("min_ca")
    t_max_ca = t_fin.get("current_ca")
    
    if ex_min_ca is not None and t_max_ca is not None:
        try:
            ex_val = float(ex_min_ca)
            t_val = float(t_max_ca)
            if t_val < ex_val:
                is_compliant = False
                details["financial"]["min_ca"] = f"Failed: Tenant CA {t_val} < Required {ex_val}"
            else:
                 details["financial"]["min_ca"] = f"Passed: Tenant CA {t_val} >= Required {ex_val}"
        except ValueError:
            pass

    ex_tech = extracted.get("technical_criteria", {})
    t_tech = tenant.technical_attrs or {}
    
    required_certs = ex_tech.get("certs", [])
    if required_certs and isinstance(required_certs, list):
        tenant_certs = set(t_tech.get("certs", []))
        missing = [c for c in required_certs if c not in tenant_certs]
        if missing:
            is_compliant = False
            details["technical"]["certs"] = f"Missing certificates: {missing}"
        else:
            details["technical"]["certs"] = "Passed all certificates"

    return {
        "is_compliant": is_compliant,
        "details": details
    }

def run_compliance_for_document(doc_id: str, tenant_db_id: str) -> None:
    db = SessionLocal()
    try:
        # Load the tenant
        tenant = db.query(Tenant).filter(Tenant.id == tenant_db_id).first()
        if not tenant:
            logger.error(f"Tenant {tenant_db_id} not found.")
            return
            
        # Get DB document mapping
        doc_entry = db.query(Document).filter(Document.id == doc_id).first()
        if not doc_entry:
            logger.error(f"Document entry for id {doc_id} not found")
            return
            
        # Load the chunks
        chunks = db.query(Chunk).filter(Chunk.document_id == doc_id).order_by(Chunk.chunk_index).all()
        if not chunks:
            logger.warning(f"No chunks found for document {doc_id} in DB.")
            return
            
        texts = [c.text_original for c in chunks]
        
        # 1. & 2. & 3. Extraction with Sliding Window + LLM merge
        extracted_criteria = extract_criteria_sliding_window(texts)
        if not extracted_criteria:
            logger.error("Extraction failed or returned empty.")
            return
            
        # 4. Compare with Tenant
        comparison_results = compare_with_tenant(extracted_criteria, tenant)
        
        # 5. Save to database
        compliance_record = db.query(DocumentCompliance).filter(DocumentCompliance.document_id == doc_id).first()
        
        if not compliance_record:
            compliance_record = DocumentCompliance(
                document_id=doc_entry.id,
                tenant_id=tenant.id,
            )
            db.add(compliance_record)
            
        compliance_record.extracted_criteria = extracted_criteria
        compliance_record.is_compliant = comparison_results["is_compliant"]
        compliance_record.compliance_details = comparison_results["details"]
        
        db.commit()
        logger.info(f"Compliance check completed for document {doc_id}.")
        
    except Exception as e:
        logger.error(f"Error during compliance check: {e}")
        db.rollback()
    finally:
        db.close()
