import {
  LayoutDashboard,
  Inbox,
  CalendarClock,
  PhoneCall,
  Users,
  Receipt,
  BarChart3,
  Settings,
  LucideIcon,
} from "lucide-react";
import {
  VoicePersona,
  LanguageOption,
  LanguageMode,
  ClinicProfile,
  GreetingLanguage,
} from "./types";

export * from "./types";

export {
  ALL_COUNTRIES,
  ALL_CURRENCIES,
  getCountryProfile,
  getCurrencyForCode,
  getAllCountries,
  getAllCurrencies,
} from "@/lib/country-metadata";
export type { CountryOption, CurrencyOption } from "@/lib/country-metadata";

export interface ClinicNavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  badge?: string;
  roles?: ('doctor' | 'receptionist')[];
}

export const CLINIC_NAV_ITEMS: ClinicNavItem[] = [
  { href: "/clinic", label: "Consultation Desk", icon: LayoutDashboard, roles: ['doctor'] },
  { href: "/clinic/schedule", label: "Queue & Schedule", icon: CalendarClock, roles: ['doctor', 'receptionist'] },
  { href: "/clinic/calls", label: "Call History", icon: PhoneCall, roles: ['doctor', 'receptionist'] },
  { href: "/clinic/action-center", label: "Action Center", icon: Inbox, roles: ['doctor', 'receptionist'] },
  { href: "/clinic/patients", label: "Patient Records", icon: Users, roles: ['doctor'] },
  { href: "/clinic/revenue", label: "Billing & Revenue", icon: Receipt, roles: ['doctor'] },
  { href: "/clinic/analytics", label: "Reports", icon: BarChart3, roles: ['doctor'] },
  { href: "/clinic/settings", label: "Settings", icon: Settings, roles: ['doctor'] },
];

export { DEFAULT_WEEKLY_HOURS } from '@/lib/weekly-schedule';
export const VOICE_PERSONAS: VoicePersona[] = [
  {
    id: "aura-asteria-en",
    label: "Asteria",
    desc: "Clear, conversational, and natural tone optimized for healthcare reception and patient intake.",
    provider: "deepgram",
    sampleAudio: "",
    tier: "starter",
    category: "studio",
    gender: "feminine",
    accent: "US English",
    language: "english",
    badge: "RECOMMENDED",
    role: "Front-Desk Receptionist",
    tone: "Warm & Conversational",
    defaultPhrase:
      "Hello! Welcome to {clinic_name}. How can I help you today?",
  },
  {
    id: "aura-luna-en",
    label: "Luna",
    desc: "Calm, gentle, and empathetic cadence suitable for pediatrics, mental health, and family care.",
    provider: "deepgram",
    sampleAudio: "",
    tier: "starter",
    category: "standard",
    gender: "feminine",
    accent: "US English",
    language: "english",
    badge: "RECOMMENDED",
    role: "Patient Care Coordinator",
    tone: "Gentle & Attentive",
    defaultPhrase:
      "Hello, thank you for calling {clinic_name}. How may I assist you today?",
  },
  {
    id: "aura-athena-en",
    label: "Athena",
    desc: "Crisp, articulate, and formal voice tailored for specialist clinics and diagnostic centers.",
    provider: "deepgram",
    sampleAudio: "",
    tier: "starter",
    category: "standard",
    gender: "feminine",
    accent: "UK English",
    language: "english",
    role: "Clinical Specialist",
    tone: "Crisp & Professional",
    defaultPhrase:
      "Good day, you have reached {clinic_name}. How may I direct your call?",
  },
  {
    id: "aura-arcas-en",
    label: "Arcas",
    desc: "Natural, confident, and approachable male voice for general practice scheduling.",
    provider: "deepgram",
    sampleAudio: "",
    tier: "starter",
    category: "standard",
    gender: "masculine",
    accent: "US English",
    language: "english",
    role: "Appointment Specialist",
    tone: "Confident & Friendly",
    defaultPhrase:
      "Hello and welcome to {clinic_name}. I can help you schedule or manage an appointment.",
  },
  {
    id: "aura-zeus-en",
    label: "Zeus",
    desc: "Deep, steady, and reassuring voice providing clear structure for busy clinical practices.",
    provider: "deepgram",
    sampleAudio: "",
    tier: "pro",
    category: "studio",
    gender: "masculine",
    accent: "US English",
    language: "english",
    role: "Practice Coordinator",
    tone: "Deep & Reassuring",
    defaultPhrase:
      "Thank you for calling {clinic_name}. Please let me know how I can help you today.",
  },
  {
    id: "aura-stella-en",
    label: "Stella",
    desc: "Bright, energetic, and engaging voice tailored for rapid triage and wellness clinics.",
    provider: "deepgram",
    sampleAudio: "",
    tier: "starter",
    category: "standard",
    gender: "feminine",
    accent: "US English",
    language: "english",
    badge: "RAPID RESPONSE",
    role: "Express Reception",
    tone: "Bright & Energetic",
    defaultPhrase:
      "Hi there! Welcome to {clinic_name}. How can I assist you today?",
  },
  {
    id: "aura-helios-en",
    label: "Helios",
    desc: "Polished, warm British English voice with composed and courteous demeanor.",
    provider: "deepgram",
    sampleAudio: "",
    tier: "pro",
    category: "studio",
    gender: "masculine",
    accent: "UK English",
    language: "english",
    role: "Care Concierge",
    tone: "Polished & Courteous",
    defaultPhrase:
      "Good day, thank you for contacting {clinic_name}. How may I help you today?",
  },
];

