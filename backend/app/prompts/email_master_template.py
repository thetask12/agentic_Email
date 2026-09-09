"""
Master cold-outreach email template (System.txt section 14).
This is the seed/default EMAIL_TEMPLATES row created on first run.

Per explicit user instruction: this is a fixed, complete pitch supplied by
Botivate verbatim — it is sent identically to every company, with only the
sender name substituted. No AI personalization line is inserted into it.
"""

MASTER_SUBJECT = "A Complete Business Automation Team Beyond a Single MIS Hire"

MASTER_PLAIN_TEMPLATE = """Dear Sir/Madam,

Greetings from Botivate Services LLP, Raipur.

We noticed that your organization is strengthening its MIS function. This could be the right opportunity to go beyond regular MIS reporting and build a complete business automation system.

Many organizations hire an MIS professional expecting them to manage reporting as well as automate business processes. However, business automation requires multiple capabilities, including process analysis, software development, integrations, dashboards, data management, testing and continuous technical support.

Depending entirely on a single MIS resource can create several challenges:

- One person may not have expertise in every required technology
- Management must spend considerable time explaining and reviewing the work
- The quality of automation depends entirely on that individual's skills
- Proper testing, documentation and quality control may be missing
- Advanced automation and system integrations may remain incomplete
- If the employee leaves, system development and automation can stop
- The company must again search, hire and train another resource
- Business owners continue spending their valuable time and energy managing technical work

At Botivate, instead of depending on one individual, you receive the support of a complete business automation team.

We are a Raipur-based business automation company with an in-house team of 40+ professionals and experience working with 100+ clients.

We offer two business automation solutions:

1. AutoRocket - One Day Business Automation

AutoRocket is our ready-to-use business automation product designed to quickly bring important business processes, tasks, reports, follow-ups and management information into one centralized system.

It helps businesses begin their automation journey quickly without spending months developing a system from the beginning.

2. Botivate Business Automation Plan - 100% Customized Automation

For companies with unique workflows and requirements, Botivate provides a completely customized business automation solution.

Our team studies your existing processes and develops automation according to your exact business requirements, including:

- Customized MIS reports and live dashboards
- Sales, purchase, inventory and operational automation
- Dispatch, logistics and delivery management
- Billing, outstanding and collection tracking
- Approval, task and follow-up automation
- WhatsApp and email integrations
- ERP, CRM and third-party application integrations
- Customized workflows for different departments
- Trained MIS/DME manpower support
- Documentation and employee training
- Dedicated testing and quality control
- Continuous technical and operational support

Every system developed by Botivate goes through proper review, testing and quality checks. You do not have to depend on the knowledge or availability of one employee.

Even if a particular team member changes, Botivate continues to maintain the technology, documentation, process knowledge and support. Your automation journey continues without interruption.

Our objective is to provide a reliable, high-quality and continuously supported business automation system, while saving the management's valuable time and energy.

Please find a brief profile of Botivate and AutoRocket below.

Learn more about us:

Botivate: {{botivate_website}}
AutoRocket: {{autorocket_website}}

We would be happy to understand your requirements and recommend the right solution for your organization.

Please let us know a convenient time for a short meeting or live demonstration.
"""

