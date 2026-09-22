import re
from typing import Optional, Dict, Any

HEBREW_WORDS_TO_NUMBERS = {
    "אפס": 0,
    "חמש": 5,
    "עשר": 10,
    "עשרה": 10,
    "חמש עשרה": 15,
    "חמישה עשר": 15,
    "עשרים": 20,
    "עשרים וחמש": 25,
    "שלושים": 30,
    "ארבעים": 40,
    "חמישים": 50,
    "שישים": 60,
    "שבעים": 70,
    "שמונים": 80,
    "תשעים": 90,
    "מאה": 100,
    "חצי": 50,
}

# Longest first, so "עשרים וחמש" is matched before "עשרים".
_NUMBER_WORDS = "|".join(sorted(HEBREW_WORDS_TO_NUMBERS, key=len, reverse=True))
_VALUE = r"(\d+|" + _NUMBER_WORDS + r")"

# Hebrew attaches its prepositions to the following word, and dictation keeps
# them attached: "לשמונים", "בחמישים". Requiring a hyphen or a space after the
# prefix missed every dictated command, so the separator is optional.
_ABSOLUTE = re.compile(r"(?:ל[-\s]?|על\s+|בדיוק\s+)" + _VALUE)
_RELATIVE = re.compile(r"(?:ב[-\s]?)" + _VALUE)

#: Words that mean "set it to", as whole words.
_SET_VERBS = {"שים", "קבע", "ווליום"}


def _words(text: str) -> set:
    """Whole words, so a verb cannot be found hiding inside a longer word."""
    return set(re.findall(r"\w+", text))


def _extract_number(text: str) -> Optional[int]:
    """Finds either digits (e.g. '50') or Hebrew number words (e.g. 'חמישים')."""
    # Check digits first
    match = re.search(r'\b(\d+)\b', text)
    if match:
        return int(match.group(1))

    # Check Hebrew number words
    for word, num in sorted(HEBREW_WORDS_TO_NUMBERS.items(), key=lambda x: -len(x[0])):
        if word in text:
            return num

    return None

def parse_voice_command(text: str) -> Dict[str, Any]:
    """
    Parses natural language Hebrew voice commands and determines intent:
    - Relative decrease (e.g., 'תנמיך ב-50 אחוז') -> intent: change_relative, delta: -50
    - Relative increase (e.g., 'תגביר ב-20 אחוז') -> intent: change_relative, delta: +20
    - Absolute set (e.g., 'תנמיך ל-50 אחוז', 'תגביר ל-80 אחוז', 'שים על 60') -> intent: set_absolute, target: X
    - Mute / Unmute
    """
    cleaned = text.strip().lower()
    
    # Check mute / unmute first
    if any(term in cleaned for term in ["בטל השתקה", "בטל השתק", "תחזיר סאונד", "תחזיר קול", "unmute"]):
        return {
            "intent": "mute",
            "value": False,
            "feedback": "ההשתקה בוטלה"
        }
    if any(term in cleaned for term in ["תשתיק", "השתק", "השתקה", "בלי קול", "שקט", "mute"]):
        return {
            "intent": "mute",
            "value": True,
            "feedback": "המחשב הושתק"
        }

    # Check extreme keywords
    if any(term in cleaned for term in ["עד הסוף", "מקסימום", "ווליום מלא", "100 אחוז"]):
        return {
            "intent": "set_absolute",
            "target": 100,
            "feedback": "ווליום הוגדר למקסימום (100%)"
        }
    if any(term in cleaned for term in ["על חצי", "חצי כוח", "חצי ווליום"]):
        return {
            "intent": "set_absolute",
            "target": 50,
            "feedback": "ווליום הוגדר ל-50%"
        }

    num = _extract_number(cleaned)

    # "ל-50", "ל 50", "לחמישים", "על 40", "בדיוק 30" — a target to reach.
    is_explicitly_absolute = bool(_ABSOLUTE.search(cleaned))

    # "ב-50", "ב 50", "בחמישים" — an amount to move by.
    is_explicitly_relative = bool(_RELATIVE.search(cleaned))

    # Direction: Down or Up?
    is_down = any(w in cleaned for w in ["תנמיך", "להנמיך", "תוריד", "להוריד", "תרד", "לרדת", "יותר חלש", "פחות", "חלש"])
    is_up = any(w in cleaned for w in ["תגביר", "להגביר", "תרים", "להרים", "תעלה", "לעלות", "יותר חזק", "עוד", "חזק"])

    if num is not None:
        # If explicitly relative ("ב-X")
        if is_explicitly_relative:
            delta = -num if is_down else num
            direction_str = "הונמך" if delta < 0 else "הוגבר"
            return {
                "intent": "change_relative",
                "delta": delta,
                "feedback": f"ווליום {direction_str} ב-{num}%"
            }

        # If explicitly absolute ("ל-X" or "על X")
        if is_explicitly_absolute or any(w in cleaned for w in ["שים על", "תכוון ל", "כוון ל", "קבע על"]):
            return {
                "intent": "set_absolute",
                "target": num,
                "feedback": f"ווליום כוון ל-{num}%"
            }

        # Neither preposition was used, so fall back on the verb:
        # "שים 50 אחוז" sets, "תנמיך 20 אחוז" moves.
        #
        # Matched as whole words. A substring test found "שים" inside
        # "חמישים" and turned every relative command naming a Hebrew number
        # into an absolute one.
        if _words(cleaned) & _SET_VERBS:
            return {
                "intent": "set_absolute",
                "target": num,
                "feedback": f"ווליום כוון ל-{num}%"
            }
        elif is_down:
            # Default for "תנמיך 20 אחוז" without prefix is usually relative ("lower by 20%")
            return {
                "intent": "change_relative",
                "delta": -num,
                "feedback": f"ווליום הונמך ב-{num}%"
            }
        elif is_up:
            return {
                "intent": "change_relative",
                "delta": num,
                "feedback": f"ווליום הוגבר ב-{num}%"
            }

    # Default relative bump when no number is given:
    if is_down:
        return {
            "intent": "change_relative",
            "delta": -10,
            "feedback": "ווליום הונמך ב-10%"
        }
    if is_up:
        return {
            "intent": "change_relative",
            "delta": 10,
            "feedback": "ווליום הוגבר ב-10%"
        }

    return {
        "intent": "unknown",
        "raw": text,
        "feedback": "לא הבנתי את הפקודה. נסה למשל: 'תנמיך ב-30 אחוז' או 'תגביר ל-80 אחוז'"
    }
