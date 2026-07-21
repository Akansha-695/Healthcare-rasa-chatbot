import re
import json
import mysql.connector
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from typing import Any, Text, Dict, List
from rapidfuzz import process, utils, fuzz


def get_connection():
    return mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password=os.environ.get("DB_PASSWORD", ""),
        database="healthcaree",
        use_pure=True
    )


def extract_blood_type(text):
    if not text:
        return None
    t = text.lower()
    negation_markers = ["not", "other than", "except", "excluding", "exclude", "should not"]
    has_negation = any(marker in t for marker in negation_markers)
    spelled_map = [
        ("ab positive", "AB+"), ("ab negative", "AB-"),
        ("a positive",  "A+"),  ("a negative",  "A-"),
        ("b positive",  "B+"),  ("b negative",  "B-"),
        ("o positive",  "O+"),  ("o negative",  "O-"),
    ]
    for phrase, value in spelled_map:
        if phrase in t:
            if has_negation:
                return None
            return value
    group_match = re.search(r'(?<![a-z])(ab[+\-]|a[+\-]|b[+\-]|o[+\-])(?![a-z])', t)
    if group_match:
        if has_negation:
            return None
        return group_match.group(1).upper()
    return None


def extract_negated_blood_type(text):
    if not text:
        return None
    t = text.lower()
    negation_patterns = [
        r"not\s+be\s+([ab][\+\-]|ab[\+\-]|o[\+\-])",
        r"should\s+not\s+be\s+([ab][\+\-]|ab[\+\-]|o[\+\-])",
        r"other\s+than\s+([ab][\+\-]|ab[\+\-]|o[\+\-])",
        r"except\s+([ab][\+\-]|ab[\+\-]|o[\+\-])",
        r"excluding\s+([ab][\+\-]|ab[\+\-]|o[\+\-])",
        r"not\s+([ab][\+\-]|ab[\+\-]|o[\+\-])",
        r"exclude\s+([ab][\+\-]|ab[\+\-]|o[\+\-])",
    ]
    spelled_negation_patterns = [
        r"not\s+be\s+(ab\s+positive|ab\s+negative|a\s+positive|a\s+negative|b\s+positive|b\s+negative|o\s+positive|o\s+negative)",
        r"should\s+not\s+be\s+(ab\s+positive|ab\s+negative|a\s+positive|a\s+negative|b\s+positive|b\s+negative|o\s+positive|o\s+negative)",
        r"other\s+than\s+(ab\s+positive|ab\s+negative|a\s+positive|a\s+negative|b\s+positive|b\s+negative|o\s+positive|o\s+negative)",
        r"except\s+(ab\s+positive|ab\s+negative|a\s+positive|a\s+negative|b\s+positive|b\s+negative|o\s+positive|o\s+negative)",
        r"not\s+(ab\s+positive|ab\s+negative|a\s+positive|a\s+negative|b\s+positive|b\s+negative|o\s+positive|o\s+negative)",
    ]
    spelled_map = {
        "ab positive": "AB+", "ab negative": "AB-",
        "a positive": "A+",  "a negative": "A-",
        "b positive": "B+",  "b negative": "B-",
        "o positive": "O+",  "o negative": "O-",
    }
    for pattern in negation_patterns:
        m = re.search(pattern, t)
        if m:
            return m.group(1).upper()
    for pattern in spelled_negation_patterns:
        m = re.search(pattern, t)
        if m:
            phrase = m.group(1).strip()
            return spelled_map.get(phrase)
    return None


def extract_gender(text):
    if not text:
        return None
    synonyms = {
        "gents": "Male", "gent": "Male", "men": "Male",
        "man": "Male", "boys": "Male", "males": "Male",
        "femles": "Female", "femsle": "Female",
        "ladies": "Female", "lady": "Female", "women": "Female",
        "woman": "Female", "girls": "Female", "females": "Female"
    }
    for word in text.lower().split():
        if word in synonyms:
            return synonyms[word]
    result = process.extractOne(text.lower(), ["male", "female"], scorer=fuzz.ratio)
    if result:
        match, score, _ = result
        if score >= 70:
            return match.title()
    return None


def extract_both_genders(text):
    t = text.lower()
    has_male   = any(w in t.split() for w in ["male", "males", "men", "man", "gent", "gents", "boys"])
    has_female = any(w in t.split() for w in ["female", "females", "women", "woman", "ladies", "lady", "girls", "femles"])
    return has_male and has_female


def extract_medical_condition(text):
    if not text:
        return None
    valid = ["Cancer", "Diabetes", "Obesity", "Hypertension", "Asthma", "Arthritis"]
    t = text.lower()
    for c in valid:
        if c.lower() in t:
            return c
    if len(text.split()) <= 3:
        return None
    words = t.split()
    best_match, best_score = None, 0
    for word in words:
        result = process.extractOne(word, valid, scorer=fuzz.ratio)
        if result:
            match, score, _ = result
            if score > best_score:
                best_match, best_score = match, score
    if best_score >= 60:
        return best_match
    return None


def extract_admission_type(text):
    if not text:
        return None
    valid = ["Urgent", "Emergency", "Elective"]
    words = text.lower().split()
    for word in words:
        result = process.extractOne(word, valid, scorer=fuzz.ratio)
        if result:
            match, score, _ = result
            if score >= 70:
                return match
    return None


def extract_medication(text):
    if not text:
        return None
    valid = ["Paracetamol", "Ibuprofen", "Aspirin", "Penicillin", "Lipitor"]
    words = text.lower().split()
    best_match, best_score = None, 0
    for word in words:
        result = process.extractOne(word, valid, scorer=fuzz.ratio)
        if result:
            match, score, _ = result
            if score > best_score:
                best_match, best_score = match, score
    if best_score >= 65:
        return best_match
    return None


def extract_test_result(text):
    if not text:
        return None
    t = text.lower()
    if "inconclusive" in t:
        return "Inconclusive"
    if "abnormal" in t:
        return "Abnormal"
    if "normal" in t:
        return "Normal"
    valid = ["Normal", "Abnormal", "Inconclusive"]
    words = t.split()
    for word in words:
        result = process.extractOne(word, valid, scorer=fuzz.ratio)
        if result:
            match, score, _ = result
            if score >= 85:
                return match
    return None


def extract_age_filter(text):
    if not text:
        return None, None
    patterns = [
        (r'above\s+(\d+)', 'above'),
        (r'older\s+than\s+(\d+)', 'above'),
        (r'greater\s+than\s+(\d+)', 'above'),
        (r'below\s+(\d+)', 'below'),
        (r'younger\s+than\s+(\d+)', 'below'),
        (r'less\s+than\s+(\d+)', 'below'),
        (r'under\s+(\d+)', 'below'),
        (r'over\s+(\d+)', 'above'),
        (r'aged?\s+(\d+)', 'exact'),
        (r'age\s+(\d+)', 'exact'),
    ]
    for pattern, operator in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return operator, match.group(1)
    between = re.search(r'between\s+(\d+)\s+and\s+(\d+)', text.lower())
    if between:
        return 'between', f"{between.group(1)},{between.group(2)}"
    return None, None


