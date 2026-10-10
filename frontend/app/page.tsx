"use client";

import Link from "next/link";

const features = [
  { number: "01", title: "Talent, all in one place", text: "Build a clear picture of every candidate, conversation and opportunity without losing the human details." },
  { number: "02", title: "A pipeline that moves", text: "Keep jobs, submissions, interviews and offers connected in one recruitment workflow." },
  { number: "03", title: "Know what needs attention", text: "Turn day-to-day recruitment activity into a sharper view of priorities, progress and outcomes." },
];

export default function HomePage() {
  return (
    <main className="marketing">
      <div className="marketing-topline"><span className="marketing-dot" /> Recruitment, with a clearer point of view <span className="topline-right">Built for people who move talent forward</span></div>
      <header className="marketing-nav">
        <Link href="/" className="marketing-brand" aria-label="AQERITH home"><span className="brand-mark"><i /><i /><b /></span><span>AQERITH</span></Link>
        <nav className="marketing-links" aria-label="Main navigation">
          <a href="#platform">Platform</a><a href="#features">Capabilities</a><a href="#workflow">How it works</a>
        </nav>
        <div className="marketing-nav-actions"><Link href="/login" className="nav-login">Sign in</Link><Link href="/login" className="marketing-cta small">Get started <span>↗</span></Link></div>
      </header>

      <section className="marketing-hero" id="platform">
        <div className="hero-copy">
          <div className="hero-kicker"><span /> RECRUITMENT INTELLIGENCE, REIMAGINED</div>
          <h1>Make every<br /><span>connection</span><br />count.</h1>
          <p className="hero-description">The recruitment workspace that brings your jobs, people and hiring momentum together — so your team can focus on the work that moves talent forward.</p>
          <div className="hero-actions"><Link href="/login" className="marketing-cta">Explore AQERITH <span>↗</span></Link><a href="#features" className="text-cta">Discover the platform <span>↓</span></a></div>
          <div className="hero-proof"><div className="proof-avatars"><span>R</span><span>T</span><span>A</span></div><p><strong>People first.</strong><br />Clarity at every stage.</p></div>
        </div>
        <div className="hero-art" aria-label="Illustration of a connected recruitment pipeline">
          <div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" />
          <div className="art-glow" />
          <div className="art-label label-top"><span className="status-pip blue" /> Talent, connected <b>↗</b></div>
          <div className="art-core"><div className="core-symbol"><i /><i /><b /></div><strong>Human potential</strong><span>MEETS OPPORTUNITY</span></div>
          <div className="art-label label-left"><span className="mini-icon orange">✳</span><div><b>Candidate journey</b><small>One connected view</small></div></div>
          <div className="art-label label-right"><span className="mini-icon purple">↗</span><div><b>Hiring momentum</b><small>Progress, made visible</small></div></div>
          <div className="art-label label-bottom"><span className="status-pip green" /> People in motion <span className="label-bars"><i /><i /><i /><i /></span></div>
          <div className="art-spark spark-a">✳</div><div className="art-spark spark-b">✦</div>
        </div>
        <div className="hero-bottomline"><span>BUILT AROUND THE PEOPLE BEHIND EVERY PLACEMENT</span><span>01 / THE AQERITH APPROACH</span></div>
      </section>

      <section className="manifesto" id="workflow">
        <div className="section-eyebrow"><span>01</span> LESS FRAGMENTATION. MORE FORWARD MOTION.</div>
        <div className="manifesto-grid"><h2>Recruitment is<br />human work.<br /><em>Your systems should<br />make it feel that way.</em></h2><div className="manifesto-copy"><p>Great hiring depends on timing, trust and the details between conversations. AQERITH brings the moving parts into one considered workspace, giving recruiters a clearer way to manage the process without losing sight of the people in it.</p><Link href="/login" className="underlined-link">Step into your workspace <span>↗</span></Link></div></div>
      </section>

      <section className="features-section" id="features">
        <div className="features-heading"><div><div className="section-eyebrow"><span>02</span> ONE WORKSPACE. CONNECTED WORK.</div><h2>Everything moves<br />better <em>together.</em></h2></div><p>From first conversation to final placement, keep the details connected and the next step in view.</p></div>
        <div className="feature-grid">{features.map((feature) => <article className="feature-card" key={feature.number}><div className="feature-number">{feature.number}<span>↗</span></div><div className="feature-line" /><h3>{feature.title}</h3><p>{feature.text}</p></article>)}</div>
      </section>

      <section className="closing-cta"><div className="closing-orb orb-blue" /><div className="closing-orb orb-orange" /><div className="section-eyebrow"><span>03</span> YOUR NEXT CHAPTER STARTS HERE</div><h2>Bring your recruitment<br /><em>into focus.</em></h2><p>A more connected way to manage the work behind every great hire.</p><Link href="/login" className="marketing-cta">Enter AQERITH <span>↗</span></Link></section>

      <footer className="marketing-footer"><Link href="/" className="marketing-brand"><span className="brand-mark"><i /><i /><b /></span><span>AQERITH</span></Link><span>The intelligence of human potential.</span><div><a href="#platform">Back to top ↑</a><Link href="/login">Sign in</Link></div><small>© {new Date().getFullYear()} AQERITH. All rights reserved.</small></footer>
    </main>
  );
}
