import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Applicant Privacy Notice | TalentOS Careers",
  description: "How information submitted through a TalentOS Careers application is used.",
  robots: { index: true, follow: true },
};

export default function ApplicantPrivacyPage() {
  return (
    <main className="careers-page">
      <header className="careers-header">
        <Link href="/careers" className="careers-brand">Talent<span>OS</span> Careers</Link>
        <Link href="/careers" className="career-back-link">← Careers</Link>
      </header>
      <article className="career-detail">
        <p className="careers-eyebrow">PRIVACY</p>
        <h1>Applicant privacy notice</h1>
        <p className="career-detail-meta">Last updated: 10 October 2026</p>
        <div className="career-detail-content">
          <h2>Who is responsible for your information?</h2>
          <p>The organisation advertising the role is responsible for deciding how applicant information is used. TalentOS provides recruitment software to support that process.</p>
          <h2>What information is collected?</h2>
          <p>When you apply through this page, the form collects your name, email address, optional phone number, the role you applied for, the source of your visit when provided, and a record that you agreed to the application notice.</p>
          <h2>Why is it used?</h2>
          <p>Your information is used to receive, manage and assess your application and to contact you about the role. It should not be used for unrelated purposes without an appropriate legal basis and notice.</p>
          <h2>Retention and your rights</h2>
          <p>The recruiting organisation should keep applicant information only as long as necessary for its stated purposes and applicable legal obligations. Depending on applicable law, you may have rights to access, correct, delete or restrict use of your information, and to raise a concern with your data protection authority.</p>
          <h2>Contact</h2>
          <p>This shared notice is a starting point, not a substitute for the recruiting organisation's specific privacy notice. Before using public applications in production, the organisation must provide its legal name, contact details, retention period, lawful basis and a working privacy contact.</p>
        </div>
        <Link className="career-view-link" href="/careers">Back to careers <span aria-hidden="true">→</span></Link>
      </article>
      <footer className="careers-footer">Powered by TalentOS · Recruitment, made more human.</footer>
    </main>
  );
}
