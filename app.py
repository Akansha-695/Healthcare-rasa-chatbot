import json
import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import mysql.connector
from io import BytesIO
import uuid


def show_chart(fig):
    st.plotly_chart(
        fig,
        key=f"chart_{uuid.uuid4()}",
        width='stretch'
    )

st.set_page_config(
    page_title="Healthcare Assistant",
    page_icon="🩺",
    layout="wide"
)

st.title("🩺 Healthcare Assistant")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_filters" not in st.session_state:
    st.session_state.last_filters = {}


def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password=os.environ.get("DB_PASSWORD", ""),
        database="healthcaree",
        use_pure=True
    )


def convert_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Patients")
    return output.getvalue()



def get_full_data(filters):
    """Query MySQL with no row limit for Excel download."""
    conn   = get_db_connection()
    cursor = conn.cursor()

    conditions = []
    params     = []

    if "gender" in filters:
        conditions.append("LOWER(Gender) = LOWER(%s)")
        params.append(filters["gender"])

    if "blood_type" in filters:
        conditions.append("LOWER(`Blood Type`) = LOWER(%s)")
        params.append(filters["blood_type"])

    # Negated blood type
    if "exclude_blood_type" in filters:
        conditions.append("LOWER(`Blood Type`) != LOWER(%s)")
        params.append(filters["exclude_blood_type"])

    if "medical_condition" in filters:
        mc = filters["medical_condition"]
        if isinstance(mc, list):
            placeholders = ",".join(["%s"] * len(mc))
            conditions.append(f"`Medical Condition` IN ({placeholders})")
            params.extend(mc)
        else:
            conditions.append("LOWER(`Medical Condition`) = LOWER(%s)")
            params.append(mc)

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

    where = " AND ".join(conditions) if conditions else "1=1"
    query = (
        f"SELECT Name, Age, Gender, `Blood Type`, `Medical Condition`, Doctor, Hospital, "
        f"`Admission Type`, Medication, `Test Results` "
        f"FROM health_data WHERE {where}"
    )

    cursor.execute(query, params)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    return pd.DataFrame(rows, columns=[
        "Name", "Age", "Gender", "Blood Type", "Medical Condition",
        "Doctor", "Hospital", "Admission Type", "Medication", "Test Results"
    ])


def parse_filters_from_text(text):
    """Parse filters from user message to use for full data download."""
    filters = {}
    text_lower = text.lower()

    # Check negated blood type first
    import re
    negation_patterns = [
        r"not\s+be\s+([ab][\+\-]|ab[\+\-]|o[\+\-])",
        r"should\s+not\s+be\s+([ab][\+\-]|ab[\+\-]|o[\+\-])",
        r"other\s+than\s+([ab][\+\-]|ab[\+\-]|o[\+\-])",
        r"except\s+([ab][\+\-]|ab[\+\-]|o[\+\-])",
        r"not\s+([ab][\+\-]|ab[\+\-]|o[\+\-])",
    ]
    spelled_neg_patterns = [
        r"not\s+be\s+(b\s+positive|b\s+negative|a\s+positive|a\s+negative|ab\s+positive|ab\s+negative|o\s+positive|o\s+negative)",
        r"should\s+not\s+be\s+(b\s+positive|b\s+negative|a\s+positive|a\s+negative|ab\s+positive|ab\s+negative|o\s+positive|o\s+negative)",
        r"other\s+than\s+(b\s+positive|b\s+negative|a\s+positive|a\s+negative|ab\s+positive|ab\s+negative|o\s+positive|o\s+negative)",
        r"not\s+(b\s+positive|b\s+negative|a\s+positive|a\s+negative|ab\s+positive|ab\s+negative|o\s+positive|o\s+negative)",
    ]
    spelled_map = {
        "ab positive": "AB+", "ab negative": "AB-",
        "a positive":  "A+",  "a negative":  "A-",
        "b positive":  "B+",  "b negative":  "B-",
        "o positive":  "O+",  "o negative":  "O-",
    }
    found_negation = False
    for pattern in negation_patterns:
        m = re.search(pattern, text_lower)
        if m:
            filters["exclude_blood_type"] = m.group(1).upper()
            found_negation = True
            break
    if not found_negation:
        for pattern in spelled_neg_patterns:
            m = re.search(pattern, text_lower)
            if m:
                phrase = m.group(1).strip()
                val = spelled_map.get(phrase)
                if val:
                    filters["exclude_blood_type"] = val
                    found_negation = True
                break

    # Positive blood type only if no negation found
    if not found_negation:
        spelled_blood = {
            "ab positive": "AB+", "ab negative": "AB-",
            "a positive":  "A+",  "a negative":  "A-",
            "b positive":  "B+",  "b negative":  "B-",
            "o positive":  "O+",  "o negative":  "O-",
        }
        # Try spelled form first
        matched_blood = None
        for phrase, value in spelled_blood.items():
            if phrase in text_lower:
                matched_blood = value
                break
        # Fall back to symbol with word-boundary check
        if not matched_blood:
            sym_match = re.search(r'(?<![a-z])(ab[+\-]|a[+\-]|b[+\-]|o[+\-])(?![a-z])', text_lower)
            if sym_match:
                matched_blood = sym_match.group(1).upper()
        if matched_blood:
            filters["blood_type"] = matched_blood

    # Gender — handle both male AND female
    gender_map = {
        "female": "Female", "females": "Female", "women": "Female",
        "woman": "Female", "ladies": "Female", "femles": "Female",
        "male": "Male", "males": "Male", "men": "Male",
        "gents": "Male", "gent": "Male"
    }
    words = text_lower.split()
    genders_found = set()
    for word in words:
        if word in gender_map:
            genders_found.add(gender_map[word])
    if len(genders_found) == 1:
        filters["gender"] = genders_found.pop()
    # If both genders found, no gender filter (show all)

    valid_conditions = ["Cancer", "Diabetes", "Obesity", "Hypertension", "Asthma", "Arthritis"]
    found = [c for c in valid_conditions if c.lower() in text_lower]
    if found:
        filters["medical_condition"] = found

    for admission in ["Urgent", "Emergency", "Elective"]:
        if admission.lower() in text_lower:
            filters["admission_type"] = admission
            break

    for med in ["Paracetamol", "Ibuprofen", "Aspirin", "Penicillin", "Lipitor"]:
        if med.lower() in text_lower:
            filters["medication"] = med
            break

    if "inconclusive" in text_lower:
        filters["test_result"] = "Inconclusive"
    elif "abnormal" in text_lower:
        filters["test_result"] = "Abnormal"
    elif "normal" in text_lower:
        filters["test_result"] = "Normal"

    return filters


