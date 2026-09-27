"""English and Hindi/Hinglish controlled realization; regional fallback is explicit."""
import re
from .evidence import Book, text


def language(book: Book) -> str:
    pref = book.string("customer", "identity.language_pref").lower()
    if not pref:
        pref = book.string("merchant", "identity.language_pref").lower()
    if not pref:
        langs = book.get("merchant", "identity.languages", ["en"])
        pref = str(langs[0]).lower() if isinstance(langs, list) and langs else "en"
    if pref in {"hi", "hindi"}:
        return "hi"
    if pref.startswith("hi-") or pref in {"hinglish", "hindi-english"}:
        return "hi-en"
    return "en"


def salutation(book: Book, customer: bool = False) -> str:
    if customer:
        name = book.string("customer", "identity.name", "Hello", 100)
        parent = re.search(r"parent:\s*([^)]*)", name, re.I)
        if parent:
            name = parent.group(1).strip()
        channel = book.string("customer", "preferences.channel")
        if channel == "whatsapp_via_son" and not parent:
            return f"{name} के परिवार को नमस्ते" if language(book) == "hi" else f"Hello, {name}'s family"
        return name
    name = book.string("merchant", "identity.owner_first_name", limit=80)
    if not name:
        return book.string("merchant", "identity.name", "Hello", 100)
    category = book.string("category", "slug") or book.string("merchant", "category_slug")
    return f"Dr. {name}" if category == "dentists" and not name.lower().startswith("dr") else name


def choose(lang: str, en: str, mix: str = "", hi: str = "") -> str:
    return hi if lang == "hi" and hi else mix if lang in {"hi", "hi-en"} and mix else en


def service_name(value: str) -> str:
    return text(value.replace("_", " "), 100)


ASKS = {
    "offer_draft": ("Want a ready-to-use draft built around it?", "Iske liye ready-to-use draft bana doon?", "क्या इसके लिए एक संदेश का मसौदा बनाऊँ?"),
    "review_reply": ("Want a delivery-status reply your team can use?", "Team ke liye delivery-status reply bana doon?", "क्या आपकी टीम के लिए डिलीवरी-स्थिति का जवाब लिखूँ?"),
    "review_general": ("Want a calm reply addressing that feedback?", "Is feedback ke liye clear reply bana doon?", "क्या इस प्रतिक्रिया का शांत और स्पष्ट जवाब लिखूँ?"),
    "research_summary": ("Want the supplied summary and its limitations?", "Summary aur uski limitations bhejoon?", "क्या दी गई जानकारी का सार और उसकी सीमाएँ बताऊँ?"),
    "checklist": ("Want a short verification checklist?", "Chhoti verification checklist bana doon?", "क्या एक छोटी जाँच-सूची बनाऊँ?"),
    "performance_audit": ("Want a focused listing-check plan before changing prices?", "Prices badalne se pehle listing-check plan bana doon?", "दाम बदलने से पहले क्या लिस्टिंग की जाँच का प्लान बनाऊँ?"),
    "plan": ("Want a draft plan to review?", "Review ke liye draft plan bana doon?", "क्या समीक्षा के लिए एक प्रारूप बनाऊँ?"),
    "refill_request": ("Reply YES for a refill enquiry draft, or STOP to opt out.", "Refill enquiry draft ke liye YES, messages band karne ke liye STOP.", "रिफिल पूछताछ का मसौदा पाने के लिए YES, संदेश बंद करने के लिए STOP लिखें।"),
    "recall_request": ("Reply YES for an appointment-enquiry draft, or STOP to opt out.", "Appointment enquiry draft ke liye YES, messages band karne ke liye STOP.", "अपॉइंटमेंट पूछताछ का मसौदा पाने के लिए YES, संदेश बंद करने के लिए STOP लिखें।"),
    "return_request": ("Reply YES for a return-visit enquiry draft, or STOP to opt out.", "Return visit enquiry draft ke liye YES, messages band karne ke liye STOP.", "वापसी की विज़िट की पूछताछ के लिए YES, संदेश बंद करने के लिए STOP लिखें।"),
}


def ask(kind: str, lang: str) -> str:
    return choose(lang, *ASKS[kind])
