const jobs = [
  { title: "Senior Python Engineer", client: "Northstar Digital", applicants: 28, status: "Active", recruiter: "AM" },
  { title: "Data Analyst", client: "Brightline Group", applicants: 19, status: "Active", recruiter: "RK" },
  { title: "Full Stack Developer", client: "Vertex Systems", applicants: 34, status: "Interviewing", recruiter: "SG" },
  { title: "Cloud Engineer", client: "Atlas Technology", applicants: 12, status: "On hold", recruiter: "AM" },
];

const nav = ["Dashboard", "Jobs", "Candidates", "Submissions", "Interviews", "Clients", "Vendors", "Talent Bench", "Onboarding", "Placements", "Leads", "Reports"];

export default function Dashboard() {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">Talent<span>OS</span></div>
        <div className="nav-label">Workspace</div>
        {nav.map((item, i) => <div key={item} className={`nav-item ${i === 0 ? "active" : ""}`}><span>{["⌂","▣","♙","↗","◷","□","◇","♧","✓","◈","◌","▤"][i]}</span><span>{item}</span></div>)}
        <div className="nav-label">Administration</div>
        <div className="nav-item"><span>⚙</span><span>Settings</span></div>
        <div className="nav-item"><span>?</span><span>Help & support</span></div>
      </aside>

      <main className="main">
        <header className="topbar">
          <input className="search" placeholder="Search candidates, jobs, clients..." aria-label="Global search" />
          <div className="profile"><span>Acme Recruitment</span><div className="avatar">VG</div></div>
        </header>

        <section className="content">
          <div className="header-row">
            <div><div className="eyebrow">Recruitment operations</div><h1>Good afternoon</h1><p className="subtitle">Here’s what is happening across your hiring pipeline.</p></div>
            <div className="actions"><button className="btn">Import candidates</button><button className="btn primary">+ New requisition</button></div>
          </div>

          <div className="metrics">
            <div className="card"><div className="metric-title">Open requisitions</div><div className="metric-value">42</div><div className="metric-foot">↑ 8% this month</div></div>
            <div className="card"><div className="metric-title">Active candidates</div><div className="metric-value">1,284</div><div className="metric-foot">↑ 12% this month</div></div>
            <div className="card"><div className="metric-title">Interviews this week</div><div className="metric-value">37</div><div className="metric-foot">↑ 5 from last week</div></div>
            <div className="card"><div className="metric-title">Placements this month</div><div className="metric-value">18</div><div className="metric-foot">↑ 20% this month</div></div>
          </div>

          <div className="card" style={{ marginBottom: 18 }}>
            <div className="card-head"><span className="card-title">Recruitment pipeline</span><span className="link">View analytics →</span></div>
            <div className="pipeline">
              {[['New applicants','186'],['Screening','74'],['Submitted','51'],['Interview','37'],['Offer / hire','18']].map(([label, value]) => <div className="stage" key={label}><strong>{value}</strong><span>{label}</span></div>)}
            </div>
          </div>

          <div className="grid">
            <div className="card">
              <div className="card-head"><span className="card-title">Active requisitions</span><span className="link">View all →</span></div>
              <table className="table"><thead><tr><th>Position</th><th>Client</th><th>Applicants</th><th>Status</th></tr></thead><tbody>{jobs.map(j => <tr key={j.title}><td><strong>{j.title}</strong><br /><small style={{color:'var(--muted)'}}>Recruiter {j.recruiter}</small></td><td>{j.client}</td><td>{j.applicants}</td><td><span className={`badge ${j.status === 'Active' ? 'green' : j.status === 'Interviewing' ? 'blue' : 'amber'}`}>{j.status}</span></td></tr>)}</tbody></table>
            </div>
            <div className="card">
              <div className="card-head"><span className="card-title">Recent activity</span><span className="link">View activity →</span></div>
              <div className="activity">
                {[['New candidate added','Sarah Wilson was added to Senior Python Engineer','8 min ago'],['Interview scheduled','James Patel · Data Analyst · Tomorrow 10:30','24 min ago'],['Candidate submitted','Michael Chen submitted to Vertex Systems','41 min ago'],['Placement created','Aisha Khan placed at Northstar Digital','1 hr ago'],['New client lead','Brightline Group added as a prospect','2 hrs ago']].map(([a,b,c]) => <div className="activity-row" key={b}><div className="dot"/><div className="activity-text"><strong>{a}</strong><br />{b}<div className="activity-time">{c}</div></div></div>)}
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
