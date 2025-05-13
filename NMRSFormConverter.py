import tkinter as tk
from tkinter import ttk, Listbox, Text, END, VERTICAL, messagebox
import mysql.connector
from bs4 import BeautifulSoup
from openpyxl import Workbook
import json
import os
import re
import uuid

def to_camel_case_id(label):
    # Remove non-alphanumeric, split by space, lowercase first, capitalize rest, join with _
    words = re.sub(r'[^a-zA-Z0-9 ]', '', label).strip().split()
    if not words:
        return "q"
    camel = words[0].lower() + ''.join(w.capitalize() for w in words[1:])
    return camel

class NMRSFormConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("NMRS HTML Form Converter")
        self.root.geometry("1400x800")
        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(1, weight=1)

        # DB Connection Frame
        self.db_frame = ttk.LabelFrame(root, text="Database Connection")
        self.db_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self._add_db_widgets()

        # Concept Search Frame
        self.concept_frame = ttk.LabelFrame(root, text="Concept Search/Info")
        self.concept_frame.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        self._add_concept_widgets()

        # Forms List Frame (left)
        self.forms_frame = ttk.LabelFrame(root, text="Available Forms")
        self.forms_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.forms_frame.columnconfigure(0, weight=1)
        self.forms_frame.rowconfigure(1, weight=1)

        self.convert_btn = ttk.Button(self.forms_frame, text="Convert Selected Form", command=self.convert_selected_form)
        self.convert_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.forms_listbox = Listbox(self.forms_frame, width=60)
        self.forms_listbox.grid(row=1, column=0, sticky="nsew")
        self.forms_scrollbar = ttk.Scrollbar(self.forms_frame, orient=VERTICAL, command=self.forms_listbox.yview)
        self.forms_scrollbar.grid(row=1, column=1, sticky="ns")
        self.forms_listbox.config(yscrollcommand=self.forms_scrollbar.set)
        self.forms_listbox.bind('<<ListboxSelect>>', self.on_form_select)

        # XML Data Display Frame (right)
        self.xml_frame = ttk.LabelFrame(root, text="Form XML (xml_data)")
        self.xml_frame.grid(row=1, column=1, rowspan=2, padx=10, pady=10, sticky="nsew")
        self.xml_frame.rowconfigure(0, weight=1)
        self.xml_frame.columnconfigure(0, weight=1)
        self.xml_text = Text(self.xml_frame, wrap="none")
        self.xml_text.grid(row=0, column=0, sticky="nsew")
        self.xml_scrollbar = ttk.Scrollbar(self.xml_frame, orient=VERTICAL, command=self.xml_text.yview)
        self.xml_scrollbar.grid(row=0, column=1, sticky="ns")
        self.xml_text.config(yscrollcommand=self.xml_scrollbar.set)
        self.xml_text.config(state="disabled")

        self.connection = None
        self.concept_map = {}      # {concept_id: {"uuid": ..., "name": ...}}
        self.forms = []
        self.selected_form_index = None
        self.option_sets = {}

        self.connect_to_db(auto=True)

    def _add_db_widgets(self):
        labels = ["Host", "User", "Password", "Database"]
        self.db_entries = {}
        defaults = {"host": "localhost", "user": "root", "password": "root", "database": "openmrs"}
        for i, label in enumerate(labels):
            ttk.Label(self.db_frame, text=label).grid(row=i, column=0, sticky="w")
            entry = ttk.Entry(self.db_frame, show="*" if label == "Password" else "")
            entry.insert(0, defaults[label.lower()])
            entry.grid(row=i, column=1, padx=5, pady=2)
            self.db_entries[label.lower()] = entry
        self.connect_btn = ttk.Button(self.db_frame, text="Connect", command=self.connect_to_db)
        self.connect_btn.grid(row=len(labels), column=0, columnspan=2, pady=5)

    def _add_concept_widgets(self):
        self.concept_search_var = tk.StringVar()
        self.concept_search_entry = ttk.Entry(self.concept_frame, textvariable=self.concept_search_var, width=40)
        self.concept_search_entry.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.concept_search_entry.bind("<Return>", self.on_concept_search)
        self.concept_search_btn = ttk.Button(self.concept_frame, text="Search", command=self.on_concept_search)
        self.concept_search_btn.grid(row=0, column=1, padx=5, pady=5)
        self.concept_info_text = Text(self.concept_frame, height=10, width=70, wrap="word")
        self.concept_info_text.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        self.concept_info_text.config(state="disabled")

    def connect_to_db(self, auto=False):
        try:
            self.connection = mysql.connector.connect(
                host=self.db_entries["host"].get(),
                user=self.db_entries["user"].get(),
                password=self.db_entries["password"].get(),
                database=self.db_entries["database"].get()
            )
            if not auto:
                messagebox.showinfo("Success", "Connected to database.")
            self.fetch_forms()
        except mysql.connector.Error as err:
            if not auto:
                messagebox.showerror("Error", f"Database connection failed:\n{err}")

    def fetch_forms(self):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT h.form_id, f.name 
            FROM htmlformentry_html_form h
            JOIN form f ON h.form_id = f.form_id
        """)
        self.forms = cursor.fetchall()
        self.forms_listbox.delete(0, END)
        for form in self.forms:
            self.forms_listbox.insert(END, f"{form['form_id']}: {form['name']}")
        cursor.close()

    def on_form_select(self, event):
        selection = event.widget.curselection()
        if not selection:
            self.selected_form_index = None
            self.xml_text.config(state="normal")
            self.xml_text.delete(1.0, END)
            self.xml_text.config(state="disabled")
            return
        self.selected_form_index = selection[0]
        form = self.forms[self.selected_form_index]
        xml_data = self.fetch_form_html(form['form_id'])
        self.xml_text.config(state="normal")
        self.xml_text.delete(1.0, END)
        self.xml_text.insert(END, xml_data if xml_data else "(No xml_data found)")
        self.xml_text.config(state="disabled")

    def convert_selected_form(self):
        if self.selected_form_index is None:
            messagebox.showwarning("No Selection", "Please select a form to convert.")
            return
        form = self.forms[self.selected_form_index]
        html = self.fetch_form_html(form['form_id'])
        if not html:
            messagebox.showerror("Error", "No HTML found for this form.")
            return
        soup = BeautifulSoup(html, 'html.parser')
        concept_ids = set()
        for obs in soup.find_all("obs"):
            cid = obs.get("conceptid")
            if cid and cid.isdigit():
                concept_ids.add(int(cid))
            # Also collect answerConceptIds
            answer_ids = []
            if obs.get("answers"):
                answer_ids = [a.strip() for a in obs.get("answers").split(",")]
            elif obs.get("answerconceptids"):
                answer_ids = [a.strip() for a in obs.get("answerconceptids").split(",")]
            elif obs.get("answerconceptid"):
                answer_ids = [obs.get("answerconceptid").strip()]
            for aid in answer_ids:
                if aid.isdigit():
                    concept_ids.add(int(aid))
        # Now fetch all concepts at once
        self.fetch_concepts_from_db(concept_ids)
        self.generate_outputs(soup, form['name'])

    def fetch_form_html(self, form_id):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT xml_data FROM htmlformentry_html_form WHERE form_id = %s", (form_id,))
        row = cursor.fetchone()
        cursor.close()
        return row['xml_data'] if row else ""

    def fetch_concepts_from_db(self, concept_ids):
        if not concept_ids:
            self.concept_map = {}
            return
        cursor = self.connection.cursor(dictionary=True)
        placeholders = ",".join(["%s"] * len(concept_ids))
        cursor.execute(
            f"SELECT c.concept_id, c.uuid, n.name FROM concept c JOIN concept_name n ON c.concept_id = n.concept_id AND n.locale = 'en' WHERE c.concept_id IN ({placeholders})",
            list(concept_ids)
        )
        self.concept_map = {row["concept_id"]: {"uuid": row["uuid"], "name": row["name"]} for row in cursor.fetchall()}
        cursor.close()

    def on_concept_search(self, event=None):
        search = self.concept_search_var.get().strip()
        self.concept_info_text.config(state="normal")
        self.concept_info_text.delete(1.0, END)
        if not search:
            self.concept_info_text.config(state="disabled")
            return
        cursor = self.connection.cursor(dictionary=True)
        results = []
        # Numeric or UUID search
        if re.fullmatch(r'\d+', search):
            cursor.execute("""
                SELECT c.concept_id, c.uuid, n.name, d.description
                FROM concept c
                LEFT JOIN concept_name n ON c.concept_id = n.concept_id AND n.locale='en'
                LEFT JOIN concept_description d ON c.concept_id = d.concept_id AND d.locale='en'
                WHERE c.concept_id = %s
                LIMIT 1
            """, (int(search),))
            results = cursor.fetchall()
        elif re.fullmatch(r'[0-9a-fA-F-]{36}', search):
            cursor.execute("""
                SELECT c.concept_id, c.uuid, n.name, d.description
                FROM concept c
                LEFT JOIN concept_name n ON c.concept_id = n.concept_id AND n.locale='en'
                LEFT JOIN concept_description d ON c.concept_id = d.concept_id AND d.locale='en'
                WHERE c.uuid = %s
                LIMIT 1
            """, (search,))
            results = cursor.fetchall()
        else:
            # Text search in name and description
            cursor.execute("""
                SELECT c.concept_id, c.uuid, n.name, d.description
                FROM concept c
                LEFT JOIN concept_name n ON c.concept_id = n.concept_id AND n.locale='en'
                LEFT JOIN concept_description d ON c.concept_id = d.concept_id AND d.locale='en'
                WHERE n.name LIKE %s OR d.description LIKE %s
                LIMIT 20
            """, (f"%{search}%", f"%{search}%"))
            results = cursor.fetchall()
        if results:
            for row in results:
                self.concept_info_text.insert(END, f"Concept ID: {row['concept_id']}\nUUID: {row['uuid']}\nName: {row.get('name','')}\nDescription: {row.get('description','')}\n{'-'*40}\n")
        else:
            self.concept_info_text.insert(END, "No concept found.")
        cursor.close()
        self.concept_info_text.config(state="disabled")

    def generate_outputs(self, soup, form_name):
        form_uuid = str(uuid.uuid4())
        json_form = {
            "name": form_name,
            "uuid": form_uuid,
            "processor": "EncounterFormProcessor",
            "version": "1.0",
            "description": "",
            "pages": []
        }
        wb = Workbook()
        ws = wb.active
        ws.title = "Form"
        ws.append([
            "Page", "Section", "Question", "Datatype", "Mandatory", "Question ID",
            "External ID", "Rendering", "OptionSet name", "Upper limit", "Lower limit"
        ])
        option_sets = {}

        fieldsets = soup.find_all("fieldset")
        if not fieldsets:
            fieldsets = [soup]

        id_counter = 1  # <-- Use this for incremental numbering

        for fieldset in fieldsets:
            legend = fieldset.find("legend")
            section_label = legend.text.strip() if legend else None

            obs_tags = fieldset.find_all("obs")
            if not obs_tags:
                continue

            page_label = section_label or self.concept_map.get(
                int(obs_tags[0].get("conceptid", "0")), {}).get("name", "Page")

            first_obs_cid = obs_tags[0].get("conceptid")
            section_label_final = section_label or (
                self.concept_map.get(int(first_obs_cid), {}).get("name", "Section")
                if first_obs_cid and first_obs_cid.isdigit() else "Section"
            )

            section = {
                "label": section_label_final,
                "questions": []
            }

            for obs in obs_tags:
                cid = obs.get("conceptid")
                if not cid or not cid.isdigit():
                    continue
                cid = int(cid)
                concept_info = self.concept_map.get(cid, {"uuid": "", "name": f"Concept {cid}"})
                label = concept_info["name"]
                uuid_val = concept_info["uuid"]
                base_id = to_camel_case_id(label)
                qid = f"{base_id}_{id_counter}"
                id_counter += 1

                # --- Special handling for enable_clin_control + checkbox ---
                parent_div = obs.find_parent("div", class_="enable_clin_control")
                if parent_div and obs.get("style") == "checkbox":
                    rendering = "radio"
                    checked = obs.get("value", "false").lower() == "true"
                    answers = [
                        {"label": label, "concept": uuid_val},
                        {"label": "None", "concept": ""}
                    ]
                    question = {
                        "id": qid,
                        "label": label,
                        "type": "obs",
                        "questionOptions": {
                            "concept": uuid_val,
                            "rendering": rendering,
                            "answers": answers,
                            "default": "" if not checked else uuid_val
                        }
                    }
                    section["questions"].append(question)
                    ws.append([
                        page_label, section_label_final, label, "Coded", "No", qid,
                        "", rendering, "", "", ""
                    ])
                    continue

                rendering = obs.get("type", "text")
                if obs.get("answers") or obs.get("answerconceptids") or obs.get("answerconceptid"):
                    rendering = "select"
                elif obs.get("style") == "checkbox":
                    rendering = "radio"
                elif obs.get("type") == "number":
                    rendering = "number"
                elif obs.get("type") == "date":
                    rendering = "date"

                data_type = "Coded" if rendering == "select" else "Text"
                mandatory = obs.get("required", "false").lower() == "true"
                option_set_name = ""
                upper_limit = obs.get("maxValue", "")
                lower_limit = obs.get("minValue", "")

                label_td = obs.find_parent("td")
                if label_td:
                    prev_td = label_td.find_previous_sibling("td")
                    if prev_td and prev_td.text.strip():
                        label = prev_td.text.strip()
                        base_id = to_camel_case_id(label)
                        qid = f"{base_id}_{id_counter-1}"  # keep id_counter in sync

                question = {
                    "id": qid,
                    "label": label,
                    "type": "obs",
                    "questionOptions": {
                        "concept": uuid_val,
                        "rendering": rendering
                    }
                }

                # --- Validators using AMPATH helpers ---
                validators = []
                if obs.get("maxValue"):
                    validators.append({
                        "type": "max",
                        "value": float(obs.get("maxValue")),
                        "message": f"Value must be <= {obs.get('maxValue')}"
                    })
                    question["questionOptions"]["max"] = float(obs.get("maxValue"))
                if obs.get("minValue"):
                    validators.append({
                        "type": "min",
                        "value": float(obs.get("minValue")),
                        "message": f"Value must be >= {obs.get('minValue')}"
                    })
                    question["questionOptions"]["min"] = float(obs.get("minValue"))
                if obs.get("pattern"):
                    validators.append({
                        "type": "regex",
                        "value": obs.get("pattern"),
                        "message": "Invalid format"
                    })
                if obs.get("required", "false").lower() == "true":
                    validators.append({
                        "type": "required",
                        "message": "This field is required"
                    })
                if validators:
                    question["validators"] = validators

                # --- Calculations and Expressions (AMPATH style) ---
                if obs.get("onchange") and "calcBMI" in obs.get("onchange"):
                    question["calculate"] = {
                        "calculateExpression": "!isEmpty(Height_CM) && !isEmpty(Weight_CM) ? calcBMI(Height_CM,Weight_CM): '0'"
                    }
                    question["hide"] = {
                        "hideWhenExpression": "isEmpty(Height_CM) || isEmpty(Weight_CM)"
                    }

                # --- Data Source (AMPATH) ---
                if obs.get("data-source"):
                    question["dataSource"] = obs.get("data-source")

                # --- Answers (for select) ---
                answers = []
                if obs.get("answers"):
                    answer_ids = [a.strip() for a in obs.get("answers").split(",")]
                    for aid in answer_ids:
                        if aid.isdigit():
                            aid_int = int(aid)
                            ans_uuid = self.concept_map.get(aid_int, {"uuid": ""})["uuid"]
                            ans_label = self.concept_map.get(aid_int, {"name": f"Concept {aid}"})["name"]
                            answers.append({"label": ans_label, "concept": ans_uuid})
                        else:
                            answers.append({"label": aid, "concept": ""})
                elif obs.get("answerconceptids") and obs.get("answerlabels"):
                    ids = [a.strip() for a in obs.get("answerconceptids").split(",")]
                    labels = [l.strip() for l in obs.get("answerlabels").split(",")]
                    for aid, l in zip(ids, labels):
                        if aid.isdigit():
                            aid_int = int(aid)
                            ans_uuid = self.concept_map.get(aid_int, {"uuid": ""})["uuid"]
                            answers.append({"label": l, "concept": ans_uuid})
                        else:
                            answers.append({"label": l, "concept": ""})
                elif obs.get("answerconceptid") and obs.get("answerlabel"):
                    aid = obs.get("answerconceptid")
                    l = obs.get("answerlabel")
                    if aid and aid.isdigit():
                        aid_int = int(aid)
                        ans_uuid = self.concept_map.get(aid_int, {"uuid": ""})["uuid"]
                        answers.append({"label": l, "concept": ans_uuid})
                    else:
                        answers.append({"label": l, "concept": ""})
                if answers:
                    option_set_name = f"{label.lower().replace(' ', '_')}_options"
                    question["questionOptions"]["answers"] = answers
                    for ans in answers:
                        option_sets.setdefault(option_set_name, []).append((ans["label"], ans["concept"]))

                section["questions"].append(question)
                ws.append([
                    page_label, section_label_final, label, data_type, "Yes" if mandatory else "No", qid,
                    "", rendering, option_set_name, upper_limit, lower_limit
                ])
            if section["questions"]:
                json_form["pages"].append({
                    "label": page_label,
                    "sections": [section]
                })

        # --- OptionSets Sheet ---
        ws2 = wb.create_sheet("OptionSets")
        ws2.append(["OptionSet name", "Answers", "External ID"])
        for opt_name, values in option_sets.items():
            for ans, extid in values:
                ws2.append([opt_name, ans, extid])

        # --- Save ---
        output_dir = os.path.join(os.getcwd(), "converted")
        os.makedirs(output_dir, exist_ok=True)
        excel_path = os.path.join(output_dir, f"{form_name}_converted.xlsx")
        json_path = os.path.join(output_dir, f"{form_name}_converted.json")
        wb.save(excel_path)
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(json_form, jf, indent=2)
        messagebox.showinfo("Done", f"Files generated in {output_dir}")

if __name__ == "__main__":
    root = tk.Tk()
    app = NMRSFormConverter(root)
    root.mainloop()