const VOICE_PERSONA_ALIASES: Record<string, string> = {
  priya: 'aura-asteria-en',
  aria: 'aura-asteria-en',
  'gemini-aoede': 'aura-asteria-en',
  meena: 'aura-luna-en',
  kavya: 'aura-athena-en',
  'gemini-kore': 'aura-athena-en',
  rohan: 'aura-arcas-en',
  naveen: 'aura-arcas-en',
  'gemini-puck': 'aura-arcas-en',
  zeus: 'aura-zeus-en',
  stella: 'aura-stella-en',
  helios: 'aura-helios-en',
  asteria: 'aura-asteria-en',
  luna: 'aura-luna-en',
  athena: 'aura-athena-en',
  arcas: 'aura-arcas-en',
};

export function normalizeVoicePersona(id?: string | null): string {
  const candidate = (id || '').trim().toLowerCase();
  const normalized = VOICE_PERSONA_ALIASES[candidate] || candidate;
  return VOICE_PERSONAS.some((persona) => persona.id === normalized)
    ? normalized
    : 'aura-asteria-en';
}

export const INDIAN_LANGUAGES: LanguageOption[] = [
  {
    id: "te",
    name: "Telugu (Telugish)",
    nativeName: "తెలుగు · Telugish",
    flag: "🇮🇳",
    region: "indian",
    category: "Andhra & Telangana",
    defaultPhrase:
      "Namaskaram! {clinic_name} ki swagatham. Nenu meeku ela sahaya padagalanu?",
    transliteratedPhrase:
      "Namaskaram! {clinic_name} ki swagatham. Nenu meeku ela sahaya padagalanu?",
    scriptPhrase:
      "నమస్కారం, {clinic_name} కి స్వాగతం. నేను మీకు ఎలా సహాయపడగలను?",
    voices: [
      "gemini-aoede",
      "gemini-kore",
      "gemini-puck",
      "gemini-charon",
      "priya",
      "naveen",
      "meena",
    ],
  },
  {
    id: "ta",
    name: "Tamil (Tanglish)",
    nativeName: "தமிழ் · Tanglish",
    flag: "🇮🇳",
    region: "indian",
    category: "Tamil Nadu & Chennai",
    defaultPhrase:
      "Vanakkam! {clinic_name}-ukku ungalai anbudan varaverkirom. Ungalukku enna udhavi thevai?",
    transliteratedPhrase:
      "Vanakkam! {clinic_name}-ukku ungalai anbudan varaverkirom. Ungalukku enna udhavi thevai?",
    scriptPhrase:
      "வணக்கம், {clinic_name}-க்கு உங்களை வரவேற்கிறோம். உங்களுக்கு என்ன உதவி வேண்டும்?",
    voices: [
      "gemini-aoede",
      "gemini-kore",
      "gemini-puck",
      "gemini-charon",
      "priya",
      "naveen",
      "meena",
    ],
  },
  {
    id: "hi",
    name: "Hindi (Hinglish)",
    nativeName: "हिन्दी · Hinglish",
    flag: "🇮🇳",
    region: "indian",
    category: "Delhi & Pan-India",
    defaultPhrase:
      "Namaste! {clinic_name} mein aapka swagat hai. Main aapki kya madad kar sakti hoon?",
    transliteratedPhrase:
      "Namaste! {clinic_name} mein aapka swagat hai. Main aapki kya madad kar sakti hoon?",
    scriptPhrase:
      "नमस्ते, {clinic_name} में आपका स्वागत है। मैं आपकी क्या सहायता कर सकती हूँ?",
    voices: [
      "gemini-aoede",
      "gemini-kore",
      "gemini-puck",
      "gemini-charon",
      "priya",
      "naveen",
      "meena",
    ],
  },
  {
    id: "kn",
    name: "Kannada (Kanglish)",
    nativeName: "ಕನ್ನಡ · Kanglish",
    flag: "🇮🇳",
    region: "indian",
    category: "Karnataka & Bengaluru",
    defaultPhrase:
      "Namaskara! {clinic_name}-ge suswagatha. Naanu nimage hege sahaya madabahudu?",
    transliteratedPhrase:
      "Namaskara! {clinic_name}-ge suswagatha. Naanu nimage hege sahaya madabahudu?",
    scriptPhrase:
      "ನಮಸ್ಕಾರ, {clinic_name} ಗೆ ಸುಸ್ವಾಗತ. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
    voices: [
      "gemini-aoede",
      "gemini-kore",
      "gemini-puck",
      "gemini-charon",
      "priya",
      "naveen",
      "meena",
    ],
  },
  {
    id: "ml",
    name: "Malayalam (Manglish)",
    nativeName: "മലയാളം · Manglish",
    flag: "🇮🇳",
    region: "indian",
    category: "Kerala & Kochi",
    defaultPhrase:
      "Namaskaram! {clinic_name}-ilekku swagatham. Njangal engane sahayikkanam?",
    transliteratedPhrase:
      "Namaskaram! {clinic_name}-ilekku swagatham. Njangal engane sahayikkanam?",
    scriptPhrase:
      "നമസ്കാരം, {clinic_name} ലേക്ക് സ്വാഗതം. ഞങ്ങൾക്ക് എങ്ങനെ സഹായിക്കാനാകും?",
    voices: [
      "gemini-aoede",
      "gemini-kore",
      "gemini-puck",
      "gemini-charon",
      "priya",
      "naveen",
      "meena",
    ],
  },
  {
    id: "mr",
    name: "Marathi",
    nativeName: "मराठी · Romanized",
    flag: "🇮🇳",
    region: "indian",
    category: "Maharashtra & Mumbai",
    defaultPhrase:
      "Namaskar! {clinic_name} madhe aple swagat ahe. Me aplyala kashi madat karu shakto?",
    transliteratedPhrase:
      "Namaskar! {clinic_name} madhe aple swagat ahe. Me aplyala kashi madat karu shakto?",
    scriptPhrase:
      "नमस्कार, {clinic_name} मध्ये आपले स्वागत आहे. मी आपल्याला कशी मदत करू शकतो?",
    voices: [
      "gemini-aoede",
      "gemini-kore",
      "gemini-puck",
      "gemini-charon",
      "priya",
      "naveen",
      "meena",
    ],
  },
  {
    id: "bn",
    name: "Bengali (Banglish)",
    nativeName: "বাংলা · Banglish",
    flag: "🇮🇳",
    region: "indian",
    category: "Bengal & Kolkata",
    defaultPhrase:
      "Nomoshkar! {clinic_name}-e apnake shagotom. Ami apnake kibhabe sahajjo korte pari?",
    transliteratedPhrase:
      "Nomoshkar! {clinic_name}-e apnake shagotom. Ami apnake kibhabe sahajjo korte pari?",
    scriptPhrase:
      "নমস্কার, {clinic_name}-এ আপনাকে স্বাগতম। আমি আপনাকে কীভাবে সাহায্য করতে পারি?",
    voices: [
      "gemini-aoede",
      "gemini-kore",
      "gemini-puck",
      "gemini-charon",
      "priya",
      "naveen",
      "meena",
    ],
  },
  {
    id: "gu",
    name: "Gujarati",
    nativeName: "ગુજરાતી · Romanized",
    flag: "🇮🇳",
    region: "indian",
    category: "Gujarat & Ahmedabad",
    defaultPhrase:
      "Namaste! {clinic_name} ma aapnu swagat chhe. Hu tamne kevi rite madad kari shaku?",
    transliteratedPhrase:
      "Namaste! {clinic_name} ma aapnu swagat chhe. Hu tamne kevi rite madad kari shaku?",
    scriptPhrase:
      "નમસ્તે, {clinic_name} માં આપનું સ્વાગત છે. હું તમને કેવી રીતે મદદ કરી શકું?",
    voices: [
      "gemini-aoede",
      "gemini-kore",
      "gemini-puck",
      "gemini-charon",
      "priya",
      "naveen",
      "meena",
    ],
  },
  {
    id: "en_in",
    name: "Indian English",
    nativeName: "Indian English (en-IN)",
    flag: "🇮🇳",
    region: "indian",
    category: "Pan-India Metro",
    defaultPhrase:
      "Hello! Thank you for calling {clinic_name}. How may I assist you with your appointment today?",
    voices: [
      "gemini-aoede",
      "gemini-kore",
      "gemini-puck",
      "gemini-charon",
      "priya",
      "naveen",
      "meena",
    ],
  },
];