def render_chart(chart_data: dict):
    """Render a Plotly chart from chart_data returned by ActionChartData."""
    title      = chart_data.get("title", "Chart")
    chart_type = chart_data.get("chart_type", "bar")
    split_by   = chart_data.get("split_by")
    group_by   = chart_data.get("group_by", "")
    data       = chart_data.get("data", {})

    if not data:
        st.warning("No data available for this chart.")
        return

    COLORS = px.colors.qualitative.Set2
    LAYOUT = dict(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white", size=12),
        title_font=dict(size=16),
        margin=dict(l=10, r=10, t=50, b=10),
    )

    # Long-label fields: use horizontal bars
    horizontal = group_by in ("Hospital", "Doctor")

    if split_by == "Gender":
        labels  = list(data.keys())
        males   = [data[l].get("Male", 0)   for l in labels]
        females = [data[l].get("Female", 0) for l in labels]

        if chart_type == "pie":
            col1, col2 = st.columns(2)
            with col1:
                fig = go.Figure(go.Pie(
                    labels=labels, values=males, hole=0.3,
                    marker=dict(colors=COLORS),
                ))
                fig.update_layout(title_text=f"{title} — Male", **LAYOUT)
                st.plotly_chart(fig, width='stretch', key=f"chart_{uuid.uuid4()}")
            with col2:
                fig = go.Figure(go.Pie(
                    labels=labels, values=females, hole=0.3,
                    marker=dict(colors=COLORS),
                ))
                fig.update_layout(title_text=f"{title} — Female", **LAYOUT)
                st.plotly_chart(
                fig,
                key=f"chart_{uuid.uuid4()}",
                width='stretch'
                )
        else:
            if horizontal:
                fig = go.Figure()
                fig.add_trace(go.Bar(name="Male",   y=labels, x=males,
                                     orientation="h", marker_color=COLORS[0]))
                fig.add_trace(go.Bar(name="Female", y=labels, x=females,
                                     orientation="h", marker_color=COLORS[1]))
                fig.update_layout(
                    title_text=title, barmode="group",
                    xaxis_title="Count", yaxis_title=group_by,
                    legend_title="Gender", height=max(400, len(labels) * 35),
                    **LAYOUT
                )
            else:
                fig = go.Figure()
                fig.add_trace(go.Bar(name="Male",   x=labels, y=males,
                                     marker_color=COLORS[0]))
                fig.add_trace(go.Bar(name="Female", x=labels, y=females,
                                     marker_color=COLORS[1]))
                fig.update_layout(
                    title_text=title, barmode="group",
                    xaxis_title=group_by, yaxis_title="Count",
                    legend_title="Gender", **LAYOUT
                )
            show_chart(fig)

    else:
        labels = list(data.keys())
        values = list(data.values())

        if chart_type == "pie":
            fig = go.Figure(go.Pie(
                labels=labels, values=values, hole=0.3,
                marker=dict(colors=COLORS),
                textinfo="label+percent",
            ))
            fig.update_layout(title_text=title, **LAYOUT)
            show_chart(fig)

        elif chart_type == "line":
            fig = go.Figure(go.Scatter(
                x=labels, y=values, mode="lines+markers",
                line=dict(color=COLORS[2], width=3),
                marker=dict(size=8),
            ))
            fig.update_layout(
                title_text=title,
                xaxis_title=group_by, yaxis_title="Count",
                **LAYOUT
            )
            show_chart(fig)

        else:  # bar
            bar_colors = [COLORS[i % len(COLORS)] for i in range(len(labels))]
            if horizontal:
                fig = go.Figure(go.Bar(
                    y=labels, x=values, orientation="h",
                    marker_color=bar_colors,
                    text=values, textposition="outside",
                ))
                fig.update_layout(
                    title_text=title,
                    xaxis_title="Count", yaxis_title=group_by,
                    height=max(400, len(labels) * 35),
                    **LAYOUT
                )
            else:
                fig = go.Figure(go.Bar(
                    x=labels, y=values,
                    marker_color=bar_colors,
                    text=values, textposition="outside",
                ))
                fig.update_layout(
                    title_text=title,
                    xaxis_title=group_by, yaxis_title="Count",
                    **LAYOUT
                )
            show_chart(fig)


