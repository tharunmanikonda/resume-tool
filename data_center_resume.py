"""Data center resume instructions and the user-confirmed client structure."""

import copy

CATEGORY = "data_center_infrastructure"
SKILL_CATEGORIES = [
    "Server Hardware & Infrastructure", "Operating Systems", "Networking & Cabling",
    "Data Center Operations", "IT Service Management", "Storage & Virtualization",
]


def profile_snapshot(profile, experience_key):
    result = copy.deepcopy(profile)
    result["resume_category"] = CATEGORY
    result["experience_history"] = [{
        "key": experience_key, "company": "HPE",
        "location": str((profile.get("contact") or {}).get("location", "")),
        "title": "Data Center Technician", "dates": "February 2024 - Present",
        "enabled": True,
    }]
    result["projects"] = []
    return result


def prompt(section):
    return "\n".join([
        "You tailor a Data Center / IT Infrastructure resume using the supplied schema.",
        "Return only the requested JSON fields for " + section + ".",
        "Use a top title of 2-6 words, a summary of 65-95 words, and experience titles containing role text only.",
        "Include all six skills categories with at least two concrete skills per category. Write experience bullets of 25-30 words.",
        "The user confirmed hands-on data center experience with one client, HPE, from February 2024 to Present.",
        "Preserve supplied name, contact details, education, earned certifications, location, employment dates and stable role keys.",
        "Use exactly one experience entry: HPE, Data Center Technician. Never add other employers or clients.",
        "SUMMARY: Follow this structure, adjusting years to the supplied dates rather than hard-coding two years:",
        "Detail-oriented Data Center Technician supporting enterprise data center infrastructure, server hardware maintenance, network connectivity, and IT operations. "
        "Emphasize rack-and-stack installations, hardware break-fix troubleshooting, component replacement, Linux and Windows Server support, incident resolution, and operational documentation. "
        "Mention Dell PowerEdge, HPE ProLiant, iDRAC, iLO and ServiceNow when supported by the confirmed experience and relevant to the posting. "
        "Use only the candidate's actual education; do not assume two Computer Science degrees.",
        "SKILLS: Use the supplied category order: " + ", ".join(SKILL_CATEGORIES) + ".",
        "Prioritize JD-relevant server diagnostics, BIOS/UEFI, RAM/SSD/PSU replacement, RAID, Linux CLI, SSH, logs, TCP/IP, DNS, DHCP, VLANs, copper/fiber cabling, switches, asset management, SOPs/MOPs and change management.",
        "EXPERIENCE: Produce the supplied bullet count, using the sample's practical operations focus:",
        "Server installation and deployment; rack placement and cable labeling; component diagnostics and replacement; "
        "hardware health monitoring; OS health checks; Layer 1/2 connectivity troubleshooting; ticket resolution; "
        "approved maintenance; inventory and rack documentation; collaboration with network and system administrators; "
        "secure access and approved operating procedures.",
        "Select responsibilities relevant to the JD and write distinct action-focused bullets. Do not copy the JD verbatim.",
        "Numerical evidence should appear where supported by supplied facts; never invent server counts, SLA percentages, ticket volumes or performance metrics.",
        "Do not add hypothetical projects, unsupported credentials, management scope, or software/AI product achievements unrelated to infrastructure operations.",
        "Final synthesis must preserve this technician framing, the one HPE entry, and the supplied skill categories.",
    ])
