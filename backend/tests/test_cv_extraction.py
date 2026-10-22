import pytest

from app.routers.documents import cv_candidate_fields


@pytest.mark.parametrize(
    ("text", "filename", "first_name", "last_name", "title", "years"),
    [
        (
            "Harpreet Kaur\nSr. Java/ J2EE Developer\n(586) 806-9840\nharprt2830@gmail.com\n"
            "PROFESSIONAL SUMMARY\nHaving 9+ years of experience in Java development.\n"
            "TECHNICAL SKILLS\nJava, SQL\nPROFESSIONAL EXPERIENCE\nWalmart\nSr. Java/J2EE Developer\nFeb22 - Present",
            "harpreet.pdf", "Harpreet", "Kaur", "Sr. Java/ J2EE Developer", 9.0,
        ),
        (
            "Name: Eshasree\nEmail: arjun@aspirantspro.com\nPhone: +1 904-640-3010\n"
            "Sr. Full Stack Java Developer\nPROFESSIONAL SUMMARY\nAround 9+ years of experience.\n"
            "PROFESSIONAL EXPERIENCE\nClient: JPMC, Plano-Texas. Jan 2021 to Till Date\nRole: Sr. Full Stack Java Developer",
            "candidate.docx", "Eshasree", None, "Sr. Full Stack Java Developer", 9.0,
        ),
        (
            "Girish Changlere\ngchanglere346@gmail.com\n+1-224-427-9218\nSummary\n"
            "Sr. Business System Analyst and Certified Scrum Master with 10 years of experience.\n"
            "Education\nMaster of Science of Information Studies, Trine University, 2017\n"
            "Master of Business Administration, University of Pune, 2010\nAREAS OF EXPERTISE\nSDLC",
            "girish.pdf", "Girish", "Changlere", "Sr. Business System Analyst", 10.0,
        ),
        (
            "Abhaya\nEmail: example@example.com\nPhone: +1 408-789-7830\n"
            "CORE SKILLS\npython, sql, aws\nPROFESSIONAL EXPERIENCE\n"
            "Sr. (Lead/Architect) Software Engineer at Neiman Marcus/Saks Global, Dallas, TX  Apr 2021 – Present",
            "abhaya.pdf", "Abhaya", None, "Sr. (Lead/Architect) Software Engineer", None,
        ),
    ],
)
def test_cv_candidate_fields_extracts_name_title_and_experience(text, filename, first_name, last_name, title, years):
    fields = cv_candidate_fields(text, filename)
    assert fields["first_name"] == first_name
    assert fields["last_name"] == last_name
    assert fields["current_title"] == title
    assert fields["years_experience"] == years


def test_cv_candidate_fields_extracts_education_section():
    text = (
        "Girish Changlere\nSummary\nSr. Business System Analyst\n"
        "Education\nMaster of Science of Information Studies, Trine University, 2017\n"
        "Master of Business Administration, University of Pune, 2010\n"
        "B. Com, SRTMU of Nanded, 2007\nAREAS OF EXPERTISE\nSDLC Methodologies"
    )
    fields = cv_candidate_fields(text, "girish.pdf")
    assert fields["education"] is not None
    assert "Trine University" in fields["education"]
    assert "University of Pune" in fields["education"]
    assert "AREAS OF EXPERTISE" not in fields["education"]


def test_section_heading_is_not_mistaken_for_candidate_name():
    fields = cv_candidate_fields("CORE SKILLS\npython, sql, aws\nAbhaya\nexample@example.com", "resume.pdf")
    assert fields["first_name"] == "Abhaya"



def test_fullstack_architect_header_layout():
    text = (
        "Siva Rama Krishna Prasad Padamata\n"
        "Sr. Fullstack Architect\n"
        "West Chester, PA 19382\n"
        "candidate@example.com\n"
        "+1 628-262-0002\n"
        "A results-driven Fullstack Architect with over a decade of experience.\n"
        "PROFESSIONAL EXPERIENCE\n"
        "Fullstack Architect"
    )
    fields = cv_candidate_fields(text, "Siva_Padamata___Fullstack_Architect.docx")
    assert fields["first_name"] == "Siva"
    assert fields["last_name"] == "Rama Krishna Prasad Padamata"
    assert fields["current_title"] == "Sr. Fullstack Architect"
    assert fields["email"] == "candidate@example.com"