export const GLOBAL_LANGUAGES: LanguageOption[] = [
  {
    id: "en",
    name: "English (US)",
    nativeName: "English",
    flag: "🇺🇸",
    region: "global",
    category: "United States",
    defaultPhrase:
      "Hello! Thank you for calling {clinic_name}. How may I assist you today?",
    voices: ["gemini-kore", "gemini-puck", "gemini-charon", "gemini-aoede"],
  },
  {
    id: "es",
    name: "Spanish",
    nativeName: "Español",
    flag: "🇪🇸",
    region: "global",
    category: "Spain & Americas",
    defaultPhrase:
      "¡Hola! Gracias por llamar a {clinic_name}. ¿En qué podemos ayudarle hoy?",
    voices: ["gemini-aoede", "gemini-kore"],
  },
  {
    id: "en_uk",
    name: "English (UK)",
    nativeName: "English (UK)",
    flag: "🇬🇧",
    region: "global",
    category: "United Kingdom",
    defaultPhrase:
      "Good day, thank you for calling {clinic_name}. How may I assist you today?",
    voices: ["gemini-charon", "gemini-aoede"],
  },
];

export function getScopedLanguagesForCountry(
  countryCode: string,
): LanguageOption[] {
  if (!countryCode || countryCode.toUpperCase() === "IN") {
    return INDIAN_LANGUAGES;
  }
  return GLOBAL_LANGUAGES;
}

