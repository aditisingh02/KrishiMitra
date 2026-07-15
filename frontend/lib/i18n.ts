// Languages supported across the app (must match backend app/core/languages.py)
export const LANGS: { code: string; native: string; label: string }[] = [
  { code: "en", native: "English", label: "English" },
  { code: "hi", native: "हिंदी", label: "Hindi" },
  { code: "pa", native: "ਪੰਜਾਬੀ", label: "Punjabi" },
  { code: "mr", native: "मराठी", label: "Marathi" },
  { code: "ta", native: "தமிழ்", label: "Tamil" },
  { code: "te", native: "తెలుగు", label: "Telugu" },
  { code: "bn", native: "বাংলা", label: "Bengali" },
  { code: "gu", native: "ગુજરાતી", label: "Gujarati" },
];

const KEY = "km_lang";

export function getStoredLang(): string {
  if (typeof window === "undefined") return "en";
  return localStorage.getItem(KEY) || "en";
}
export function setStoredLang(code: string) {
  if (typeof window !== "undefined") {
    localStorage.setItem(KEY, code);
    // let the runtime-i18n provider react without a full page reload (landing page)
    window.dispatchEvent(new CustomEvent("krishi-lang", { detail: code }));
  }
}

export type LandingCopy = {
  eyebrow: string;
  title: string;
  accent: string;
  sub: string;
  start: string;
  signin: string;
  getstarted: string;
  open: string;
  opendash: string;
  talk: string;
};