def extract_patient_name_from_text(text):
    if not text:
        return None
    stopwords_at_start = {"Show","What","Which","Who","When","Tell","Give",
                           "Is","Are","Does","How","List","Display"}
    words = text.replace("?", "").split()
    runs, current = [], []
    for i, w in enumerate(words):
        clean = w.strip(".,!")
        if clean and clean[0].isupper():
            if i == 0 and clean in stopwords_at_start:
                if current:
                    runs.append(current)
                    current = []
                continue
            current.append(clean)
        else:
            if current:
                runs.append(current)
                current = []
    if current:
        runs.append(current)
    if not runs:
        return None
    best = max(runs, key=len)
    return " ".join(best)


def extract_billing_filter(text):
    if not text:
        return None, None
    patterns = [
        (r'billing\s+above\s+(\d+)', 'above'),
        (r'billing\s+over\s+(\d+)', 'above'),
        (r'billing\s+more\s+than\s+(\d+)', 'above'),
        (r'billing\s+below\s+(\d+)', 'below'),
        (r'billing\s+less\s+than\s+(\d+)', 'below'),
        (r'billed\s+more\s+than\s+(\d+)', 'above'),
        (r'billed\s+less\s+than\s+(\d+)', 'below'),
        (r'amount\s+above\s+(\d+)', 'above'),
        (r'amount\s+below\s+(\d+)', 'below'),
    ]
    for pattern, operator in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return operator, match.group(1)
    return None, None


def detect_requested_field(text):
    t = text.lower()
    field_map = {
        "doctor":         ["doctor", "physician", "treating doctor"],
        "hospital":       ["hospital", "clinic", "admitted to", "which hospital"],
        "condition":      ["condition", "disease", "suffering", "diagnosis", "medical condition"],
        "medication":     ["medication", "medicine", "drug", "prescription", "taking"],
        "blood":          ["blood type", "blood group"],
        "age":            ["age", "how old", "years old"],
        "gender":         ["gender", "sex", "male or female"],
        "insurance":      ["insurance", "insurance provider", "insurer"],
        "billing":        ["billing", "bill", "amount", "cost", "charges"],
        "room":           ["room", "room number", "ward"],
        "admission":      ["admission", "admission type", "admitted"],
        "discharge":      ["discharge", "discharge date", "released"],
        "test":           ["test", "test result", "results"],
        "admission_date": ["date of admission", "when admitted", "admission date"],
    }
    for field, keywords in field_map.items():
        if any(k in t for k in keywords):
            return field
    return "all"


def is_chart_query(text):
    t = text.lower()
    explicit = [
        "chart", "graph", "plot", "visualize", "visualisation", "visualization",
        "bar chart", "pie chart", "line chart", "bar graph", "pie graph",
        "show graph", "show chart", "draw chart", "draw graph",
        "show me graph", "show me chart", "make chart", "make graph",
        "create chart", "create graph", "generate chart", "generate graph",
        "display chart", "display graph",
    ]
    if any(k in t for k in explicit):
        return True
    distribution = [
        "distribution of", "breakdown of", "breakdown by",
        "distribution by", "by gender", "by blood", "by condition",
        "by admission", "by medication", "by hospital", "by doctor",
        "by test", "by age", "gender wise", "genderwise",
        "blood wise", "bloodwise", "condition wise", "conditionwise",
        "admission wise", "admissionwise", "medication wise",
        "hospital wise", "doctor wise", "test wise",
        "compare male and female", "compare female and male",
        "male vs female", "female vs male",
        "male female comparison", "female male comparison",
        "how are patients distributed", "patient distribution",
        "which condition has most", "which blood type has most",
        "which hospital has most", "which doctor has most",
        "which medication is most", "most common condition",
        "most common blood", "most common medication",
        "most common admission", "most common test",
        "top conditions", "top diseases", "top hospitals",
        "top doctors", "top medications",
        "age distribution", "age group", "age wise",
        "gender distribution", "gender breakdown",
        "medication wise", "admission type wise","blood group breakdown",
        "blood breakdown","blood group distribution","blood type distribution",
        "blood group wise","blood wise count", "disease distribution","condition distribution",
        "condition wise","disease wise","medical condition distribution","cancer distribution",
        "diabetes distribution","asthma distribution","arthritis distribution","obesity distribution",
        "hypertension distribution","disease distribution","condition distribution",
    ]
    if any(k in t for k in distribution):
        return True
    vs_patterns = [
        r"\bvs\b", r"\bversus\b",
        r"compare\s+\w+\s+and\s+\w+",
        r"difference\s+between",
        r"which\s+is\s+(more|higher|common|frequent)",
        r"(urgent|emergency|elective)\s+(vs|versus|and|compared)",
        r"(cancer|diabetes|asthma|obesity|hypertension|arthritis).*(vs|versus|and|compared)",
    ]
    for pat in vs_patterns:
        if re.search(pat, t):
            return True
    return False


def detect_chart_type(text):
    t = text.lower()
    chart_config = {
        "group_by":   None,
        "split_by":   None,
        "chart_type": "bar",
        "filters":    {},
        "multi":      None,
    }

    # chart type
    if "pie" in t:
        chart_config["chart_type"] = "pie"
    elif "line" in t:
        chart_config["chart_type"] = "line"
    else:
        chart_config["chart_type"] = "bar"

    # ── group_by detection — ORDER MATTERS, most specific first ──────────────
    if any(k in t for k in ["urgent", "emergency", "elective",
                             "admission type", "admissionwise", "admission wise",
                             "admission type wise"]):
        chart_config["group_by"] = "Admission Type"

    elif any(k in t for k in ["age distribution", "age group", "age wise",
                               "agewise", "age breakdown", "age group wise",
                               "comparison of age"]):
        chart_config["group_by"] = "Age"

    elif any(k in t for k in ["blood group", "blood type", "bloodwise",
                               "blood wise", "blood"]):
        chart_config["group_by"] = "Blood Type"

    elif any(k in t for k in ["medical condition", "condition", "disease",
                               "conditionwise", "condition wise"]):
        chart_config["group_by"] = "Medical Condition"

    elif any(k in t for k in ["medication wise", "medication", "medicine",
                               "drug", "prescription"]):
        chart_config["group_by"] = "Medication"

    elif any(k in t for k in ["hospital", "hospitalwise", "hospital wise"]):
        chart_config["group_by"] = "Hospital"

    elif any(k in t for k in ["doctor", "physician", "doctorwise", "doctor wise"]):
        chart_config["group_by"] = "Doctor"

    elif any(k in t for k in ["test result", "test results", "testwise",
                               "test wise", "test"]):
        chart_config["group_by"] = "Test Results"

    elif any(k in t for k in ["gender", "sex", "genderwise", "gender wise",
                               "male", "female", "men", "women",
                               "gender distribution", "gender breakdown"]):
        chart_config["group_by"] = "Gender"

    else:
        chart_config["group_by"] = "Medical Condition"

    # ── split by gender ───────────────────────────────────────────────────────
    if chart_config["group_by"] != "Gender":
        if extract_both_genders(t) or re.search(r'(male.*female|female.*male)', t):
            chart_config["split_by"] = "Gender"
        elif any(w in t.split() for w in ["male", "males", "men", "man", "gent", "gents"]):
            chart_config["filters"]["gender"] = "Male"
        elif any(w in t.split() for w in ["female", "females", "women", "woman", "ladies"]):
            chart_config["filters"]["gender"] = "Female"

    # ── condition filter ──────────────────────────────────────────────────────
    valid_conditions = ["Cancer", "Diabetes", "Hypertension", "Asthma", "Arthritis", "Obesity"]
    if chart_config["group_by"] != "Medical Condition":
        found = [c for c in valid_conditions if c.lower() in t]
        if found:
            chart_config["filters"]["medical_condition"] = found

    # ── blood type filter ─────────────────────────────────────────────────────
    if chart_config["group_by"] != "Blood Type":
        bt = extract_blood_type(text)
        if bt:
            chart_config["filters"]["blood_type"] = bt

    # ── admission type filter ─────────────────────────────────────────────────
    if chart_config["group_by"] != "Admission Type":
        adm = extract_admission_type(text)
        if adm:
            chart_config["filters"]["admission_type"] = adm

    # ── medication filter ─────────────────────────────────────────────────────
    if chart_config["group_by"] != "Medication":
        med = extract_medication(text)
        if med:
            chart_config["filters"]["medication"] = med

    # ── test result filter ────────────────────────────────────────────────────
    if chart_config["group_by"] != "Test Results":
        tr = extract_test_result(text)
        if tr:
            chart_config["filters"]["test_result"] = tr

    return chart_config