export const ALL_AUDITION_LANGUAGES: LanguageOption[] = [
  ...INDIAN_LANGUAGES,
  ...GLOBAL_LANGUAGES,
];

export const LANGUAGE_MODES: LanguageMode[] = [
  {
    id: "indian_multilingual",
    label: "Smart Multilingual (Auto-Detect)",
    desc: "Seamlessly detects and speaks in Kannada, Hindi, Telugu, Tamil, Malayalam, or English as the patient speaks",
  },
  {
    id: "en_hi_bilingual",
    label: "English + Hindi (Urban Metro)",
    desc: "Fluent bilingual dialogue for metro clinics and North/Central Indian cities",
  },
  {
    id: "regional_primary",
    label: "Regional Vernacular First",
    desc: "Prioritizes the state's vernacular language (e.g. Kannada in Bengaluru, Telugu in Hyderabad) with English fallback",
  },
  {
    id: "en_only",
    label: "English Only",
    desc: "Strictly converses in clear Indian Metro English",
  },
];

export const SLOT_DURATIONS = [
  { value: "10", label: "10 Minutes (Rapid Checkup)" },
  { value: "15", label: "15 Minutes (Standard OPD)" },
  { value: "20", label: "20 Minutes (In-depth Ped)" },
  { value: "30", label: "30 Minutes (Detailed Consult)" },
  { value: "45", label: "45 Minutes (Specialty)" },
];

