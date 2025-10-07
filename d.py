from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT

# Create the document
doc = Document()

# Define title and authors
title = "Harnessing Artificial Intelligence and EMR Data to Derive Optimized HIV Treatment Protocols in Support of PEPFAR’s Third 95 Goal"
authors = "Anthony Nwokoma, Temitayo Oladimeji"
institution = "[Your Institution/Organization]"
email = "[Your Email Address]"

# Add title
title_paragraph = doc.add_paragraph()
title_run = title_paragraph.add_run(title)
title_run.bold = True
title_run.font.size = Pt(14)
title_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

# Add authors
authors_paragraph = doc.add_paragraph()
authors_run = authors_paragraph.add_run(authors)
authors_run.font.size = Pt(12)
authors_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

# Add institution and email
institution_paragraph = doc.add_paragraph()
institution_run = institution_paragraph.add_run(f"{institution}\n{email}")
institution_run.font.size = Pt(11)
institution_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

doc.add_paragraph()  # Empty line

# Add abstract body
abstract_text = """
Background:
As Nigeria works toward achieving PEPFAR and CDC’s third 95 target—ensuring that 95% of all diagnosed individuals living with HIV attain sustained viral suppression—there remains a critical need to optimize the use of available data to support evidence-based interventions. One underutilized asset is the rich trove of Electronic Medical Records (EMR) accumulated across national HIV programs, which holds latent insights into successful treatment patterns, adherence behaviors, and regimen outcomes.

Objective:
This study proposes the development of a scalable AI framework that leverages existing EMR data to derive best practices, refine treatment regimens, and generate adaptive treatment charts personalized to the Nigerian HIV context.

Methods:
The proposed research will involve:
(1) Aggregating anonymized EMR datasets from supported treatment facilities across Nigeria;
(2) Training AI models (using NLP and machine learning) on longitudinal treatment data, focusing on factors influencing viral suppression;
(3) Identifying patterns in regimen success rates, patient responses, and treatment interruptions;
(4) Creating AI-informed clinical decision support tools that suggest optimal treatment paths based on historical data trends.

Anticipated Outcomes:
The system is expected to:
- Recommend time-tested and data-driven ART regimens tailored to individual profiles;
- Enhance early warning signals for treatment failure or adherence decline;
- Support clinicians with intelligent treatment charting that improves patient outcomes and reduces loss to follow-up.

Significance:
This approach not only strengthens national HIV treatment programs but also builds a framework that can be scaled to other diseases and epidemics, such as tuberculosis, hepatitis, or maternal health challenges—particularly where AI-trainable public health datasets are available. By transforming static EMR repositories into dynamic intelligence platforms, this work supports Nigeria’s leadership in innovative epidemic response.

Conclusion:
Artificial Intelligence, when trained on localized EMR data, offers a transformative opportunity to accelerate progress toward the third 95 of the HIV cascade. This research represents a pathway to more personalized, data-informed, and sustainable public health decision-making for HIV and beyond.
"""
doc.add_paragraph(abstract_text.strip())

# Save the document
doc_path = "/mnt/data/Nwokoma_Oladimeji_IRCE_Abstract.docx"
doc.save(doc_path)

doc_path
