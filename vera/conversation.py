"""Bounded state-machine intent and useful, honest follow-through."""
import re
from datetime import datetime
from .evidence import Book, text, percent, suspicious
from .language import language, choose
from .policy import active_offer_indices
from .strategies import find_digest, read_path, slot_options
from .timeutil import date_text


def normalize(message: str) -> str:
    return " ".join(message.casefold().replace("’", "'").split())


def classify(message: str) -> str:
    s = normalize(message)
    # Explicit opt-out is not the word 'stop' embedded in 'can I stop by?'.
    if not re.search(r"(?:don't|do not|never)\s+(?:want to\s+)?(?:stop|unsubscribe)|not asking you to stop", s):
        if re.fullmatch(r"(?:please\s+)?(?:stop|unsubscribe|opt out|band karo|बंद करो|रोकें)[.!\s]*", s) or re.search(r"stop (?:messaging|texting|contacting|spamming|sending)|(?:don't|do not) (?:message|text|contact|send)|remove (?:me|my (?:number|contact))|delete my (?:number|contact)|leave me alone|message(?:s)? mat bhej|संदेश (?:मत भेज|बंद)", s):
            return "opt_out"
    if suspicious(s):
        return "injection"
    if re.search(r"thank(?:s| you) for (?:contacting|reaching)|we(?:'re| are) (?:currently )?(?:closed|unavailable)|(?:our team|we) will (?:respond|get back)|this is an (?:auto|automated)|automatic reply|business hours.*reply", s):
        return "auto_reply"
    if re.search(r"not now|later|tomorrow|busy|after (?:\d+|an? |half)|in \d+ (?:min|hour)|baad mein|बाद में|कल", s):
        return "delay"
    if re.search(r"not interested|no thanks|no thank you|don't want|do not want|nahi chahiye|नहीं चाहिए|rather not", s) or re.fullmatch(r"no[.!\s]*", s):
        return "decline"
    if re.search(r"you(?:'re| are) (?:useless|stupid)|useless spam|bullshit|fuck|idiot", s):
        return "hostile"
    if re.search(r"\b(?:price|cost|charge|pricing|amount|kitne|kitna)\b|दाम|कीमत", s):
        return "price"
    if re.search(r"\b(?:source|citation|abstract|study|proof|evidence|research|summary)\b|कहाँ से", s):
        return "source"
    if re.search(r"\b(?:book|appointment|slot|schedule|available|reschedule)\b|समय|बुक", s):
        return "schedule"
    if re.search(r"\b(?:views|ctr|calls|performance|numbers|metrics)\b|आंकड़े", s):
        return "metrics"
    if re.search(r"\b(?:expensive|budget|too much|costly)\b|महंगा", s):
        return "objection"
    if re.search(r"(?:file|filing) (?:my |our )?gst|income tax|\b(?:politics|election|weather forecast|cricket score|tell me a joke)\b", s):
        return "offtopic"
    if re.search(r"(?:^|\b)(?:yes|yep|yeah|sure|go ahead|let's do|lets do|do it|send it|send me|draft it|sounds good|i want to join|please proceed|haan|hanji)(?:\b|$)|हाँ|ठीक है", s):
        return "commit"
    if re.fullmatch(r"(?:ok(?:ay)?|great|done|thanks|thank you)[.!\s]*", s):
        return "ack"
    return "unknown"


def delay_seconds(message: str) -> int:
    s = normalize(message)
    match = re.search(r"(\d+)\s*(min(?:ute)?s?|h(?:ou)?rs?|hours?)", s)
    if match:
        return min(7 * 86400, max(60, int(match[1]) * (3600 if match[2].startswith("h") else 60)))
    if "tomorrow" in s or "कल" in s:
        return 86400
    if "half" in s:
        return 1800
    return 1800


