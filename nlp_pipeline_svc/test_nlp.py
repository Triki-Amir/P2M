import sys
from pathlib import Path
import json

# Add project root to sys.path so we can import 'shared' and 'app'
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from shared.models import OcrDocument, OcrPage, OcrBlock
from shared import event_bus
from nlp_pipeline_svc.app.main import run_consumer
from nlp_pipeline_svc.app import config
from nlp_pipeline_svc.app.nlp.metadata_extractor import extract_metadata

def create_mock_ocr_data():
    """Creates a dummy ocr_completed.json for testing."""
    mock_doc = OcrDocument(
        doc_id="test_tender.pdf",
        source_lang="fr",
        pages=[
            OcrPage(
                page_index=0,
                blocks=[
                    OcrBlock(
                        type="heading",
                        text="Appel d'offres pour services de nettoyage",
                        bbox=[10.0, 10.0, 100.0, 30.0]
                    ),
                    OcrBlock(
                        type="paragraph",
                        text="Ministère de l'Intérieur — Direction Générale des Collectivités Locales",
                        bbox=[10.0, 35.0, 200.0, 50.0]
                    ),
                    OcrBlock(
                        type="paragraph",
                        text="Le présent marché a pour objet la prestation de services de nettoyage pour nos bureaux à Paris.",
                        bbox=[10.0, 55.0, 200.0, 80.0]
                    ),
                    OcrBlock(
                        type="paragraph",
                        text="Budget prévisionnel : 150 000 MAD TTC",
                        bbox=[10.0, 85.0, 200.0, 100.0]
                    ),
                ]
            ),
            OcrPage(
                page_index=1,
                blocks=[
                    OcrBlock(
                        type="paragraph",
                        text="Date limite de remise des offres : 15/06/2026 à 12h00.",
                        bbox=[10.0, 10.0, 200.0, 30.0]
                    ),
                ]
            ),
        ]
    )
    
    # Write to data folder
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    event_bus.publish(config.INPUT_EVENT, mock_doc, config.DATA_DIR)
    print(f"[test_nlp] Mock OCR data created at {config.DATA_DIR}/{config.INPUT_EVENT}.json")
    return mock_doc

def test_metadata_extractor(mock_doc: OcrDocument):
    """Unit-tests the metadata extractor directly (no pipeline required)."""
    print("\n[test_nlp] ── Metadata extraction ──────────────────────────────")
    meta = extract_metadata(mock_doc)
    for key, value in meta.items():
        status = "✓" if value else "–"
        print(f"  {status}  {key}: {value!r}")
    assert meta["title"] is not None, "title should be extracted"
    assert meta["deadline"] is not None, "deadline should be extracted"
    assert meta["organization"] is not None, "organization should be extracted"
    assert meta["budget"] is not None, "budget should be extracted"
    print("[test_nlp] Metadata assertions passed.")

def test_nlp_service():
    """Runs the NLP service on the mock data and verifies output."""
    print("\n[test_nlp] ── Full pipeline ─────────────────────────────────────")
    
    # Run the consumer (which reads the mock data we just created)
    run_consumer()
    
    # Check if output exists
    output_path = config.DATA_DIR / f"{config.OUTPUT_EVENT}.json"
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"[test_nlp] Success! Found {len(data['chunks'])} chunks in output.")
            for i, chunk in enumerate(data['chunks']):
                print(f"  Chunk {i+1}: {chunk['text_en'][:50]}... ({chunk['source_lang']})")
            # Verify doc_metadata is present in the output
            meta = data.get("doc_metadata", {})
            print(f"[test_nlp] doc_metadata in output: {meta}")
    else:
        print("[test_nlp] FAILED: Output file not found.")

if __name__ == "__main__":
    mock_doc = create_mock_ocr_data()
    test_metadata_extractor(mock_doc)
    test_nlp_service()
