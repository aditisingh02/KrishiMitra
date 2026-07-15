"""Lightweight RAG knowledge base.

A curated natural-farming / disease / scheme corpus with simple TF-style keyword
retrieval. Keeps the demo dependency-free (no ChromaDB needed) while still
grounding agent answers in real agronomy facts to reduce hallucination.
Swap `retrieve` for a ChromaDB/FAISS query when you wire embeddings.
"""
from __future__ import annotations

import re
from typing import Any

KB: list[dict[str, str]] = [
    # ---- Natural farming preparations ----
    {
        "topic": "Jeevamrut",
        "tags": "jeevamrut natural farming fertilizer microbial soil tonic growth",
        "text": "Jeevamrut is a fermented microbial culture made from 10kg cow dung, 10L cow urine, "
        "2kg jaggery, 2kg pulse flour, a handful of farm soil and 200L water. Ferment 3-5 days, "
        "stir twice daily. Apply 200L per acre via irrigation or as foliar spray (diluted 1:10) "
        "every 7-15 days. It boosts soil microbial activity and nutrient availability.",
    },
    {
        "topic": "Beejamrut",
        "tags": "beejamrut seed treatment natural farming sowing germination",
        "text": "Beejamrut is a seed treatment using cow dung, cow urine, lime and water. Coat seeds "
        "before sowing to protect young roots from soil-borne and seed-borne pathogens and improve germination.",
    },
    {
        "topic": "Panchagavya",
        "tags": "panchagavya foliar spray growth immunity natural farming",
        "text": "Panchagavya is a fermented blend of cow dung, urine, milk, curd and ghee. Used as a 3% "
        "foliar spray (300ml in 10L water) it acts as a growth promoter and improves crop immunity and shelf life.",
    },
    {
        "topic": "Neem oil spray",
        "tags": "neem oil pest pesticide fungus mildew aphid whitefly organic",
        "text": "Neem oil (azadirachtin) is a broad-spectrum organic pesticide and antifungal. Mix 5ml neem "
        "oil + 1ml liquid soap per litre of water. Spray in the cool evening, covering leaf undersides. "
        "Effective against aphids, whitefly, mites and early fungal infection. Avoid spraying before rain.",
    },
    {
        "topic": "Mulching",
        "tags": "mulch moisture weed soil temperature straw natural farming",
        "text": "Mulching with straw or dry biomass conserves soil moisture, suppresses weeds, moderates soil "
        "temperature and feeds soil life as it decomposes. Core practice in Subhash Palekar Natural Farming.",
    },
    # ---- Diseases ----
    {
        "topic": "Powdery Mildew",
        "tags": "powdery mildew white spots powder fungus tomato cucurbit humidity disease",
        "text": "Powdery Mildew shows as white powdery patches on leaf surfaces, thriving in warm humid weather "
        "with poor airflow. Organic control: spray diluted raw milk (1:9 with water) or potassium-bicarbonate "
        "solution, improve spacing/airflow, and apply neem oil. Remove severely infected leaves.",
    },
    {
        "topic": "Early Blight",
        "tags": "early blight alternaria brown spots concentric rings tomato potato disease",
        "text": "Early Blight (Alternaria) causes dark brown spots with concentric rings on older lower leaves, "
        "often with a yellow halo. Remove affected leaves, avoid overhead watering, mulch to prevent soil splash, "
        "and apply neem oil or a copper-based organic fungicide and cow-dung-based Jeevamrut to build resistance.",
    },
    {
        "topic": "Nitrogen Deficiency",
        "tags": "nitrogen deficiency yellow leaves chlorosis pale lower leaves nutrient",
        "text": "Nitrogen deficiency appears as uniform yellowing (chlorosis) starting on older lower leaves and "
        "stunted growth. Correct with Jeevamrut, well-rotted compost/vermicompost, or a foliar spray of "
        "fermented buttermilk; intercrop legumes (cowpea) to fix nitrogen naturally.",
    },
    {
        "topic": "Leaf Curl Virus",
        "tags": "leaf curl virus whitefly tomato chilli curling upward disease vector",
        "text": "Leaf Curl Virus is spread by whitefly and causes upward leaf curling, crinkling and stunting. "
        "Control the whitefly vector with yellow sticky traps and neem oil, remove infected plants, and use "
        "barrier crops like maize. There is no cure once infected - manage the vector.",
    },
    # ---- Schemes ----
    {
        "topic": "PM-KISAN",
        "tags": "pm-kisan scheme subsidy income support government farmer ₹6000",
        "text": "PM-KISAN provides ₹6,000/year in three ₹2,000 installments to landholding farmer families. "
        "Eligibility: cultivable landholding; excludes institutional landholders and income-tax payers. "
        "Apply via pmkisan.gov.in or a Common Service Centre with Aadhaar and land records.",
    },
    {
        "topic": "Paramparagat Krishi Vikas Yojana",
        "tags": "pkvy organic natural farming subsidy cluster grant scheme government",
        "text": "PKVY supports organic/natural farming clusters with financial assistance of around ₹50,000 per "
        "hectare over 3 years (toward inputs, certification and marketing). Farmers organise into clusters; "
        "apply through the State Agriculture Department.",
    },
    {
        "topic": "Pradhan Mantri Fasal Bima Yojana",
        "tags": "pmfby crop insurance premium risk weather loss scheme government",
        "text": "PMFBY is the crop insurance scheme: farmer premium is 2% for Kharif, 1.5% for Rabi and 5% for "
        "commercial/horticultural crops, with the government subsidising the rest. Covers yield loss from "
        "drought, flood, pest and disease. Enroll via bank/CSC within the cutoff for each season.",
    },
]


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z₹0-9]+", s.lower())


def retrieve(query: str, k: int = 3) -> list[dict[str, str]]:
    """Return the top-k most relevant KB chunks for a query."""
    q = set(_tokens(query))
    scored: list[tuple[int, dict[str, str]]] = []
    for chunk in KB:
        hay = set(_tokens(chunk["tags"] + " " + chunk["topic"] + " " + chunk["text"]))
        score = len(q & hay)
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:k]]


def context_for(query: str, k: int = 3) -> str:
    chunks = retrieve(query, k)
    if not chunks:
        return ""
    return "\n\n".join(f"[{c['topic']}] {c['text']}" for c in chunks)