# ── Display chat history ──────────────────────────────────────────────────────
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            if msg.get("chart_data"):
                st.markdown(f"**{msg.get('content', 'Here is your chart:')}**")
                render_chart(msg["chart_data"])

            elif msg.get("table") is not None:
                st.dataframe(msg["table"], width='stretch')

                if msg.get("filters"):
                    try:
                        full_df    = get_full_data(msg["filters"])
                        excel_data = convert_to_excel(full_df)
                        st.download_button(
                            label=f"⬇️ Download Full Data ({len(full_df)} rows) as Excel",
                            data=excel_data,
                            file_name="patients_full.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"download_{i}"
                        )
                    except Exception as e:
                        st.error(f"Download error: {str(e)}")
            else:
                st.markdown(msg["content"])
        else:
            st.markdown(msg["content"])


# ── Chat input ────────────────────────────────────────────────────────────────
prompt = st.chat_input("Ask about patients, blood groups, diseases, or request a chart...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    payload  = {"sender": "user1", "message": prompt}
    response = requests.post(
        "http://localhost:5005/webhooks/rest/webhook",
        json=payload
    )

    result    = response.json()
    bot_reply = ""

    for item in result:
        if "text" in item:
            bot_reply += item["text"] + "\n"

    bot_reply = bot_reply.strip()

    # ── Check if response is a chart ─────────────────────────────────────────
    if "CHART_DATA:" in bot_reply:
        chart_json_str = bot_reply.split("CHART_DATA:", 1)[1].strip()
        try:
            chart_data = json.loads(chart_json_str)
            with st.chat_message("assistant"):
                st.markdown(f"**{chart_data.get('title', 'Chart')}**")
                render_chart(chart_data)

            st.session_state.messages.append({
                "role":       "assistant",
                "content":    chart_data.get("title", "Chart"),
                "chart_data": chart_data,
            })
        except Exception as e:
            st.error(f"Chart rendering error: {str(e)}")
        st.stop()

    # ── Parse patient rows from bot response ─────────────────────────────────
    patient_rows = []

    for line in bot_reply.split("\n"):
        if line.startswith("-"):
            parts = [x.strip() for x in line.split("|")]
            if len(parts) >= 4:
                patient_rows.append({
                    "Name":       parts[0].replace("-", "").strip(),
                    "Age":        parts[1].replace("Age:", "").strip()        if len(parts) > 1 else "",
                    "Gender":     parts[2].strip()                            if len(parts) > 2 else "",
                    "Blood Type": parts[3].replace("Blood Type:", "").strip() if len(parts) > 3 else "",
                    "Condition":  parts[4].replace("Condition:", "").strip()  if len(parts) > 4 else "",
                    "Doctor":     parts[5].replace("Doctor:", "").strip()     if len(parts) > 5 else "",
                    "Hospital":   parts[6].replace("Hospital:", "").strip()   if len(parts) > 6 else "",
                    "Admission":  parts[7].replace("Admission:", "").strip()  if len(parts) > 7 else "",
                    "Medication": parts[8].replace("Medication:", "").strip() if len(parts) > 8 else "",
                    "Test":       parts[9].replace("Test:", "").strip()       if len(parts) > 9 else "",
                })

    with st.chat_message("assistant"):
        if patient_rows:
            df = pd.DataFrame(patient_rows)
            st.dataframe(df, width='stretch')

            filters = parse_filters_from_text(prompt)

            try:
                full_df    = get_full_data(filters)
                excel_data = convert_to_excel(full_df)
                st.download_button(
                    label=f"⬇️ Download Full Data ({len(full_df)} rows) as Excel",
                    data=excel_data,
                    file_name="patients_full.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_new"
                )
            except Exception as e:
                st.error(f"Download error: {str(e)}")

            st.session_state.messages.append({
                "role":    "assistant",
                "table":   df,
                "filters": filters
            })

        else:
            st.markdown(bot_reply)
            st.session_state.messages.append({
                "role":    "assistant",
                "content": bot_reply
            })