RESET_KEYWORDS = [
    "all patients", "how many patients", "total patients",
    "count patients", "list all", "show all", "display all",
    "how many people", "how many individuals"
]


def is_followup_query(text):
    t = text.lower().strip()
    if len(t.split()) <= 3:
        return True
    if any(k in t for k in RESET_KEYWORDS):
        return False
    new_query_signals = ["patients", "people", "individuals", "cases", "admissions"]
    if any(k in t for k in new_query_signals):
        return False
    return True


def is_count_query(text):
    return any(k in text.lower() for k in ["total", "how many", "count", "number of", "how much"])


def extract_all_filters(text, tracker):
    filters = {}

    if is_followup_query(text):
        prev = tracker.get_slot("previous_filters")
        if prev:
            try:
                filters = json.loads(prev)
                filters.pop("_action_type", None)
            except:
                filters = {}

    filters.pop("medical_condition", None)

    if not is_followup_query(text):
        filters.pop("gender", None)
        filters.pop("blood_type", None)
        filters.pop("medical_condition", None)   # ← add this line here
        filters.pop("exclude_blood_type", None)
        filters.pop("admission_type", None)
        filters.pop("medication", None)
        filters.pop("test_result", None)
        filters.pop("age_operator", None)
        filters.pop("age_value", None)
        filters.pop("billing_operator", None)
        filters.pop("billing_value", None)

    slot_map = {
        "gender": "gender",
        "blood_type": "blood_type",
        "admission_type": "admission_type",
        "medication": "medication",
        "test_result": "test_result",
    }
    for slot, key in slot_map.items():
        val = tracker.get_slot(slot)
        if val:
            filters[key] = val

    negated_blood = extract_negated_blood_type(text)
    if negated_blood:
        filters["exclude_blood_type"] = negated_blood
    else:
        blood_type = extract_blood_type(text)
        if blood_type:
            filters["blood_type"] = blood_type

    if extract_both_genders(text):
        filters.pop("gender", None)
        filters["both_genders"] = True
    else:
        gender = extract_gender(text)
        if gender:
            filters["gender"] = gender
            filters.pop("both_genders", None)

        txt = text.lower().strip()
        if txt in ["for males", "male", "only males", "only male", "males", "and males",
                   "and male", "for gent", "gent", "only gent", "and gent", "for gents",
                   "gents", "only gents", "and gents", "and for males", "what about males"]:
            filters["gender"] = "Male"
            filters.pop("both_genders", None)
        elif txt in ["for females", "female", "only females", "only female", "females",
                     "and females", "and female", "for women", "women", "only women",
                     "and women", "for womens", "womens", "only womens", "and womens",
                     "for woman", "woman", "only woman", "and woman",
                     "and for females", "what about females", "and females?"]:
            filters["gender"] = "Female"
            filters.pop("both_genders", None)

    valid_conditions = ["Cancer", "Diabetes", "Hypertension", "Asthma", "Arthritis", "Obesity"]
    found_conditions = [c for c in valid_conditions if c.lower() in text.lower()]
    if found_conditions and len(text.split()) >= 4:
        filters["medical_condition"] = found_conditions
    else:
        condition = extract_medical_condition(text)
        if condition:
            filters["medical_condition"] = [condition]

    admission = extract_admission_type(text)
    if admission:
        filters["admission_type"] = admission

    medication = extract_medication(text)
    if medication:
        filters["medication"] = medication

    test_result = extract_test_result(text)
    if test_result:
        filters["test_result"] = test_result

    age_op, age_val = extract_age_filter(text)
    if age_op and age_val:
        filters["age_operator"] = age_op
        filters["age_value"]    = age_val

    billing_op, billing_val = extract_billing_filter(text)
    if billing_op and billing_val:
        filters["billing_operator"] = billing_op
        filters["billing_value"]    = billing_val

    return filters


def build_where_clause(filters):
    conditions = []
    params     = []

    if "gender" in filters:
        conditions.append("LOWER(Gender) = LOWER(%s)")
        params.append(filters["gender"])

    if "blood_type" in filters:
        conditions.append("LOWER(`Blood Type`) = LOWER(%s)")
        params.append(filters["blood_type"])

    if "exclude_blood_type" in filters:
        conditions.append("LOWER(`Blood Type`) != LOWER(%s)")
        params.append(filters["exclude_blood_type"])

    if "medical_condition" in filters:
        conds = filters["medical_condition"]
        if isinstance(conds, list):
            placeholders = ",".join(["%s"] * len(conds))
            conditions.append(f"`Medical Condition` IN ({placeholders})")
            params.extend(conds)
        else:
            conditions.append("LOWER(`Medical Condition`) = LOWER(%s)")
            params.append(conds)

    if "admission_type" in filters:
        conditions.append("LOWER(`Admission Type`) = LOWER(%s)")
        params.append(filters["admission_type"])

    if "medication" in filters:
        conditions.append("LOWER(Medication) = LOWER(%s)")
        params.append(filters["medication"])

    if "test_result" in filters:
        conditions.append("LOWER(`Test Results`) = LOWER(%s)")
        params.append(filters["test_result"])

    if "age_operator" in filters and "age_value" in filters:
        op  = filters["age_operator"]
        val = filters["age_value"]
        if op == "above":
            conditions.append("Age > %s")
            params.append(int(val))
        elif op == "below":
            conditions.append("Age < %s")
            params.append(int(val))
        elif op == "exact":
            conditions.append("Age = %s")
            params.append(int(val))
        elif op == "between":
            low, high = val.split(",")
            conditions.append("Age BETWEEN %s AND %s")
            params.extend([int(low), int(high)])

    if "billing_operator" in filters and "billing_value" in filters:
        op  = filters["billing_operator"]
        val = filters["billing_value"]
        if op == "above":
            conditions.append("`Billing Amount` > %s")
            params.append(float(val))
        elif op == "below":
            conditions.append("`Billing Amount` < %s")
            params.append(float(val))

    return conditions, params


