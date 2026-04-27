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
    "deadline": "YYYY-MM-DD",
    "geo_zone": "string",
    "required_specialization": []
  }},
  "financial_criteria": {{
    "annual_revenue": null,
    "guarantee": "string"
  }},
  "technical_criteria": {{
    "certifications": [],
    "staff_count": {{
      "engineers": null,
      "technicians": null,
      "others": null
    }}
  }}
}}
"""

CONSOLIDATION_PROMPT = """Voici plusieurs extractions JSON issues du même document. Fusionne-les en un seul JSON final, supprime les doublons et résous les contradictions. 
Réponds uniquement en JSON valide sans aucun texte additionnel. Le format doit être identique à celui des entrées.

Extractions :
{extractions_json}
"""

async def call_llm(prompt: str) -> dict:
    """Async call to local Ollama for JSON extraction."""
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json"  # specific to ollama JSON mode
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(LLM_URL, json=payload, timeout=60.0)
            response.raise_for_status()
            data = response.json()
            result_text = data.get("response", "")
            return json.loads(result_text)
    except Exception as e:
        logger.error(f"Error calling LLM or parsing JSON: {e}")
        return {}

async def extract_criteria_sliding_window(texts: List[str]) -> dict:
    """Extract criteria using a sliding window approach with no memory across windows."""
    results_list = []
    
    # Process by windows of size WINDOW_SIZE
    for i in range(0, len(texts), WINDOW_SIZE):
        window = texts[i:i+WINDOW_SIZE]
        combined_text = "\n---\n".join(window)
        
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(chunks_text=combined_text)
        logger.info(f"Processing window {i // WINDOW_SIZE + 1} with {len(window)} chunks...")
        
        extracted = await call_llm(prompt)
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
    final_merged = await call_llm(consolidation_prompt)
    if not final_merged:
         logger.warning("Consolidation returned empty, falling back to first result.")
         return results_list[0]
         
    return final_merged

from datetime import datetime

def compare_with_tenant(extracted: dict, tenant: Tenant, doc_date: datetime) -> dict:
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
    tenant_meta = tenant.tenant_metadata or {}
    
    # --- ADMIN CRITERIA ---
    ex_admin = extracted.get("admin_criteria", {})
    t_geo_zone = tenant_meta.get("geo_zone", "")
    
    ex_deadline_str = ex_admin.get("deadline")
    if ex_deadline_str and isinstance(ex_deadline_str, str) and ex_deadline_str != "null":
        try:
            # handle formats like YYYY-MM-DD
            ex_deadline = datetime.strptime(ex_deadline_str, "%Y-%m-%d").date()
            if doc_date and doc_date.date() > ex_deadline:
                is_compliant = False
                details["admin"]["deadline"] = f"Failed: Upload date {doc_date.date()} is past the deadline {ex_deadline}"
            else:
                details["admin"]["deadline"] = f"Passed: Upload date {doc_date.date() if doc_date else 'unknown'} is before deadline {ex_deadline}"
        except ValueError:
            details["admin"]["deadline"] = f"Warning: Unparsed date format: {ex_deadline_str}"
            
    ex_zone_geo = ex_admin.get("geo_zone")
    if ex_zone_geo and isinstance(ex_zone_geo, str) and ex_zone_geo != "null":
        # A simple check: if the required geo_zone text isn't somewhat included in the tenant's zone
        # This is a naive substring match. In production, consider NLP-based matching.
        if t_geo_zone and ex_zone_geo.lower() not in t_geo_zone.lower():
             details["admin"]["geo_zone"] = f"Warning: Tenant zone '{t_geo_zone}' might not match required zone '{ex_zone_geo}'"
             # Warn rather than fail immediately due to naive string match
        else:
             details["admin"]["geo_zone"] = f"Passed or unchecked: required {ex_zone_geo}"

    # --- FINANCIAL CRITERIA ---
    ex_fin = extracted.get("financial_criteria", {})
    
    ex_annual_revenue = ex_fin.get("annual_revenue")
    t_annual_revenue = tenant_meta.get("annual_revenue")
    
    if ex_annual_revenue is not None and ex_annual_revenue != "null" and t_annual_revenue is not None:
        try:
            ex_val = float(str(ex_annual_revenue).replace(" ", "").replace(",", ".").split()[0])
            t_val = float(t_annual_revenue)
            if t_val < ex_val:
                is_compliant = False
                details["financial"]["annual_revenue"] = f"Failed: Tenant revenue {t_val} < Required {ex_val}"
            else:
                 details["financial"]["annual_revenue"] = f"Passed: Tenant revenue {t_val} >= Required {ex_val}"
        except (ValueError, TypeError):
            pass
            
    ex_guarantee = ex_fin.get("guarantee")
    t_guarantee = tenant_meta.get("guarantee")
    if ex_guarantee and ex_guarantee != "null":
         if t_guarantee and str(t_guarantee).strip() != "":
             # Hard string comparison, naive logic
             details["financial"]["guarantee"] = f"Checked visually: Required={ex_guarantee} | Tenant={t_guarantee}"
         else:
             is_compliant = False
             details["financial"]["guarantee"] = f"Failed: Required guarantee '{ex_guarantee}' but Tenant has none."

    # --- TECHNICAL CRITERIA ---
    ex_tech = extracted.get("technical_criteria", {})
    
    required_certs = ex_tech.get("certifications", [])
    if required_certs and isinstance(required_certs, list):
        tenant_certs = set([c.lower() for c in tenant_meta.get("certifications", [])])
        missing = [c for c in required_certs if isinstance(c, str) and c.lower() not in tenant_certs]
        if missing:
            is_compliant = False
            details["technical"]["certifications"] = f"Missing certifications: {missing}"
        else:
            details["technical"]["certifications"] = "Passed all certifications"

    ex_staff = ex_tech.get("staff_count", {})
    t_staff = tenant_meta.get("staff_count", {})
    if isinstance(ex_staff, dict) and isinstance(t_staff, dict):
        for role in ["engineers", "technicians", "others"]:
             req_count = ex_staff.get(role)
             t_count = t_staff.get(role, 0)
             if req_count is not None and req_count != "null":
                 try:
                     req_val = float(req_count)
                     t_val = float(t_count)
                     if t_val < req_val:
                         is_compliant = False
                         details["technical"][f"staff_{role}"] = f"Failed: Tenant {role} {t_val} < Required {req_val}"
                     else:
                         details["technical"][f"staff_{role}"] = f"Passed: Tenant {role} {t_val} >= Required {req_val}"
                 except (ValueError, TypeError):
                     pass

    return {
        "is_compliant": is_compliant,
        "details": details
    }

import asyncio

async def run_compliance_for_document(doc_id: str, tenant_db_id: str) -> None:
    db = SessionLocal()
    try:
        # Load the tenant
        tenant = await asyncio.to_thread(lambda: db.query(Tenant).filter(Tenant.id == tenant_db_id).first())
        if not tenant:
            logger.error(f"Tenant {tenant_db_id} not found.")
            return
            
        # Get DB document mapping
        doc_entry = await asyncio.to_thread(lambda: db.query(Document).filter(Document.id == doc_id).first())
        if not doc_entry:
            logger.error(f"Document entry for id {doc_id} not found")
            return
            
        # Load the chunks
        chunks = await asyncio.to_thread(lambda: db.query(Chunk).filter(Chunk.document_id == doc_id).order_by(Chunk.chunk_index).all())
        if not chunks:
            logger.warning(f"No chunks found for document {doc_id} in DB.")
            return
            
        texts = [c.text_original for c in chunks]
        
        # 1. & 2. & 3. Extraction with Sliding Window + LLM merge
        extracted_criteria = await extract_criteria_sliding_window(texts)
        if not extracted_criteria:
            logger.error("Extraction failed or returned empty.")
            return
            
        # 4. Compare with Tenant
        comparison_results = compare_with_tenant(extracted_criteria, tenant, doc_entry.created_at)
        
        # 5. Save to database
        def save_compliance():
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

        await asyncio.to_thread(save_compliance)
        logger.info(f"Compliance check completed for document {doc_id}.")
        
        # 6. Publish event back to UI with Appel d'Offres metadata
        try:
            from compliance_service.publisher import publish_compliance_result
            metadata = doc_entry.doc_metadata or {}
            # Provide merged AO data (extracted + details)
            ao_payload = {
                "extracted_criteria": extracted_criteria,
                "compliance_details": comparison_results["details"],
                "document_filename": doc_entry.filename,
                "ao_status": "COMPLIANT" if comparison_results["is_compliant"] else "REJECTED"
            }
            await asyncio.to_thread(
                publish_compliance_result,
                doc_id,
                tenant_db_id,
                comparison_results["is_compliant"],
                ao_payload
            )
        except Exception as e:
            logger.error(f"Failed to publish compliance UI event: {e}")

    except Exception as e:
        logger.error(f"Error during compliance check: {e}")
        await asyncio.to_thread(db.rollback)
    finally:
        db.close()