// Localized landing-hero copy. Falls back to English for any missing key.
export const LANDING: Record<string, LandingCopy> = {
  en: {
    eyebrow: "AI agronomist · natural farming",
    title: "An AI agronomist that runs your farm -",
    accent: "not just answers questions.",
    sub: "KrishiMitra knows your crops, soil, weather, disease history and mandi prices, and tells each farmer what to do next - in their own language, by voice.",
    start: "Start your farm",
    signin: "Sign in",
    getstarted: "Get started",
    open: "Open the farm",
    opendash: "Open the dashboard",
    talk: "Talk to KrishiMitra",
  },
  hi: {
    eyebrow: "एआई कृषि सलाहकार · प्राकृतिक खेती",
    title: "एक एआई कृषि विशेषज्ञ जो आपका खेत चलाता है -",
    accent: "सिर्फ़ सवालों के जवाब नहीं देता।",
    sub: "कृषिमित्र आपकी फ़सल, मिट्टी, मौसम, बीमारी का इतिहास और मंडी भाव जानता है, और हर किसान को उसकी अपनी भाषा में, आवाज़ से बताता है कि आगे क्या करना है।",
    start: "अपना खेत शुरू करें",
    signin: "साइन इन करें",
    getstarted: "शुरू करें",
    open: "खेत खोलें",
    opendash: "डैशबोर्ड खोलें",
    talk: "कृषिमित्र से बात करें",
  },
  pa: {
    eyebrow: "ਏਆਈ ਖੇਤੀ ਸਲਾਹਕਾਰ · ਕੁਦਰਤੀ ਖੇਤੀ",
    title: "ਇੱਕ ਏਆਈ ਖੇਤੀ ਮਾਹਰ ਜੋ ਤੁਹਾਡਾ ਖੇਤ ਚਲਾਉਂਦਾ ਹੈ -",
    accent: "ਸਿਰਫ਼ ਸਵਾਲਾਂ ਦੇ ਜਵਾਬ ਨਹੀਂ ਦਿੰਦਾ।",
    sub: "ਕ੍ਰਿਸ਼ੀਮਿੱਤਰ ਤੁਹਾਡੀਆਂ ਫ਼ਸਲਾਂ, ਮਿੱਟੀ, ਮੌਸਮ, ਬਿਮਾਰੀ ਦਾ ਇਤਿਹਾਸ ਅਤੇ ਮੰਡੀ ਭਾਅ ਜਾਣਦਾ ਹੈ, ਅਤੇ ਹਰ ਕਿਸਾਨ ਨੂੰ ਉਸ ਦੀ ਆਪਣੀ ਭਾਸ਼ਾ ਵਿੱਚ ਦੱਸਦਾ ਹੈ ਕਿ ਅੱਗੇ ਕੀ ਕਰਨਾ ਹੈ।",
    start: "ਆਪਣਾ ਖੇਤ ਸ਼ੁਰੂ ਕਰੋ",
    signin: "ਸਾਈਨ ਇਨ ਕਰੋ",
    getstarted: "ਸ਼ੁਰੂ ਕਰੋ",
    open: "ਖੇਤ ਖੋਲ੍ਹੋ",
    opendash: "ਡੈਸ਼ਬੋਰਡ ਖੋਲ੍ਹੋ",
    talk: "ਕ੍ਰਿਸ਼ੀਮਿੱਤਰ ਨਾਲ ਗੱਲ ਕਰੋ",
  },
  mr: {
    eyebrow: "एआय कृषी सल्लागार · नैसर्गिक शेती",
    title: "तुमचं शेत चालवणारा एआय कृषीतज्ज्ञ -",
    accent: "फक्त प्रश्नांची उत्तरं देत नाही.",
    sub: "कृषीमित्र तुमची पिकं, माती, हवामान, रोगांचा इतिहास आणि बाजारभाव जाणतो, आणि प्रत्येक शेतकऱ्याला त्याच्या भाषेत सांगतो की पुढे काय करायचं.",
    start: "तुमचं शेत सुरू करा",
    signin: "साइन इन करा",
    getstarted: "सुरू करा",
    open: "शेत उघडा",
    opendash: "डॅशबोर्ड उघडा",
    talk: "कृषीमित्रशी बोला",
  },
  ta: {
    eyebrow: "AI வேளாண் ஆலோசகர் · இயற்கை விவசாயம்",
    title: "உங்கள் பண்ணையை நடத்தும் AI வேளாண் நிபுணர் -",
    accent: "கேள்விகளுக்கு பதில் சொல்வது மட்டுமல்ல.",
    sub: "கிருஷிமித்ரா உங்கள் பயிர்கள், மண், வானிலை, நோய் வரலாறு மற்றும் சந்தை விலைகளை அறிந்து, ஒவ்வொரு விவசாயிக்கும் அவரவர் மொழியில் அடுத்து என்ன செய்வது என்று சொல்கிறது.",
    start: "உங்கள் பண்ணையைத் தொடங்குங்கள்",
    signin: "உள்நுழைக",
    getstarted: "தொடங்குங்கள்",
    open: "பண்ணையைத் திற",
    opendash: "டாஷ்போர்டைத் திற",
    talk: "கிருஷிமித்ராவுடன் பேசுங்கள்",
  },
  te: {
    eyebrow: "AI వ్యవసాయ సలహాదారు · సహజ వ్యవసాయం",
    title: "మీ పొలాన్ని నడిపే AI వ్యవసాయ నిపుణుడు -",
    accent: "కేవలం ప్రశ్నలకు సమాధానం ఇవ్వడం కాదు.",
    sub: "కృషిమిత్ర మీ పంటలు, నేల, వాతావరణం, వ్యాధి చరిత్ర మరియు మార్కెట్ ధరలను తెలుసుకొని, ప్రతి రైతుకు వారి భాషలో తదుపరి ఏం చేయాలో చెబుతుంది.",
    start: "మీ పొలాన్ని ప్రారంభించండి",
    signin: "సైన్ ఇన్",
    getstarted: "ప్రారంభించండి",
    open: "పొలాన్ని తెరవండి",
    opendash: "డాష్‌బోర్డ్ తెరవండి",
    talk: "కృషిమిత్రతో మాట్లాడండి",
  },
  bn: {
    eyebrow: "এআই কৃষি পরামর্শদাতা · প্রাকৃতিক চাষ",
    title: "আপনার খামার চালায় এমন একজন এআই কৃষি বিশেষজ্ঞ -",
    accent: "শুধু প্রশ্নের উত্তর দেয় না।",
    sub: "কৃষিমিত্র আপনার ফসল, মাটি, আবহাওয়া, রোগের ইতিহাস ও বাজারদর জানে, এবং প্রতিটি কৃষককে তার নিজের ভাষায় বলে পরবর্তী কী করতে হবে।",
    start: "আপনার খামার শুরু করুন",
    signin: "সাইন ইন",
    getstarted: "শুরু করুন",
    open: "খামার খুলুন",
    opendash: "ড্যাশবোর্ড খুলুন",
    talk: "কৃষিমিত্রের সাথে কথা বলুন",
  },
  gu: {
    eyebrow: "એઆઈ કૃષિ સલાહકાર · પ્રાકૃતિક ખેતી",
    title: "તમારું ખેતર ચલાવતો એઆઈ કૃષિ નિષ્ણાત -",
    accent: "ફક્ત પ્રશ્નોના જવાબ આપતો નથી.",
    sub: "કૃષિમિત્ર તમારા પાક, માટી, હવામાન, રોગનો ઇતિહાસ અને બજારભાવ જાણે છે, અને દરેક ખેડૂતને તેની પોતાની ભાષામાં કહે છે કે આગળ શું કરવું.",
    start: "તમારું ખેતર શરૂ કરો",
    signin: "સાઇન ઇન",
    getstarted: "શરૂ કરો",
    open: "ખેતર ખોલો",
    opendash: "ડેશબોર્ડ ખોલો",
    talk: "કૃષિમિત્ર સાથે વાત કરો",
  },
};

export function landingCopy(code: string): LandingCopy {
  return LANDING[code] || LANDING.en;
}
