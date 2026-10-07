"""Recognize explicit device families, avoiding incidental body-diode mentions."""
import re
from app.categories import CATEGORIES


def detect_category(pages):
    text = '\n'.join(pages[:2])
    # Characteristic symbols are stronger than incidental feature descriptions.
    signatures = [('mosfet',r'R\s*DS\s*\(?\s*ON\s*\)?|\bVDS\b'),
                  ('bipolar',r'\bVCEO\b|V\s*\(BR\)\s*CEO'),
                  ('diode',r'\bVRRM\b|IF\s*\(AV\)')]
    found = [(category,match.group()) for category,pattern in signatures
             if (match:=re.search(pattern,text,re.I))]
    if len({category for category,_ in found})==1:
        return dict(category=found[0][0], label=CATEGORIES[found[0][0]]['label'], evidence=found[0][1])
    # Only the opening description is used for words: applications later in a
    # datasheet commonly mention many unrelated component categories.
    opening = (pages[0] if pages else '')[:1800]
    patterns = {
        'mosfet':r'\bMOSFET\b|\bfield.effect transistor\b|полев\w* транзистор',
        'bipolar':r'\bbipolar transistor\b|\b(?:NPN|PNP)\b[^\n]{0,80}\btransistor\b|биполяр\w* транзистор',
        'resistor':r'\bresistors?\b|\bresistor network\b|резистор',
        'capacitor':r'\bcapacitors?\b|конденсатор',
        'inductor':r'\binductors?\b|\bpower chokes?\b|индуктивност',
        'diode':r'\brectifiers?\b|\bdiodes?\b|диод',
        'connector':r'\bconnectors?\b|\bterminal blocks?\b|соединител|разъ[её]м',
        'power':r'\bpower suppl(?:y|ies)\b|\bpower modules?\b|источник\w* питания',
        'ic':r'\bintegrated circuits?\b|\bmicrocontrollers?\b|\boperational amplifiers?\b|\bvoltage regulators?\b|микросхем',
    }
    found=[(category,match.group()) for category,pattern in patterns.items() if (match:=re.search(pattern,opening,re.I))]
    # MOSFET often advertises an internal diode; it remains a transistor.
    if any(category=='mosfet' for category,_ in found):found=[item for item in found if item[0]!='diode']
    if len(found)==1:
        category,evidence=found[0]
        return dict(category=category,label=CATEGORIES[category]['label'],evidence=evidence)
    return None