def reset_slots():
    return [
        SlotSet("gender", None),
        SlotSet("blood_type", None),
        SlotSet("medical_condition", None),
        SlotSet("admission_type", None),
        SlotSet("medication", None),
        SlotSet("test_result", None),
        SlotSet("age_value", None),
        SlotSet("age_operator", None),
        SlotSet("billing_value", None),
        SlotSet("billing_operator", None),
        SlotSet("room_number", None),
        SlotSet("patient_name", None),
        SlotSet("doctor_name", None),
        SlotSet("hospital_name", None),
        SlotSet("insurance_provider", None),
    ]


class ActionCountPatients(Action):

    def name(self) -> Text:
        return "action_count_patients"

    def run(self, dispatcher, tracker, domain):
        user_text = tracker.latest_message.get("text", "")

        if is_chart_query(user_text):
            return ActionChartData().run(dispatcher, tracker, domain)

        if extract_both_genders(user_text):
            return self._run_both_genders(dispatcher, tracker, user_text)

        if any(k in user_text.lower() for k in ["billing", "billed", "amount", "age", "older", "younger"]):
            filters = {}
            billing_op, billing_val = extract_billing_filter(user_text)
            if billing_op and billing_val:
                filters["billing_operator"] = billing_op
                filters["billing_value"]    = billing_val
            age_op, age_val = extract_age_filter(user_text)
            if age_op and age_val:
                filters["age_operator"] = age_op
                filters["age_value"]    = age_val
            gender = extract_gender(user_text)
            if gender:
                filters["gender"] = gender
            valid_conditions = ["Cancer", "Diabetes", "Hypertension", "Asthma", "Arthritis", "Obesity"]
            found_conditions  = [c for c in valid_conditions if c.lower() in user_text.lower()]
            if found_conditions:
                filters["medical_condition"] = found_conditions
        else:
            filters = extract_all_filters(user_text, tracker)

        print(f"COUNT DEBUG — filters: {filters}")

        if not filters or filters == {"both_genders": True}:
            dispatcher.utter_message(text="Please specify at least one filter.")
            return []

        conditions, params = build_where_clause(filters)
        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT COUNT(*) FROM health_data WHERE {where}"

        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            count  = cursor.fetchone()[0]

            parts = []
            if "gender"             in filters: parts.append(filters["gender"])
            if "blood_type"         in filters: parts.append(f"blood type {filters['blood_type']}")
            if "exclude_blood_type" in filters: parts.append(f"blood type NOT {filters['exclude_blood_type']}")
            if "medical_condition"  in filters:
                mc = filters["medical_condition"]
                parts.append(", ".join(mc) if isinstance(mc, list) else mc)
            if "admission_type"     in filters: parts.append(f"{filters['admission_type']} admission")
            if "medication"         in filters: parts.append(f"on {filters['medication']}")
            if "test_result"        in filters: parts.append(f"{filters['test_result']} test results")
            if "age_operator"       in filters: parts.append(f"age {filters['age_operator']} {filters['age_value']}")
            if "billing_operator"   in filters: parts.append(f"billing {filters['billing_operator']} {filters['billing_value']}")

            if parts:
                dispatcher.utter_message(text=f"Total patients with {', '.join(parts)}: {count}")
            else:
                dispatcher.utter_message(text=f"Total patients: {count}")

            cursor.close()
            conn.close()

        except Exception as e:
            dispatcher.utter_message(text=f"Database error: {str(e)}")

        return reset_slots() + [SlotSet("previous_filters", json.dumps({**filters, "_action_type": "count"}))]

    def _run_both_genders(self, dispatcher, tracker, user_text):
        filters = {}
        negated_blood = extract_negated_blood_type(user_text)
        if negated_blood:
            filters["exclude_blood_type"] = negated_blood
        else:
            blood_type = extract_blood_type(user_text)
            if blood_type:
                filters["blood_type"] = blood_type

        valid_conditions = ["Cancer", "Diabetes", "Hypertension", "Asthma", "Arthritis", "Obesity"]
        found_conditions = [c for c in valid_conditions if c.lower() in user_text.lower()]
        if found_conditions:
            filters["medical_condition"] = found_conditions

        admission = extract_admission_type(user_text)
        if admission:
            filters["admission_type"] = admission

        medication = extract_medication(user_text)
        if medication:
            filters["medication"] = medication

        test_result = extract_test_result(user_text)
        if test_result:
            filters["test_result"] = test_result

        age_op, age_val = extract_age_filter(user_text)
        if age_op and age_val:
            filters["age_operator"] = age_op
            filters["age_value"]    = age_val

        billing_op, billing_val = extract_billing_filter(user_text)
        if billing_op and billing_val:
            filters["billing_operator"] = billing_op
            filters["billing_value"]    = billing_val

        results = {}
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            for gender in ["Male", "Female"]:
                gender_filters = {**filters, "gender": gender}
                conditions, params = build_where_clause(gender_filters)
                where = " AND ".join(conditions) if conditions else "1=1"
                query = f"SELECT COUNT(*) FROM health_data WHERE {where}"
                cursor.execute(query, params)
                results[gender] = cursor.fetchone()[0]
            cursor.close()
            conn.close()

            parts = []
            if "blood_type"         in filters: parts.append(f"blood type {filters['blood_type']}")
            if "exclude_blood_type" in filters: parts.append(f"blood type NOT {filters['exclude_blood_type']}")
            if "medical_condition"  in filters:
                mc = filters["medical_condition"]
                parts.append(", ".join(mc) if isinstance(mc, list) else mc)
            if "admission_type"     in filters: parts.append(f"{filters['admission_type']} admission")
            if "medication"         in filters: parts.append(f"on {filters['medication']}")
            if "test_result"        in filters: parts.append(f"{filters['test_result']} test results")

            extra = f" with {', '.join(parts)}" if parts else ""
            msg = (f"Patient counts{extra}:\n"
                   f"• Male: {results['Male']}\n"
                   f"• Female: {results['Female']}\n"
                   f"• Total: {results['Male'] + results['Female']}")
            dispatcher.utter_message(text=msg)

        except Exception as e:
            dispatcher.utter_message(text=f"Database error: {str(e)}")

        return reset_slots() + [SlotSet("previous_filters", json.dumps({**filters, "_action_type": "count"}))]


class ActionListPatients(Action):

    def name(self) -> Text:
        return "action_list_patients"

    def run(self, dispatcher, tracker, domain):
        user_text = tracker.latest_message.get("text", "")

        if is_chart_query(user_text):
            return ActionChartData().run(dispatcher, tracker, domain)

        if is_count_query(user_text):
            return ActionCountPatients().run(dispatcher, tracker, domain)

        if is_followup_query(user_text):
            prev = tracker.get_slot("previous_filters")
            if prev:
                try:
                    prev_data = json.loads(prev)
                    if prev_data.get("_action_type") == "count":
                        return ActionCountPatients().run(dispatcher, tracker, domain)
                except:
                    pass

        filters = extract_all_filters(user_text, tracker)

        print(f"LIST DEBUG — filters: {filters}")

        if not filters or filters == {"both_genders": True}:
            dispatcher.utter_message(text="Please specify at least one filter.")
            return []

        conditions, params = build_where_clause(filters)
        where = " AND ".join(conditions) if conditions else "1=1"
        query = (
            f"SELECT Name, Age, Gender, `Blood Type`, `Medical Condition`, Doctor, Hospital, "
            f"`Admission Type`, Medication, `Test Results` "
            f"FROM health_data WHERE {where} LIMIT 10"
        )

        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows   = cursor.fetchall()

            if not rows:
                dispatcher.utter_message(text="No patients found matching your criteria.")
            else:
                response = "Here are the patients:\n"
                for row in rows:
                    response += (
                        f"- {str(row[0]).title()} | Age: {row[1]} | {str(row[2]).title()} | "
                        f"Blood Type: {str(row[3]).upper()} | Condition: {str(row[4]).title()} | "
                        f"Doctor: {str(row[5]).title()} | Hospital: {str(row[6]).title()} | "
                        f"Admission: {str(row[7]).title()} | Medication: {str(row[8]).title()} | "
                        f"Test: {str(row[9]).title()}\n"
                    )
                dispatcher.utter_message(text=response)

            cursor.close()
            conn.close()

        except Exception as e:
            dispatcher.utter_message(text=f"Database error: {str(e)}")

        return reset_slots() + [SlotSet("previous_filters", json.dumps({**filters, "_action_type": "list"}))]


