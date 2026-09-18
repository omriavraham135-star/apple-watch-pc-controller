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

    # 1. ABSOLUTE PATTERNS with "ל-" or "על":
    # e.g., "תנמיך ל-50", "תגביר ל-80%", "שים על 40", "כוון ל 30", "ווליום ל-50"
    absolute_regex = re.compile(
        r'(?:ל-|ל\s+|על\s+|בדיוק\s+)(\d+|' + '|'.join(HEBREW_WORDS_TO_NUMBERS.keys()) + r')'
    )
    is_explicitly_absolute = bool(absolute_regex.search(cleaned))

    # 2. RELATIVE PATTERNS with "ב-":
    # e.g., "תנמיך ב-50%", "תגביר ב 20 אחוז", "תרד ב-15"
    relative_regex = re.compile(
        r'(?:ב-|ב\s+)(\d+|' + '|'.join(HEBREW_WORDS_TO_NUMBERS.keys()) + r')'
    )
    is_explicitly_relative = bool(relative_regex.search(cleaned))

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

        # If neither "ב-" nor "ל-" was said explicitly, but a direction verb + number:
        # e.g. "תנמיך 20 אחוז" vs "שים 50 אחוז"
        if any(w in cleaned for w in ["שים", "קבע", "ווליום"]):
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
