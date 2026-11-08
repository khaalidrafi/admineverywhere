/** aiProviders.ts — one-click provider presets for the AI settings form.
 *
 *  Owner order 2026-11-08 ("add keyless APIs like kilo code gateway; find
 *  more keyless options in omniroute"): the three FREE/KEYLESS entries below
 *  were each verified live from this desk on 2026-11-08 — a real HTTP POST
 *  answered before anything shipped:
 *    - Kilo Gateway  `kilo-auto/free`  → keyless chat confirmed (200, token-free)
 *    - AI Horde      `oai.aihorde.net` → anonymous key `0000000000` confirmed
 *    - Pollinations  `/openai` compat  → keyless chat confirmed
 *  (uncloseai.com is listed in OmniRoute's noauth catalog but its endpoint
 *  did not answer /v1/models from here on 2026-11-08 — left out rather than
 *  shipping a dead preset.)
 *
 *  Contract law kept: the settings form still renders EXACTLY three inputs
 *  (base URL, API key, model — MVP brief). Presets are BUTTONS that fill
 *  those three inputs; they add no input element.
 *
 *  Every entry speaks OpenAI /chat/completions (the app's single wire law).
 */

export interface ProviderPreset {
  id: string;
  label: string;
  /** Filled into the Base URL input (the app appends /chat/completions). */
  baseUrl: string;
  /** Filled into the Model input. Always a model verified live or a stable alias. */
  model: string;
  /** Filled into the API key input ("" = none needed). */
  apiKey: string;
  /** true = works with no signup at all (verified keyless). */
  keyless: boolean;
  /** One line shown under the presets row. */
  note: string;
}

export const AI_PRESETS: ProviderPreset[] = [
  {
    id: "kilo-free",
    label: "Kilo Gateway",
    baseUrl: "https://ai-gateway.kilo.ai/api/v1",
    model: "kilo-auto/free",
    apiKey: "",
    keyless: true,
    note: "Free auto-routed model, no signup. Hundreds more models with a free kilo.ai key.",
  },
  {
    id: "aihorde",
    label: "AI Horde",
    baseUrl: "https://oai.aihorde.net/v1",
    model: "koboldcpp/debug-gemma-4-E2B-Queen-it-qat-q4_0-unquantized.i1-Q4_K_M",
    apiKey: "0000000000",
    keyless: true,
    note: "Volunteer GPU swarm, truly keyless (anonymous key). Slow under load; model list at oai.aihorde.net.",
  },
  {
    id: "pollinations",
    label: "Pollinations",
    baseUrl: "https://text.pollinations.ai/openai",
    model: "openai",
    apiKey: "",
    keyless: true,
    note: "Free anonymous OpenAI-compatible endpoint. Rate limited per IP.",
  },
  {
    id: "openai",
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    apiKey: "",
    keyless: false,
    note: "Needs your platform.openai.com key.",
  },
  {
    id: "groq",
    label: "Groq",
    baseUrl: "https://api.groq.com/openai/v1",
    model: "llama-3.3-70b-versatile",
    apiKey: "",
    keyless: false,
    note: "Needs a console.groq.com key (generous free tier).",
  },
  {
    id: "ollama",
    label: "Ollama (local)",
    baseUrl: "http://localhost:11434/v1",
    model: "llama3.2",
    apiKey: "",
    keyless: true,
    note: "Your own machine — nothing leaves it. `ollama serve` must be running.",
  },
];

/** The three keyless presets, first-class (owner order: keyless APIs). */
export const KEYLESS_PRESETS: ProviderPreset[] = AI_PRESETS.filter((p) => p.keyless);

export function presetById(id: string): ProviderPreset | undefined {
  return AI_PRESETS.find((p) => p.id === id);
}