class ActionGetPatientInfo(Action):

    def name(self) -> Text:
        return "action_get_patient_info"

    def run(self, dispatcher, tracker, domain):
        user_text    = tracker.latest_message.get("text", "")
        patient_name = tracker.get_slot("patient_name")

        if not patient_name:
            patient_name = extract_patient_name_from_text(user_text)

        if not patient_name:
            dispatcher.utter_message(text="Please provide the patient's name.")
            return []

        requested_field = detect_requested_field(user_text)

        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT Name, Age, Gender, `Blood Type`, `Medical Condition`, `Date of Admission`, "
                "Doctor, Hospital, `Insurance Provider`, `Billing Amount`, `Room Number`, "
                "`Admission Type`, `Discharge Date`, Medication, `Test Results` "
                "FROM health_data WHERE LOWER(Name) LIKE LOWER(%s) LIMIT 1",
                (f"%{patient_name}%",)
            )
            row = cursor.fetchone()

            if row:
                name       = str(row[0]).title()
                age        = row[1]
                gender     = str(row[2]).title()
                blood      = str(row[3]).upper()
                condition  = str(row[4]).title()
                adm_date   = row[5]
                doctor     = str(row[6]).title()
                hospital   = str(row[7]).title()
                insurance  = str(row[8]).title()
                billing    = row[9]
                room       = row[10]
                adm_type   = str(row[11]).title()
                dis_date   = row[12]
                medication = str(row[13]).title()
                test       = str(row[14]).title()

                if requested_field == "doctor":
                    response = f"Doctor of {name}: {doctor}"
                elif requested_field == "hospital":
                    response = f"{name} was admitted to: {hospital}"
                elif requested_field == "condition":
                    response = f"Medical condition of {name}: {condition}"
                elif requested_field == "medication":
                    response = f"Medication for {name}: {medication}"
                elif requested_field == "blood":
                    response = f"Blood type of {name}: {blood}"
                elif requested_field == "age":
                    response = f"Age of {name}: {age}"
                elif requested_field == "gender":
                    response = f"Gender of {name}: {gender}"
                elif requested_field == "insurance":
                    response = f"Insurance provider of {name}: {insurance}"
                elif requested_field == "billing":
                    response = f"Billing amount for {name}: {billing}"
                elif requested_field == "room":
                    response = f"Room number of {name}: {room}"
                elif requested_field == "admission":
                    response = f"Admission type of {name}: {adm_type}"
                elif requested_field == "discharge":
                    response = f"Discharge date of {name}: {dis_date}"
                elif requested_field == "test":
                    response = f"Test results of {name}: {test}"
                elif requested_field == "admission_date":
                    response = f"Date of admission of {name}: {adm_date}"
                else:
                    response = (
                        f"Here are the patients:\n"
                        f"- {name} | Age: {age} | {gender} | "
                        f"Blood Type: {blood} | Condition: {condition} | "
                        f"Doctor: {doctor} | Hospital: {hospital} | "
                        f"Insurance: {insurance} | Billing: {billing} | "
                        f"Room: {room} | Admission: {adm_type} | "
                        f"Admitted: {adm_date} | Discharged: {dis_date} | "
                        f"Medication: {medication} | Test: {test}"
                    )

                dispatcher.utter_message(text=response)
            else:
                dispatcher.utter_message(text=f"No patient found with name '{patient_name}'.")

            cursor.close()
            conn.close()

        except Exception as e:
            dispatcher.utter_message(text=f"Database error: {str(e)}")

        return reset_slots() + [SlotSet("previous_filters", None)]


class ActionMostCommonBloodType(Action):

    def name(self) -> Text:
        return "action_most_common_blood_type"

    def run(self, dispatcher, tracker, domain):
        user_text = tracker.latest_message.get("text", "")
        gender    = tracker.get_slot("gender") or extract_gender(user_text)

        if not gender and is_followup_query(user_text):
            prev = tracker.get_slot("previous_filters")
            if prev:
                try:
                    prev_filters = json.loads(prev)
                    gender = prev_filters.get("gender")
                except:
                    pass

        query  = "SELECT `Blood Type`, COUNT(*) as count FROM health_data"
        params = []
        if gender:
            query += " WHERE LOWER(Gender) = LOWER(%s)"
            params.append(gender)
        query += " GROUP BY `Blood Type` ORDER BY count DESC LIMIT 1"

        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            result = cursor.fetchone()
            if result:
                msg = "Most common blood type"
                if gender:
                    msg += f" among {gender} patients"
                msg += f": {str(result[0]).upper()} ({result[1]} patients)"
                dispatcher.utter_message(text=msg)
            else:
                dispatcher.utter_message(text="No data found.")
            cursor.close()
            conn.close()
        except Exception as e:
            dispatcher.utter_message(text=f"Database error: {str(e)}")

        return reset_slots() + [SlotSet("previous_filters", None)]
    

class ActionLeastCommonBloodType(Action):

    def name(self):
        return "action_least_common_blood_type"

    def run(self, dispatcher, tracker, domain):

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT `Blood Type`, COUNT(*)
        FROM health_data
        GROUP BY `Blood Type`
        ORDER BY COUNT(*) ASC
        LIMIT 1
        """)

        result = cursor.fetchone()

        dispatcher.utter_message(
            text=f"Least common blood type: {result[0]} ({result[1]} patients)"
        )

        cursor.close()
        conn.close()

        return []


class ActionCompareBloodTypes(Action):

    def name(self) -> Text:
        return "action_compare_blood_types"

    def run(self, dispatcher, tracker, domain):

        user_text = tracker.latest_message.get("text", "").upper()

        bloods = re.findall(
                r'AB\+|AB-|A\+|A-|B\+|B-|O\+|O-',
        user_text
        )

        if len(bloods) < 2:
            dispatcher.utter_message(
                text="Please specify two blood groups."
            )
        return []

        blood1 = bloods[0]
        blood2 = bloods[1]

        try:

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM health_data
                WHERE `Blood Type`=%s
                """,
                (blood1,)
            )

            count1 = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM health_data
                WHERE `Blood Type`=%s
                """,
                (blood2,)
            )

            count2 = cursor.fetchone()[0]

            if count1 > count2:

                msg = (
                    f"{blood1} patients ({count1}) "
                    f"are more than {blood2} patients ({count2})."
                )

            elif count2 > count1:

                msg = (
                    f"{blood2} patients ({count2}) "
                    f"are more than {blood1} patients ({count1})."
                )

            else:

                msg = (
                    f"{blood1} and {blood2} have equal patients "
                    f"({count1})."
                )

            dispatcher.utter_message(text=msg)

            cursor.close()
            conn.close()

        except Exception as e:
            dispatcher.utter_message(text=str(e))

        return []


class ActionMostCommonDisease(Action):

    def name(self):
        return "action_most_common_disease"

    def run(self, dispatcher, tracker, domain):

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT `Medical Condition`, COUNT(*)
            FROM health_data
            GROUP BY `Medical Condition`
            ORDER BY COUNT(*) DESC
            LIMIT 1
        """)

        result = cursor.fetchone()

        if result:
            dispatcher.utter_message(
                text=f"Most common disease: {result[0]} ({result[1]} patients)"
            )

        cursor.close()
        conn.close()

        return []


