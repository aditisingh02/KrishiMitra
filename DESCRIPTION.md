# 🌱 KrishiMitra AI — an AI agronomist that *runs* your farm, not just answers questions

**See it live**
- 🔗 Live app: https://krishimitra-ai-flax.vercel.app/
- ▶️ Demo video (3 min): https://youtu.be/IBrTLGzkR4A

---

## The problem

India has 100M+ small farmers, but almost no access to an agronomist. Most can't read
manuals or speak English, advice arrives too late, and weather, prices, diseases and
government schemes all live in separate silos. Generic chatbots only *answer questions* —
farmers need to be **told what to do next**, in their own language.

## What KrishiMitra is

A **voice-first, multilingual AI agronomist** that runs on a basic phone. A farmer speaks
in their own language and gets **one clear, prioritized action plan, read aloud** —
personalized to *their* farm (crops, soil, weather, disease history, mandi prices) and
grounded in real data, not generic tips.

## Built for Bharat × powered by Agentic AI

It's not one chatbot — it's a **team of agents**. A **Planner** breaks each request into a
task graph; specialist agents (**Crop Health, Natural Farming, Weather, Market, Finance,
Risk, Vision**) run in parallel; and an **Action Planner** synthesizes a single, localized
plan. Answers are grounded by a **RAG knowledge base** + **real APIs** (OpenWeather,
Agmarknet mandi prices) and remembered in a **Farm Digital Twin**, so the AI never invents
dosages or prices.

## All four feature areas (the brief asked for two)

- 🌿 **Disease ID & Treatment** — snap a leaf photo → diagnosis, severity & an organic remedy, read aloud
- ☁️ **Weather & Market Intelligence** — live forecast + real mandi prices → spray, irrigation & sell advice
- 🌱 **Natural Farming Education** — a multilevel "food-forest" cropping designer (4 layers + spacing)
- 💰 **Seed & Financial Guidance** — voice query → real government schemes (PM-KISAN, PKVY, PMFBY), eligibility & next step

## What makes it stand out

- **Agentic, not a chatbot** — planner + parallel specialists + synthesizer
- **Proactive farm OS** — an autonomous monitor warns *before* problems spread, even on **WhatsApp**
- **Fully localized in 8 Indian languages** — the entire UI, every AI answer, and voice in/out
  (Hindi, English, Punjabi, Marathi, Tamil, Telugu, Bengali, Gujarati)
- **Accurate by design** — RAG grounding + strict JSON guardrails + graceful degradation; real data only

## Tech

FastAPI + Fireworks AI (`gpt-oss-120b` text agents, `Kimi K2.6` vision) · Next.js 14 + Tailwind ·
Clerk auth · SQLite farm twin · Web Speech (STT/TTS) · Twilio WhatsApp. Deploys in minutes on
Render + Vercel; per-farm caching keeps AI cost low and stateless agents scale horizontally.

---

**KrishiMitra — an agronomist in every farmer's pocket. Built for Bharat. Powered by Agentic AI.**