export const BUFFER_OPTIONS = [
  { value: "0", label: "0 Minutes (Back-to-back)" },
  { value: "5", label: "5 Minutes (Recommended)" },
  { value: "10", label: "10 Minutes (Relaxed buffer)" },
];

export const MAX_PATIENT_OPTIONS = [
  { value: "20", label: "20 Patients / Day" },
  { value: "25", label: "25 Patients / Day" },
  { value: "30", label: "30 Patients / Day (Default)" },
  { value: "40", label: "40 Patients / Day" },
  { value: "999", label: "Unlimited Bookings" },
];

export const DEFAULT_CLINIC_PROFILE: ClinicProfile = {
  clinicName: "",
  doctorName: "",
  doctorEmail: "",
  doctorPhone: "",
  registrationNumber: "",
  clinicAddress: "",
  city: "",
  timezone: "UTC",
  specialty: "",
  consultationFee: "",
  emergencyPhone: "",
  defaultGreetingPrompt: "",
};

export const GREETING_LANGUAGES: GreetingLanguage[] = [
  {
    id: "en",
    name: "English",
    nativeName: "English",
    flag: "🇮🇳",
    template:
      "Hello! Thank you for calling {clinic_name}. How may I assist you with your appointment today?",
    friendlyTemplate:
      "Hello! Welcome to {clinic_name}. How may I help you today?",
    conciseTemplate:
      "Good day, thank you for calling {clinic_name}. How can I assist you today?",
  },
  {
    id: "hi",
    name: "Hindi",
    nativeName: "हिन्दी",
    flag: "🇮🇳",
    template:
      "Namaste! {clinic_name} mein aapka swagat hai. Main aapki kya madad kar sakti hoon?",
    scriptTemplate:
      "नमस्ते, {clinic_name} में आपका स्वागत है। मैं आपकी क्या सहायता कर सकती हूँ?",
    conciseTemplate:
      "Namaste! {clinic_name} mein swagat hai. Appointment ke liye main aapki kya madad kar sakti hoon?",
  },
  {
    id: "kn",
    name: "Kannada",
    nativeName: "ಕನ್ನಡ",
    flag: "🇮🇳",
    template:
      "Namaskara! {clinic_name}-ge suswagatha. Naanu nimage hege sahaya madabahudu?",
    scriptTemplate:
      "ನಮಸ್ಕಾರ, {clinic_name} ಗೆ ಸುಸ್ವಾಗತ. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
    conciseTemplate:
      "Namaskara! {clinic_name}-ge suswagatha. Appointment booking-ge naanu nimage hege sahaya madabahudu?",
  },
  {
    id: "te",
    name: "Telugu",
    nativeName: "తెలుగు",
    flag: "🇮🇳",
    template:
      "Namaskaram! {clinic_name} ki swagatham. Nenu meeku ela sahaya padagalanu?",
    scriptTemplate:
      "నమస్కారం, {clinic_name} కి స్వాగతం. నేను మీకు ఎలా సహాయపడగలను?",
    conciseTemplate:
      "Namaskaram! {clinic_name} ki swagatham. Appointment kosam nenu meeku ela sahaya padagalanu?",
  },
  {
    id: "ta",
    name: "Tamil",
    nativeName: "தமிழ்",
    flag: "🇮🇳",
    template:
      "Vanakkam! {clinic_name}-ukku ungalai anbudan varaverkirom. Ungalukku enna udhavi thevai?",
    scriptTemplate:
      "வணக்கம், {clinic_name}-க்கு உங்களை வரவேற்கிறோம். உங்களுக்கு என்ன உதவி வேண்டும்?",
    conciseTemplate:
      "Vanakkam! {clinic_name}-ukku varaverkirom. Appointment-ukku ungalukku enna udhavi thevai?",
  },
  {
    id: "mr",
    name: "Marathi",
    nativeName: "मराठी",
    flag: "🇮🇳",
    template:
      "Namaskar! {clinic_name} madhe aple swagat ahe. Me aplyala kashi madat karu shakto?",
    scriptTemplate:
      "नमस्कार, {clinic_name} मध्ये आपले स्वागत आहे. मी आपल्याला कशी मदत करू शकतो?",
    conciseTemplate:
      "Namaskar! {clinic_name} madhe aple swagat ahe. Appointment sathi me aplyala kashi madat karu shakto?",
  },
  {
    id: "bn",
    name: "Bengali",
    nativeName: "বাংলা",
    flag: "🇮🇳",
    template:
      "Nomoshkar! {clinic_name}-e apnake shagotom. Ami apnake kibhabe sahajjo korte pari?",
    scriptTemplate:
      "নমস্কার, {clinic_name}-এ আপনাকে স্বাগতম। আমি আপনাকে কীভাবে সাহায্য করতে পারি?",
    conciseTemplate:
      "Nomoshkar! {clinic_name}-e shagotom. Appointment-er jonno ami apnake kibhabe sahajjo korte pari?",
  },
  {
    id: "gu",
    name: "Gujarati",
    nativeName: "ગુજરાતી",
    flag: "🇮🇳",
    template:
      "Namaste! {clinic_name} ma aapnu swagat chhe. Hu tamne kevi rite madad kari shaku?",
    scriptTemplate:
      "નમસ્તે, {clinic_name} માં આપનું સ્વાગત છે. હું તમને કેવી રીતે મદદ કરી શકું?",
    conciseTemplate:
      "Namaste! {clinic_name} ma swagat chhe. Appointment mate hu tamne kevi rite madad kari shaku?",
  },
];