MASTER_HTML_TEMPLATE = """<div style="font-family:Arial,sans-serif;font-size:14px;color:#1f2937;line-height:1.6;">
<p>Dear Sir/Madam,</p>
<p>Greetings from <strong>Botivate Services LLP, Raipur</strong>.</p>
<p>We noticed that your organization is strengthening its MIS function. This could be the right opportunity to go beyond regular MIS reporting and build a complete business automation system.</p>
<p>Many organizations hire an MIS professional expecting them to manage reporting as well as automate business processes. However, business automation requires multiple capabilities, including process analysis, software development, integrations, dashboards, data management, testing and continuous technical support.</p>
<p>Depending entirely on a single MIS resource can create several challenges:</p>
<ul>
<li>One person may not have expertise in every required technology</li>
<li>Management must spend considerable time explaining and reviewing the work</li>
<li>The quality of automation depends entirely on that individual's skills</li>
<li>Proper testing, documentation and quality control may be missing</li>
<li>Advanced automation and system integrations may remain incomplete</li>
<li>If the employee leaves, system development and automation can stop</li>
<li>The company must again search, hire and train another resource</li>
<li>Business owners continue spending their valuable time and energy managing technical work</li>
</ul>
<p>At <strong>Botivate</strong>, instead of depending on one individual, you receive the support of a complete business automation team.</p>
<p>We are a Raipur-based business automation company with an <strong>in-house team of 40+ professionals</strong> and experience working with <strong>100+ clients</strong>.</p>
<p>We offer two business automation solutions:</p>
<p><strong>1. AutoRocket &ndash; One Day Business Automation</strong></p>
<p>AutoRocket is our ready-to-use business automation product designed to quickly bring important business processes, tasks, reports, follow-ups and management information into one centralized system.</p>
<p>It helps businesses begin their automation journey quickly without spending months developing a system from the beginning.</p>
{{autorocket_banner}}
<p><strong>2. Botivate Business Automation Plan &ndash; 100% Customized Automation</strong></p>
<p>For companies with unique workflows and requirements, Botivate provides a completely customized business automation solution.</p>
<p>Our team studies your existing processes and develops automation according to your exact business requirements, including:</p>
<ul>
<li>Customized MIS reports and live dashboards</li>
<li>Sales, purchase, inventory and operational automation</li>
<li>Dispatch, logistics and delivery management</li>
<li>Billing, outstanding and collection tracking</li>
<li>Approval, task and follow-up automation</li>
<li>WhatsApp and email integrations</li>
<li>ERP, CRM and third-party application integrations</li>
<li>Customized workflows for different departments</li>
<li>Trained MIS/DME manpower support</li>
<li>Documentation and employee training</li>
<li>Dedicated testing and quality control</li>
<li>Continuous technical and operational support</li>
</ul>
<p>Every system developed by Botivate goes through proper review, testing and quality checks. You do not have to depend on the knowledge or availability of one employee.</p>
<p>Even if a particular team member changes, Botivate continues to maintain the technology, documentation, process knowledge and support. Your automation journey continues without interruption.</p>
<p>Our objective is to provide a <strong>reliable, high-quality and continuously supported business automation system</strong>, while saving the management's valuable time and energy.</p>
<p>Please find a brief profile of <strong>Botivate and AutoRocket</strong> below.</p>
{{botivate_profile_image}}
<p>Learn more about us:</p>
<p><strong>Botivate:</strong> <a href="{{botivate_website}}">{{botivate_website}}</a><br/>
<strong>AutoRocket:</strong> <a href="{{autorocket_website}}">{{autorocket_website}}</a></p>
<p>We would be happy to understand your requirements and recommend the right solution for your organization.</p>
<p>Please let us know a convenient time for a short meeting or live demonstration.</p>
{{signature_poster}}
</div>"""

DEFAULT_FOLLOW_UP_1_SUBJECT = "Re: A Complete Business Automation Team Beyond a Single MIS Hire"
DEFAULT_FOLLOW_UP_1_BODY = """Hi {{contact_name_or_team}},

Just following up on my earlier note regarding {{company_name}}'s {{job_title}} requirement.

If your team is currently evaluating options for MIS reporting, dashboards, \
or business process automation, we'd be happy to discuss how Botivate could support it.

Please let me know if this would be relevant.

Best regards,
{{sender_name}}
Botivate Services LLP
"""

DEFAULT_FOLLOW_UP_FINAL_SUBJECT = "Closing the loop — Botivate x {{company_name}}"
DEFAULT_FOLLOW_UP_FINAL_BODY = """Hi {{contact_name_or_team}},

I don't want to keep following up if the timing isn't right — I'll leave \
this here for now.

If a need for MIS/reporting automation comes up in the future, feel free to \
reach out anytime.

Best regards,
{{sender_name}}
Botivate Services LLP
"""