class ActionCompareAdmissions(Action):

    def name(self) -> Text:
        return "action_compare_admissions"

    def run(self, dispatcher, tracker, domain):
        user_text = tracker.latest_message.get("text", "").lower()

        admission_types = []
        if "urgent"    in user_text: admission_types.append("Urgent")
        if "emergency" in user_text: admission_types.append("Emergency")
        if "elective"  in user_text: admission_types.append("Elective")

        if len(admission_types) < 2:
            dispatcher.utter_message(
                text="Please specify at least two admission types to compare."
            )
            return []

        try:
            conn   = get_connection()
            cursor = conn.cursor()
            results = {}
            for adm in admission_types:
                cursor.execute(
                    "SELECT COUNT(*) FROM health_data WHERE LOWER(`Admission Type`) = LOWER(%s)",
                    (adm,)
                )
                results[adm] = cursor.fetchone()[0]
            cursor.close()
            conn.close()

            response = "Admission Type Comparison:\n\n"
            for adm, count in results.items():
                response += f"{adm}: {count}\n"
            highest  = max(results, key=results.get)
            response += f"\nMost common: {highest} ({results[highest]} patients)"
            dispatcher.utter_message(text=response)

        except Exception as e:
            dispatcher.utter_message(text=f"Database error: {str(e)}")

        return []
    

class ActionHighestCancerBloodGroup(Action):

    def name(self):
        return "action_highest_cancer_bloodgroup"

    def run(self, dispatcher, tracker, domain):

        try:

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT `Blood Type`,
                       COUNT(*) as total
                FROM health_data
                WHERE `Medical Condition`='Cancer'
                GROUP BY `Blood Type`
                ORDER BY total DESC
                LIMIT 1
            """)

            row = cursor.fetchone()

            if row:

                dispatcher.utter_message(
                    text=f"Blood group with highest cancer cases: {row[0]} ({row[1]} patients)"
                )

            cursor.close()
            conn.close()

        except Exception as e:

            dispatcher.utter_message(text=str(e))

        return []


class ActionCompareDiseases(Action):

    def name(self):
        return "action_compare_diseases"

    def run(self, dispatcher, tracker, domain):

        try:

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
            SELECT COUNT(*)
            FROM health_data
            WHERE `Medical Condition`='Cancer'
            """)

            cancer = cursor.fetchone()[0]

            cursor.execute("""
            SELECT COUNT(*)
            FROM health_data
            WHERE `Medical Condition`='Diabetes'
            """)

            diabetes = cursor.fetchone()[0]

            dispatcher.utter_message(
                text=
                f"Cancer cases: {cancer}\n"
                f"Diabetes cases: {diabetes}"
            )

            cursor.close()
            conn.close()

        except Exception as e:
            dispatcher.utter_message(text=str(e))

        return []


class ActionChartData(Action):

    def name(self) -> Text:
        return "action_chart_data"

    def run(self, dispatcher, tracker, domain):
        user_text     = tracker.latest_message.get("text", "")
        chart_cfg     = detect_chart_type(user_text)
        group_by      = chart_cfg["group_by"]
        split_by      = chart_cfg["split_by"]
        chart_type    = chart_cfg["chart_type"]
        extra_filters = chart_cfg["filters"]

        print(f"CHART DEBUG — config: {chart_cfg}")

        try:
            conn   = get_connection()
            cursor = conn.cursor()

            conditions, params = build_where_clause(extra_filters)
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

            if group_by == "Age":
                if split_by == "Gender":
                    age_query = (
                        f"SELECT "
                        f"  CASE "
                        f"    WHEN Age < 18 THEN 'Under 18' "
                        f"    WHEN Age BETWEEN 18 AND 30 THEN '18-30' "
                        f"    WHEN Age BETWEEN 31 AND 45 THEN '31-45' "
                        f"    WHEN Age BETWEEN 46 AND 60 THEN '46-60' "
                        f"    WHEN Age BETWEEN 61 AND 75 THEN '61-75' "
                        f"    ELSE '75+' "
                        f"  END AS age_group, Gender, COUNT(*) as cnt "
                        f"FROM health_data {where} "
                        f"GROUP BY age_group, Gender "
                        f"ORDER BY MIN(Age)"
                    )
                    cursor.execute(age_query, params)
                    rows = cursor.fetchall()
                    data = {}
                    for age_group, gender, cnt in rows:
                        ag = str(age_group)
                        g  = str(gender).title()
                        if ag not in data:
                            data[ag] = {}
                        data[ag][g] = cnt
                    chart_data = {
                        "chart_type": chart_type,
                        "group_by":   "Age Group",
                        "split_by":   "Gender",
                        "data":       data,
                        "title":      "Age Group Distribution by Gender",
                    }
                else:
                    age_query = (
                        f"SELECT "
                        f"  CASE "
                        f"    WHEN Age < 18 THEN 'Under 18' "
                        f"    WHEN Age BETWEEN 18 AND 30 THEN '18-30' "
                        f"    WHEN Age BETWEEN 31 AND 45 THEN '31-45' "
                        f"    WHEN Age BETWEEN 46 AND 60 THEN '46-60' "
                        f"    WHEN Age BETWEEN 61 AND 75 THEN '61-75' "
                        f"    ELSE '75+' "
                        f"  END AS age_group, COUNT(*) as cnt "
                        f"FROM health_data {where} "
                        f"GROUP BY age_group "
                        f"ORDER BY MIN(Age)"
                    )
                    cursor.execute(age_query, params)
                    rows = cursor.fetchall()
                    data = {str(r[0]): r[1] for r in rows}
                    gender_label = extra_filters.get("gender", "")
                    chart_data = {
                        "chart_type": chart_type,
                        "group_by":   "Age Group",
                        "split_by":   None,
                        "data":       data,
                        "title":      "Age Group Distribution"
                                      + (f" ({gender_label})" if gender_label else ""),
                    }

            elif group_by in ("Hospital", "Doctor"):
                if split_by == "Gender":
                    query = (
                        f"SELECT `{group_by}`, Gender, COUNT(*) as cnt "
                        f"FROM health_data {where} "
                        f"GROUP BY `{group_by}`, Gender ORDER BY cnt DESC"
                    )
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
                    totals = {}
                    for label, gender, cnt in rows:
                        totals[label] = totals.get(label, 0) + cnt
                    top10 = sorted(totals, key=totals.get, reverse=True)[:10]
                    data = {}
                    for label, gender, cnt in rows:
                        if label in top10:
                            lbl = str(label).title()
                            g   = str(gender).title()
                            if lbl not in data:
                                data[lbl] = {}
                            data[lbl][g] = cnt
                    chart_data = {
                        "chart_type": chart_type,
                        "group_by":   group_by,
                        "split_by":   "Gender",
                        "data":       data,
                        "title":      f"Top 10 {group_by}s by Gender",
                    }
                else:
                    query = (
                        f"SELECT `{group_by}`, COUNT(*) as cnt "
                        f"FROM health_data {where} "
                        f"GROUP BY `{group_by}` ORDER BY cnt DESC LIMIT 10"
                    )
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
                    data = {str(r[0]).title(): r[1] for r in rows}
                    gender_label = extra_filters.get("gender", "")
                    chart_data = {
                        "chart_type": chart_type,
                        "group_by":   group_by,
                        "split_by":   None,
                        "data":       data,
                        "title":      f"Top 10 {group_by}s"
                                      + (f" ({gender_label})" if gender_label else ""),
                    }

            elif split_by == "Gender":
                query = (
                    f"SELECT `{group_by}`, Gender, COUNT(*) as cnt "
                    f"FROM health_data {where} "
                    f"GROUP BY `{group_by}`, Gender ORDER BY `{group_by}`"
                )
                cursor.execute(query, params)
                rows = cursor.fetchall()
                data = {}
                for label, gender, cnt in rows:
                    lbl = str(label).title() if label else "Unknown"
                    g   = str(gender).title()
                    if lbl not in data:
                        data[lbl] = {}
                    data[lbl][g] = cnt
                chart_data = {
                    "chart_type": chart_type,
                    "group_by":   group_by,
                    "split_by":   "Gender",
                    "data":       data,
                    "title":      f"{group_by} Distribution by Gender",
                }

            else:
                query = (
                    f"SELECT `{group_by}`, COUNT(*) as cnt "
                    f"FROM health_data {where} "
                    f"GROUP BY `{group_by}` ORDER BY cnt DESC"
                )
                cursor.execute(query, params)
                rows = cursor.fetchall()
                data = {(str(r[0]).upper() if group_by == "Blood Type"
                         else str(r[0]).title() if r[0] else "Unknown"): r[1]
                        for r in rows}
                gender_label = extra_filters.get("gender", "")
                cond_label   = ", ".join(extra_filters["medical_condition"]) \
                               if "medical_condition" in extra_filters else ""
                suffix_parts = [x for x in [gender_label, cond_label] if x]
                chart_data = {
                    "chart_type": chart_type,
                    "group_by":   group_by,
                    "split_by":   None,
                    "data":       data,
                    "title":      f"{group_by} Distribution"
                                  + (f" ({', '.join(suffix_parts)})" if suffix_parts else ""),
                }

            cursor.close()
            conn.close()
            dispatcher.utter_message(text=f"CHART_DATA:{json.dumps(chart_data)}")

        except Exception as e:
            dispatcher.utter_message(text=f"Database error: {str(e)}")

        return reset_slots() + [SlotSet("previous_filters", None)]