def execute(book: Book, pending: dict, now: datetime, *, question: str = "") -> str:
    """All outputs are drafts/instructions. There are no hidden external tools."""
    lang = language(book)
    m, c = book.roots["merchant"], book.roots.get("customer", {})
    customer = bool(c)
    brand = book.string("merchant", "identity.name", "the business", 120)
    kind = pending.get("kind", "plan")
    title = ""
    offers = active_offer_indices(m, now, customer=c if customer else None)
    if pending.get("offer_id") and kind in {"offer_draft", "price"}:
        offers = [i for i in offers if m["offers"][i].get("id") == pending["offer_id"]]
    if offers:
        title = book.string("merchant", f"offers.{offers[0]}.title", limit=220)
    if kind in {"recall_request", "return_request", "refill_request", "schedule"}:
        slots = slot_options(book, now)
        what = "refill availability" if kind == "refill_request" else "an appointment" if kind != "return_request" else "a return visit"
        chosen_slot = ""
        for slot in slots:
            # Only echo a listed option if message references its exact rendered date/time.
            if slot.lower() in question.lower():
                chosen_slot = slot
        if chosen_slot:
            draft = f"Hello {brand}, I'd like to enquire about {what} on {chosen_slot}. Please confirm availability."
        else:
            draft = f"Hello {brand}, I'd like to enquire about {what}. Please confirm availability and the next step."
        lead = choose(lang, f'Here is the enquiry draft: “{draft}”', f'Enquiry draft ready hai: “{draft}”', f'पूछताछ का मसौदा: “नमस्ते {brand}, कृपया अगली मुलाकात या रिफिल की उपलब्धता और अगला कदम बताएं।”')
        tail = choose(lang, " This has not been sent, booked or dispensed; share it with the business for confirmation.", " Yeh send, book ya dispense nahi hua hai; confirmation ke liye business ko bhejein.", " इसे भेजा नहीं गया है, बुकिंग नहीं हुई है और दवा नहीं दी गई है। पुष्टि के लिए इसे व्यवसाय को भेजें।")
        return lead + tail
    if kind == "offer_draft":
        if title:
            return choose(lang,
                f'Here is your draft: “{brand}: {title}. Contact our team to check eligibility and availability.” Nothing has been published or sent.',
                f'Draft ready hai: “{brand}: {title}. Eligibility aur availability hamari team se confirm karein.” Abhi kuch publish ya send nahi hua hai.',
                f'मसौदा तैयार है: “{brand}: {title}। पात्रता और उपलब्धता हमारी टीम से पक्की करें।” इसे अभी प्रकाशित या भेजा नहीं गया है।')
        return choose(lang,
            f'The latest context has no valid approved offer for this draft. Here is a price-free draft instead: “Explore services at {brand}. Contact the team for current options and availability.”',
            f'Latest context mein valid approved offer nahi hai. Price-free draft: “{brand} ki current services aur availability ke liye team se sampark karein.”',
            f'नए रिकॉर्ड में कोई मान्य स्वीकृत ऑफ़र नहीं है। बिना दाम का मसौदा: “{brand} की वर्तमान सेवाओं और उपलब्धता के लिए टीम से संपर्क करें।”')
    if kind in {"review_reply", "review_general"}:
        theme = pending.get("theme", "")
        if theme == "delivery_late":
            draft = "Sorry for the delay. Please share your order ID privately with our team so they can check its status and update you."
        else:
            draft = "Thank you for flagging this. Please share the visit details privately with our team so they can look into what happened."
        return choose(lang, f'Here is a reply draft: “{draft}” It acknowledges the issue without inventing a refund, delivery time or completed investigation.', f'Reply draft: “{draft}” Isme refund, delivery time ya completed investigation ka jhootha claim nahi hai.', f'जवाब का मसौदा: “यह बात बताने के लिए धन्यवाद। कृपया ऑर्डर या विज़िट का विवरण हमारी टीम को निजी तौर पर दें, ताकि वे स्थिति जाँच सकें।” इसमें रिफंड या तय समय का वादा नहीं है।')
    if kind in {"research_summary", "source", "checklist"}:
        path, item = find_digest(book)
        wanted = pending.get("digest_id")
        if wanted and item and item.get("id") != wanted:
            item = None
        if not item or not path:
            return choose(lang, "The latest supplied context does not contain that source. I won't invent the abstract or a link. Please use the original notice for verification.", "Latest context mein woh source nahi hai; abstract ya link invent nahi karunga. Original notice se verify karein.", "नए रिकॉर्ड में वह स्रोत नहीं है। सार या लिंक बनाकर नहीं दूँगा; मूल सूचना से पुष्टि करें।")
        source = read_path(book, path, "source", limit=180)
        title = read_path(book, path, "title", limit=300)
        if kind == "checklist":
            return f"Checklist for the supplied notice from {source}: verify the original notice and effective date; compare the affected equipment, products or batches with your records; have the responsible professional approve any change and document it. I have not inspected your inventory or identified affected customers."
        summary = read_path(book, path, "summary", limit=800)
        # Do not turn synthetic healthcare claims into patient advice.
        clinical = book.roots["category"].get("slug") in {"dentists", "pharmacies"} or pending.get("sensitive")
        if clinical:
            summary = title
        return f"Supplied source: {source}. Summary: {summary or title} This is a summary of the provided material, not independent verification or a complete abstract. Verify the original before applying it; no treatment or dispensing change has been made."
    if kind == "performance_audit" or kind == "metrics":
        window = book.number("merchant", "performance.window_days")
        calls = book.number("merchant", "performance.calls")
        views = book.number("merchant", "performance.views")
        ctr = book.number("merchant", "performance.ctr")
        bits = []
        if views is not None: bits.append(f"{views:g} views")
        if calls is not None: bits.append(f"{calls:g} calls")
        if ctr is not None: bits.append(f"{percent(ctr)} click-through rate")
        snapshot = ", ".join(bits) or "no complete performance figures supplied"
        label = f"{window:g}-day snapshot" if window is not None else "latest snapshot"
        return choose(lang,
            f"Here is the check plan using your {label}: {snapshot}. Verify opening hours and contact details; inspect the latest photos and offer terms; compare the next equivalent reporting window. These are checks to perform, not diagnosed causes or promised uplift.",
            f"Aapke {label} par check plan: {snapshot}. Opening hours, contact details, latest photos aur offer terms verify karein; phir equivalent reporting window compare karein. Yeh checks hain, proven causes ya guaranteed uplift nahi.",
            f"आपके {label} पर जाँच योजना: {snapshot}। खुलने का समय, संपर्क विवरण, नई तस्वीरें और ऑफ़र की शर्तें जाँचें; फिर समान रिपोर्टिंग अवधि से तुलना करें। ये जाँच के कदम हैं, सिद्ध कारण या बढ़ोतरी की गारंटी नहीं।")
    if kind == "price":
        if title:
            return f"The latest valid merchant offer is {title}. I have no confirmed quote for a different service or bundle, and haven't processed any payment."
        return "No currently valid merchant-approved price is supplied. I won't substitute a category example or another merchant's price. A quote must come from the business."
    if kind == "verification_checklist":
        return "Verification checklist: confirm the business name, address and phone match your records; open your own Google Business Profile management screen; follow the verification method offered there. I cannot verify the listing for you or promise a visibility increase."
    if kind == "stock_checklist":
        return "Stock-review checklist: compare the supplied demand signal with your actual stock and recent sales; ask the pharmacist to check expiry dates and storage requirements; only then approve replenishment. No stock quantity, medicine substitution or order has been assumed."
    if kind == "renewal_plan":
        return "Renewal checklist: confirm the current plan, expiry date and official quote in your merchant account; review the terms; complete payment only through your usual authorized channel. I have not renewed the plan or created a payment link."
    if kind == "review_request":
        return f'Here is a review-request draft: “Thank you for visiting {brand}. An honest review of your experience helps our team improve.” Ask without incentives or a request for a particular rating; no review has been posted.'
    topic = text(pending.get("topic", "your next campaign"), 120).replace("_", " ")
    lead = f"Here is a draft plan for {topic}: define the audience; confirm capacity and schedule; review the message before publishing."
    if title:
        lead += f" Use only this approved offer: {title}."
    else:
        lead += " No approved price is supplied, so leave pricing out until confirmed."
    return lead + " Nothing has been published, booked or sent."