export function detectLanguageFromText(
  text: string,
): "en" | "hi" | "kn" | "te" | "ta" | "mr" | "bn" | "gu" {
  const lower = (text || "").toLowerCase();
  if (
    lower.includes("namaskara") ||
    lower.includes("suswagatha") ||
    /[\u0C80-\u0CFF]/.test(lower)
  ) {
    return "kn";
  }
  if (
    lower.includes("vanakkam") ||
    lower.includes("varaverkirom") ||
    /[\u0B80-\u0BFF]/.test(lower)
  ) {
    return "ta";
  }
  if (
    lower.includes("namaskaram") ||
    lower.includes("swagatham") ||
    /[\u0C00-\u0C7F]/.test(lower)
  ) {
    return "te";
  }
  if (
    lower.includes("nomoshkar") ||
    lower.includes("shagotom") ||
    /[\u0980-\u09FF]/.test(lower)
  ) {
    return "bn";
  }
  if (
    lower.includes("kevi rite") ||
    lower.includes("aapnu swagat") ||
    /[\u0A80-\u0AFF]/.test(lower)
  ) {
    return "gu";
  }
  if (
    lower.includes("namaskar") ||
    lower.includes("aple swagat") ||
    lower.includes("madat karu shakto")
  ) {
    return "mr";
  }
  if (
    lower.includes("namaste") ||
    lower.includes("swagat") ||
    lower.includes("madad") ||
    /[\u0900-\u097F]/.test(lower)
  ) {
    return "hi";
  }
  return "en";
}