class ActionHealthcareAnalytics(Action):

    def run(self, dispatcher, tracker, domain):
        user_text = tracker.latest_message.get("text", "")
        possible_name = extract_patient_name_from_text(user_text)
        per_patient_keywords = ["treats", "prescribed to", "admitted to", "medication for",
                                 "details of", "about patient", "condition does"]
        if possible_name and any(k in user_text.lower() for k in per_patient_keywords):
            return ActionGetPatientInfo().run(dispatcher, tracker, domain)
    
    def name(self):
        return "action_healthcare_analytics"

    def run(self, dispatcher, tracker, domain):
        text = tracker.latest_message.get("text", "").lower()
        print("ANALYTICS ACTION HIT:", text)

        valid_conditions = ["cancer","diabetes","hypertension","asthma","arthritis","obesity"]

        conn   = get_connection()
        cursor = conn.cursor()

        try:
            # highest blood group for a condition
            if ("blood group" in text or "blood type" in text) and any(c in text for c in valid_conditions):
                matched = next((c for c in valid_conditions if c in text), "cancer")
                cursor.execute("""
                    SELECT `Blood Type`, COUNT(*) as total
                    FROM health_data
                    WHERE LOWER(`Medical Condition`) = %s
                    GROUP BY `Blood Type`
                    ORDER BY total DESC
                    LIMIT 1
                """, (matched,))
                row = cursor.fetchone()
                if row:
                    dispatcher.utter_message(
                        text=f"Blood group with highest {matched.title()} cases: {row[0]} ({row[1]} patients)"
                    )

            # oldest patient
            elif "oldest patient" in text:
                cursor.execute("SELECT Name, Age FROM health_data ORDER BY Age DESC LIMIT 1")
                row = cursor.fetchone()
                dispatcher.utter_message(text=f"Oldest patient: {str(row[0]).title()} ({row[1]} years)")

            # youngest patient
            elif "youngest patient" in text:
                cursor.execute("SELECT Name, Age FROM health_data ORDER BY Age ASC LIMIT 1")
                row = cursor.fetchone()
                dispatcher.utter_message(text=f"Youngest patient: {str(row[0]).title()} ({row[1]} years)")

            # top 10 oldest
            elif "top 10" in text and any(w in text for w in ["oldest", "age"]):
                cursor.execute("SELECT Name, Age, Gender FROM health_data ORDER BY Age DESC LIMIT 10")
                rows     = cursor.fetchall()
                response = "Top 10 oldest patients:\n"
                for i, row in enumerate(rows, 1):
                    response += f"{i}. {str(row[0]).title()} — {row[1]} yrs ({str(row[2]).title()})\n"
                dispatcher.utter_message(text=response)

            # top 10 highest billing
            elif "top 10" in text and any(w in text for w in ["billing", "highest", "bill"]):
                cursor.execute(
                    "SELECT Name, `Billing Amount`, `Medical Condition` "
                    "FROM health_data ORDER BY `Billing Amount` DESC LIMIT 10"
                )
                rows     = cursor.fetchall()
                response = "Top 10 highest billing patients:\n"
                for i, row in enumerate(rows, 1):
                    response += f"{i}. {str(row[0]).title()} — ₹{round(float(row[1]),2)} ({str(row[2]).title()})\n"
                dispatcher.utter_message(text=response)

            # most common disease
            elif any(p in text for p in ["most common disease", "most common condition"]):
                cursor.execute(
                    "SELECT `Medical Condition`, COUNT(*) as cnt "
                    "FROM health_data GROUP BY `Medical Condition` ORDER BY cnt DESC LIMIT 1"
                )
                row = cursor.fetchone()
                dispatcher.utter_message(text=f"Most common disease: {row[0]} ({row[1]} patients)")

            # most prescribed
            elif any(p in text for p in ["most prescribed", "most common medication"]):
                cursor.execute(
                    "SELECT Medication, COUNT(*) as cnt "
                    "FROM health_data GROUP BY Medication ORDER BY cnt DESC LIMIT 1"
                )
                row = cursor.fetchone()
                dispatcher.utter_message(text=f"Most prescribed medication: {row[0]} ({row[1]} patients)")

            # doctor with most patients
            elif any(p in text for p in ["doctor handles", "doctor with most", "which doctor"]):
                cursor.execute(
                    "SELECT Doctor, COUNT(*) as cnt "
                    "FROM health_data GROUP BY Doctor ORDER BY cnt DESC LIMIT 1"
                )
                row = cursor.fetchone()
                dispatcher.utter_message(
                    text=f"Doctor with most patients: {str(row[0]).title()} ({row[1]} patients)"
                )

            # hospital with most urgent
            elif any(p in text for p in ["hospital has most urgent", "hospital with most urgent", "which hospital has most"]):
                cursor.execute(
                    "SELECT Hospital, COUNT(*) as cnt FROM health_data "
                    "WHERE LOWER(`Admission Type`) = 'urgent' "
                    "GROUP BY Hospital ORDER BY cnt DESC LIMIT 1"
                )
                row = cursor.fetchone()
                dispatcher.utter_message(
                    text=f"Hospital with most urgent admissions: {str(row[0]).title()} ({row[1]} admissions)"
                )

            # average age
            elif "average age" in text:
                matched = next((c for c in valid_conditions if c in text), None)
                if matched:
                    cursor.execute(
                        "SELECT AVG(Age) FROM health_data WHERE LOWER(`Medical Condition`) = %s", (matched,)
                    )
                    avg = cursor.fetchone()[0]
                    dispatcher.utter_message(
                        text=f"Average age of {matched.title()} patients: {round(avg, 2)} years"
                    )
                else:
                    cursor.execute("SELECT AVG(Age) FROM health_data")
                    avg = cursor.fetchone()[0]
                    dispatcher.utter_message(text=f"Average age of all patients: {round(avg, 2)} years")

            # average billing
            elif any(p in text for p in ["average billing", "average bill"]):
                matched = next((c for c in valid_conditions if c in text), None)
                if matched:
                    cursor.execute(
                        "SELECT AVG(`Billing Amount`) FROM health_data WHERE LOWER(`Medical Condition`) = %s",
                        (matched,)
                    )
                    avg = cursor.fetchone()[0]
                    dispatcher.utter_message(
                        text=f"Average billing for {matched.title()} patients: ₹{round(avg, 2)}"
                    )
                else:
                    cursor.execute("SELECT AVG(`Billing Amount`) FROM health_data")
                    avg = cursor.fetchone()[0]
                    dispatcher.utter_message(text=f"Average billing for all patients: ₹{round(avg, 2)}")

            # compare male vs female
            elif any(p in text for p in ["compare male and female", "compare female and male"]):
                matched = next((c for c in valid_conditions if c in text), None)
                if matched:
                    cursor.execute(
                        "SELECT COUNT(*) FROM health_data WHERE LOWER(Gender)='male' AND LOWER(`Medical Condition`)=%s",
                        (matched,)
                    )
                    mc = cursor.fetchone()[0]
                    cursor.execute(
                        "SELECT COUNT(*) FROM health_data WHERE LOWER(Gender)='female' AND LOWER(`Medical Condition`)=%s",
                        (matched,)
                    )
                    fc = cursor.fetchone()[0]
                    dispatcher.utter_message(text=f"{matched.title()} cases — Male: {mc}, Female: {fc}")
                else:
                    cursor.execute("SELECT COUNT(*) FROM health_data WHERE LOWER(Gender)='male'")
                    mc = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM health_data WHERE LOWER(Gender)='female'")
                    fc = cursor.fetchone()[0]
                    dispatcher.utter_message(text=f"Total — Male: {mc}, Female: {fc}")

            # compare two conditions
            elif "compare" in text:
                found = [c for c in valid_conditions if c in text]
                if len(found) >= 2:
                    response = "Condition Comparison:\n"
                    for cond in found:
                        cursor.execute(
                            "SELECT COUNT(*) FROM health_data WHERE LOWER(`Medical Condition`) = %s", (cond,)
                        )
                        cnt = cursor.fetchone()[0]
                        response += f"{cond.title()}: {cnt} patients\n"
                    dispatcher.utter_message(text=response)
                else:
                    dispatcher.utter_message(text="Please name at least two conditions to compare.")

            else:
                dispatcher.utter_message(
                    text="Try: 'oldest patient', 'average age of cancer patients', "
                         "'top 10 highest billing', 'which blood group has most cancer cases', etc."
                )

        except Exception as e:
            dispatcher.utter_message(text=f"Database error: {str(e)}")
        finally:
            cursor.close()
            conn.close()

        return []


