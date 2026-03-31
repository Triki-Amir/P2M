# Détails Techniques du Service NLP Pipeline

Ce document explique le fonctionnement du service NLP, ses entrées (inputs) et ses sorties (outputs).

---

## 1. Ce qui s'est passé (Le Flux)

Le service NLP agit comme un **pont intelligent** entre les données brutes extraites par l'OCR et l'indexation pour l'IA. Voici les étapes effectuées :

1.  **Consommation** : Le service lit le fichier `ocr_completed.json` généré par le service OCR.
2.  **Nettoyage (Cleaning)** : Il supprime les espaces inutiles, normalise les sauts de ligne et nettoie les caractères spéciaux.
3.  **Détection de Langue** : Pour chaque bloc de texte, il détecte s'il s'agit de **Français (FR)**, **Arabe (AR)** ou **Anglais (EN)**.
4.  **Traduction** : Si le texte n'est pas en anglais, il le traduit (simulation pour l'instant) pour créer un espace d'embedding unifié.
5.  **Découpage (Chunking)** : Il découpe les longs paragraphes en segments plus petits (200-500 mots) pour que l'IA puisse les traiter efficacement.
6.  **Génération d'ID** : Il génère un `chunk_id` unique (MD5 hash) pour chaque segment.
7.  **Publication** : Il sauvegarde le résultat final dans `nlp_completed.json`.

---

## 2. L'Entrée (Input) : `ocr_completed.json`

C'est le résultat brut de l'analyse visuelle du PDF. Il contient :
- **doc_id** : Le nom du fichier PDF original.
- **pages** : Une liste des pages du document.
- **blocks** : Pour chaque page, les blocs de texte détectés avec leur type (`heading`, `paragraph`, `table`) et leurs coordonnées (`bbox`).

---

## 3. La Sortie (Output) : `nlp_completed.json`

C'est le fichier prêt pour l'IA. Voici le détail des champs produits :

| Champ | Description |
| :--- | :--- |
| `doc_id` | Identifiant du document source. |
| `chunk_id` | Identifiant unique pour ce segment de texte. |
| `block_type` | Le type sémantique (ex: titre, paragraphe). |
| `source_lang` | La langue originale détectée (fr, ar, en). |
| `text_original` | Le texte tel qu'il était dans le PDF (nettoyé). |
| `text_en` | **Le texte en Anglais.** C'est ce texte qui sera utilisé pour créer les vecteurs de recherche. |
| `bbox` | Les coordonnées sur la page pour pouvoir surligner la source plus tard. |

---

## 4. Pourquoi est-ce important ?

Sans cette étape NLP :
- L'IA aurait du mal à traiter des documents multilingues.
- Les paragraphes trop longs dépasseraient la "fenêtre de contexte" des modèles LLM.
- La recherche sémantique serait moins précise car elle mélangerait les langues.

Désormais, votre document est transformé en **"connaissances structurées"** prêtes à être injectées dans une base de données vectorielle.