def test_java_lead_pdf_header_layout():
    text = (
        "Jeevan Reddy Bandi\n"
        "Email ID: jeevan@example.com\n"
        "Contact Number: 972-363-9478\n"
        "Professional Summary:\n"
        "I have 16+ years of experience in all phases of software development life cycle.\n"
        "Lead role provided technical guidance to a team of Java developers.\n"
        "Professional Experience\n"
        "Java Lead Developer"
    )
    fields = cv_candidate_fields(text, "Jeevan-Java Lead Developer.pdf")
    assert fields["first_name"] == "Jeevan"
    assert fields["last_name"] == "Reddy Bandi"
    assert fields["years_experience"] == 16.0
    assert fields["email"] == "jeevan@example.com"


def test_header_title_is_preferred_over_older_role_label():
    text = (
        "Alex Morgan\nSenior Data Engineer\nalex@example.com\n"
        "PROFESSIONAL SUMMARY\nExperienced engineer with 12 years of experience.\n"
        "PROFESSIONAL EXPERIENCE\n"
        "Role: Junior Software Developer\n"
        "Previous employer, 2014–2017"
    )
    fields = cv_candidate_fields(text, "alex-morgan.pdf")
    assert fields["current_title"] == "Senior Data Engineer"
    assert fields["years_experience"] == 12.0


def test_experience_is_not_guessed_from_vague_decade_phrase():
    text = (
        "Siva Rama Krishna Prasad Padamata\nSr. Fullstack Architect\n"
        "bindu@talentclustr.com\n"
        "A results-driven Fullstack Architect with over a decade of experience "
        "in architecting and deploying scalable web applications."
    )
    fields = cv_candidate_fields(text, "Siva_Padamata___Fullstack_Architect.docx")
    assert fields["first_name"] == "Siva"
    assert fields["last_name"] == "Rama Krishna Prasad Padamata"
    assert fields["current_title"] == "Sr. Fullstack Architect"
    assert fields["years_experience"] is None


def test_experience_extracts_explicit_sixteen_plus_years():
    text = (
        "Jeevan Reddy Bandi\nJava Lead Developer\n"
        "jeevanreddi.b@gmail.com\n"
        "Professional Summary\nI have 16+ years of experience in software development."
    )
    fields = cv_candidate_fields(text, "Jeevan-Java Lead Developer.pdf")
    assert fields["years_experience"] == 16.0


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        ("16+ years in IT", 16.0),
        ("12 years in software development", 12.0),
        ("More than 10 years of experience", 10.0),
        ("Over a decade of experience", None),
    ],
)
def test_experience_patterns_are_explicit_and_conservative(summary, expected):
    fields = cv_candidate_fields(
        "Jordan Taylor\nSenior Software Engineer\n"
        "jordan@example.com\nProfessional Summary\n" + summary,
        "jordan-taylor.pdf",
    )
    assert fields["years_experience"] == expected



def test_explicit_role_after_long_summary_is_found_in_employment_history():
    summary_lines = "\n".join(f"Summary detail {index} about platform delivery" for index in range(30))
    text = (
        "Taylor Morgan\n"
        "taylor@example.com\n"
        "Professional Summary\n"
        + summary_lines
        + "\nEmployment History\nRole: Senior Platform Engineer\n"
        "Example Systems\n2021 - Present"
    )
    fields = cv_candidate_fields(text, "taylor-morgan.pdf")
    assert fields["first_name"] == "Taylor"
    assert fields["current_title"] == "Senior Platform Engineer"



def test_filename_is_not_used_as_candidate_name_when_text_has_no_name():
    fields = cv_candidate_fields(
        "Professional Summary\nSenior Software Engineer\n"
        "alex@example.com\n10 years of experience in software development.",
        "Senior-Software-Engineer-Agency-Resume.pdf",
    )
    assert fields["first_name"] == "CV candidate"
    assert fields["last_name"] is None