class ActionKeywordFallback(Action):

    def name(self) -> Text:
        return "action_keyword_fallback"

    def run(self, dispatcher, tracker, domain):
        text   = tracker.latest_message.get("text", "")
        text_l = text.lower()

        print(f"FALLBACK DEBUG — intent: {tracker.latest_message.get('intent')}, text: {text_l}")

        if is_chart_query(text_l):
            return ActionChartData().run(dispatcher, tracker, domain)

        analytics_keywords = [
            "oldest patient", "youngest patient",
            "average age", "average billing", "average bill",
            "most common disease", "most common condition",
            "most prescribed", "most common medication",
            "doctor handles", "doctor with most", "which doctor",
            "hospital has most urgent", "hospital with most urgent",
            "top 10", "highest billing",
        ]
        count_keywords = ["how many", "count", "total", "number of", "how much"]
        list_keywords  = ["show", "list", "display", "give me", "are there",
                          "is there", "any", "available"]

        if any(k in text_l for k in analytics_keywords):
            return ActionHealthcareAnalytics().run(dispatcher, tracker, domain)

        # admission comparison — 2+ admission types + compare word
        admission_count = sum(1 for w in ["urgent", "emergency", "elective"] if w in text_l)
        compare_words   = any(k in text_l for k in ["compare", "vs", "versus", "and", "difference"])
        if admission_count >= 2 and compare_words:
            return ActionCompareAdmissions().run(dispatcher, tracker, domain)

        # condition comparison — 2+ conditions + compare word
        valid_conds  = ["cancer","diabetes","hypertension","asthma","arthritis","obesity"]
        cond_count   = sum(1 for c in valid_conds if c in text_l)
        if cond_count >= 2 and any(k in text_l for k in ["compare","vs","versus","difference"]):
            return ActionHealthcareAnalytics().run(dispatcher, tracker, domain)

        # blood type comparison
        compare_keywords_bt = ["more than","compare","vs","versus","difference between","which is higher","which is more"]
        if any(k in text_l for k in compare_keywords_bt):
            return ActionCompareBloodTypes().run(dispatcher, tracker, domain)

        # most common blood type — only if "blood" is mentioned
        if any(k in text_l for k in ["most common blood","most frequent blood","which blood type","which blood group"]):
            return ActionMostCommonBloodType().run(dispatcher, tracker, domain)

        elif any(k in text_l for k in count_keywords):
            return ActionCountPatients().run(dispatcher, tracker, domain)

        elif any(k in text_l for k in list_keywords):
            return ActionListPatients().run(dispatcher, tracker, domain)

        dispatcher.utter_message(
            text="I didn't understand. Try asking about patients, blood types, conditions, medications, or request a chart/graph."
        )
        return []